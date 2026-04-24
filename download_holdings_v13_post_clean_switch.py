#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

DATE_PATTERNS = [
    # 2026-04-24 / 2026/04/24
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),
    # 04/24/2026
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b"),
    # Apr 24, 2026 / April 24, 2026
    re.compile(r"\b(Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+(\d{1,2}),\s*(20\d{2})\b", re.I),
]

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="严格日更系统包装器：在 v7 下载器基础上增加 manifest / 日期识别 / 增量 fresh 收集 / 强制补位清洗 / 补救重下载"
    )
    p.add_argument("-i", "--input", required=True, help="输入 txt 文件路径")
    p.add_argument("-o", "--output", default="daily_system_output", help="输出目录")
    p.add_argument(
        "--downloader",
        default="download_holdings_v7_unified.py",
        help="底层下载器路径，默认同目录下 download_holdings_v7_unified.py",
    )
    p.add_argument("--target-date", default="", help="目标日期 YYYY-MM-DD；默认自动取底层下载器交易日")
    p.add_argument("--beijing-download-window", action="store_true", default=True, help="仅允许北京时间周二到周六执行下载。默认开启")
    p.add_argument("--ignore-beijing-window", action="store_true", help="忽略北京时间下载窗口限制，强制执行下载")
    p.add_argument("--concurrency", type=int, default=5, help="下载并发数")
    p.add_argument("--repair-rounds", type=int, default=2, help="补救重下载轮数，默认 2")
    p.add_argument("--refresh-stale-on-download-day", action="store_true", default=True, help="在允许下载的当天，对 stale 文件至少主动重拉 1 次。默认开启")
    p.add_argument("--retry-stale-same-run", action="store_true", help="同一次运行内，对非最新(stale)文件继续重下载。默认关闭")
    p.add_argument("--stop-if-no-fresh-progress", action="store_true", default=True, help="如果最新文件数没有提升，则停止后续补救下载")
    p.add_argument("--fresh-threshold", type=float, default=99.0, help="最新完整度阈值，默认 99")
    p.add_argument("--start-clean-threshold", type=float, default=98.0, help="达到该最新完整度后，开始用旧文件补位并进入清洗阶段，默认 98")
    p.add_argument("--force-fallback-clean", action="store_true", help="强制进入补位+清洗阶段。即使 fresh 完整度未达到阈值，也允许用旧文件补齐后继续清洗")
    p.add_argument("--post-clean-repair-rounds", type=int, default=1, help="清洗后再次尝试下载缺失/补位文件的轮数，默认 1")
    p.add_argument("--post-clean-repair-mode", choices=["auto", "on", "off"], default="auto", help="清洗后是否立即做补救下载。auto=force-fallback-clean 时关闭，其余开启")
    p.add_argument("--usable-threshold", type=float, default=100.0, help="可用完整度阈值，默认 100")
    p.add_argument("--max-fallback-days", type=int, default=3, help="允许用旧文件补位的最大天数，默认 3")
    p.add_argument("--overwrite", action="store_true", help="覆盖已有同名 CSV")
    p.add_argument("--no-dynamic", action="store_true", help="透传给底层下载器")
    p.add_argument("--debug", action="store_true", help="透传给底层下载器，并输出更多诊断文件")
    p.add_argument("--keep-raw", action="store_true", help="透传给底层下载器，保留原始文件")
    p.add_argument("--probe-lines", type=int, default=80, help="日期探测读取的前几行，默认 80")
    return p.parse_args()


def resolve_target_date(args: argparse.Namespace, downloader_module) -> date:
    if args.target_date:
        return datetime.strptime(args.target_date, "%Y-%m-%d").date()

    if hasattr(downloader_module, "get_last_trading_date_string"):
        s = downloader_module.get_last_trading_date_string()
        if re.fullmatch(r"\d{8}", s):
            return datetime.strptime(s, "%Y%m%d").date()

    return date.today()


def load_downloader(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"底层下载器不存在: {path}")
    module_name = f"downloader_v7_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Python 3.13 下，dataclass 在装饰阶段会通过 cls.__module__ 回查 sys.modules。
    # 如果这里不先注册模块，某些脚本在 exec_module 时会报:
    # AttributeError: 'NoneType' object has no attribute '__dict__'
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def ensure_dirs(output_root: Path) -> dict[str, Path]:
    paths = {
        "root": output_root,
        "manifest": output_root / "manifest.db",
        "current": output_root / "current_csv",
        "raw": output_root / "raw",
        "clean_input": output_root / "clean_input",
        "report_ready": output_root / "report_ready",
        "logs": output_root / "_logs",
        "debug": output_root / "_debug",
        "state": output_root / "_state",
    }
    for k, p in paths.items():
        if k != "manifest":
            p.mkdir(parents=True, exist_ok=True)
    return paths


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_ts TEXT NOT NULL,
            target_date TEXT NOT NULL,
            input_file TEXT NOT NULL,
            total_jobs INTEGER NOT NULL,
            fresh_threshold REAL NOT NULL,
            usable_threshold REAL NOT NULL,
            fresh_count INTEGER DEFAULT 0,
            usable_count INTEGER DEFAULT 0,
            missing_count INTEGER DEFAULT 0,
            stale_count INTEGER DEFAULT 0,
            fallback_count INTEGER DEFAULT 0,
            report_allowed INTEGER DEFAULT 0,
            note TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS files (
            target_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            page_name TEXT NOT NULL,
            page_url TEXT NOT NULL,
            original_url TEXT NOT NULL,
            expected INTEGER DEFAULT 1,
            attempts INTEGER DEFAULT 0,
            last_round INTEGER DEFAULT 0,
            download_status TEXT DEFAULT 'pending',
            probe_status TEXT DEFAULT 'unknown',
            probe_date TEXT DEFAULT '',
            probe_source TEXT DEFAULT '',
            is_latest INTEGER DEFAULT 0,
            usable INTEGER DEFAULT 0,
            fallback_used INTEGER DEFAULT 0,
            fallback_from_date TEXT DEFAULT '',
            fallback_csv_path TEXT DEFAULT '',
            current_csv_path TEXT DEFAULT '',
            archive_csv_path TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            PRIMARY KEY (target_date, ticker)
        );

        CREATE TABLE IF NOT EXISTS backlog (
            ticker TEXT NOT NULL,
            unresolved_target_date TEXT NOT NULL,
            first_seen_ts TEXT NOT NULL,
            last_seen_ts TEXT NOT NULL,
            reason TEXT NOT NULL,
            is_open INTEGER DEFAULT 1,
            PRIMARY KEY (ticker, unresolved_target_date)
        );
        """
    )
    return conn


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def upsert_expected_jobs(conn: sqlite3.Connection, jobs, target_date: date) -> None:
    for job in jobs:
        conn.execute(
            """
            INSERT INTO files (
                target_date, ticker, page_name, page_url, original_url, expected, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(target_date, ticker) DO UPDATE SET
                page_name=excluded.page_name,
                page_url=excluded.page_url,
                original_url=excluded.original_url,
                expected=1,
                updated_at=excluded.updated_at
            """,
            (
                target_date.isoformat(),
                job.name,
                job.name,
                job.url,
                getattr(job, "original_url", job.url),
                now_iso(),
            ),
        )
    conn.commit()


def _parse_date_match(m: re.Match) -> Optional[date]:
    groups = m.groups()
    raw = m.group(0)
    try:
        if len(groups) == 3 and raw[:3].isalpha():
            mon = MONTHS[groups[0].lower()]
            day = int(groups[1])
            year = int(groups[2])
            return date(year, mon, day)
        if len(groups) == 3 and len(groups[0]) == 4:
            return date(int(groups[0]), int(groups[1]), int(groups[2]))
        if len(groups) == 3 and len(groups[2]) == 4:
            return date(int(groups[2]), int(groups[0]), int(groups[1]))
    except Exception:
        return None
    return None


def probe_date_from_text(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    lowered = text.lower()
    priority_keywords = [
        "as of", "date", "effective", "holdings date", "basket date",
        "portfolio date", "daily holdings",
    ]
    lines = text.splitlines()
    priority_zone = "\n".join([ln for ln in lines[:80] if any(k in ln.lower() for k in priority_keywords)])
    search_blocks = [priority_zone, "\n".join(lines[:120]), text[:20000]]

    for block_idx, block in enumerate(search_blocks, start=1):
        for pat in DATE_PATTERNS:
            for m in pat.finditer(block):
                d = _parse_date_match(m)
                if d:
                    return d.isoformat(), f"text_pattern_{block_idx}"
    return "", ""


def probe_date_from_csv(path: Path, probe_lines: int = 80) -> tuple[str, str]:
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= probe_lines:
                    break
                lines.append(line.rstrip("\n"))
        text = "\n".join(lines)
        probed, source = probe_date_from_text(text)
        if probed:
            return probed, source

        # fallback to file modified date
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
        return mtime, "mtime_fallback"
    except Exception:
        return "", ""


def probe_existing_current_files(conn: sqlite3.Connection, current_dir: Path, target_date: date, probe_lines: int) -> None:
    rows = conn.execute(
        "SELECT ticker FROM files WHERE target_date=?",
        (target_date.isoformat(),)
    ).fetchall()
    for (ticker,) in rows:
        path = current_dir / f"{ticker}.csv"
        if not path.exists():
            continue
        probe_date, probe_source = probe_date_from_csv(path, probe_lines=probe_lines)
        is_latest = 1 if probe_date == target_date.isoformat() else 0
        usable = 1 if probe_date else 0
        conn.execute(
            """
            UPDATE files
            SET current_csv_path=?,
                probe_date=?,
                probe_source=?,
                probe_status=?,
                is_latest=?,
                usable=?,
                download_status=CASE WHEN ? THEN 'present' ELSE download_status END,
                updated_at=?
            WHERE target_date=? AND ticker=?
            """,
            (
                str(path),
                probe_date,
                probe_source,
                "ok" if probe_date else "unknown",
                is_latest,
                usable,
                1 if path.exists() else 0,
                now_iso(),
                target_date.isoformat(),
                ticker,
            ),
        )
    conn.commit()


def export_manifest_csv(conn: sqlite3.Connection, output_path: Path, target_date: date) -> None:
    cols = [
        "target_date", "ticker", "page_name", "page_url", "expected", "attempts",
        "last_round", "download_status", "probe_status", "probe_date", "probe_source",
        "is_latest", "usable", "fallback_used", "fallback_from_date",
        "current_csv_path", "archive_csv_path", "last_error", "updated_at"
    ]
    rows = conn.execute(
        f"SELECT {', '.join(cols)} FROM files WHERE target_date=? ORDER BY ticker",
        (target_date.isoformat(),)
    ).fetchall()
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)


def find_last_archived_csv(raw_root: Path, ticker: str, target_date: date, max_days: int) -> tuple[str, str, int]:
    best_date = None
    best_path = None
    for d in range(1, max_days + 1):
        dt = target_date - timedelta(days=d)
        cand = raw_root / dt.isoformat() / f"{ticker}.csv"
        if cand.exists():
            best_date = dt
            best_path = cand
            return str(cand), dt.isoformat(), d
    return "", "", -1


def apply_fallbacks(conn: sqlite3.Connection, raw_root: Path, clean_input: Path, target_date: date, max_days: int) -> None:
    rows = conn.execute(
        """
        SELECT ticker, current_csv_path, is_latest, usable
        FROM files
        WHERE target_date=?
        """,
        (target_date.isoformat(),)
    ).fetchall()

    for ticker, current_csv_path, is_latest, usable in rows:
        target_clean_csv = clean_input / f"{ticker}.csv"

        if target_clean_csv.exists():
            target_clean_csv.unlink(missing_ok=True)

        if current_csv_path and is_latest:
            src = Path(current_csv_path)
            if src.exists():
                shutil.copy2(src, target_clean_csv)
                conn.execute(
                    """
                    UPDATE files SET usable=1, fallback_used=0, fallback_from_date='', fallback_csv_path='', updated_at=?
                    WHERE target_date=? AND ticker=?
                    """,
                    (now_iso(), target_date.isoformat(), ticker),
                )
            continue

        fallback_path, fallback_date, lag_days = find_last_archived_csv(raw_root, ticker, target_date, max_days)
        if fallback_path:
            shutil.copy2(fallback_path, target_clean_csv)
            conn.execute(
                """
                UPDATE files
                SET usable=1,
                    fallback_used=1,
                    fallback_from_date=?,
                    fallback_csv_path=?,
                    updated_at=?
                WHERE target_date=? AND ticker=?
                """,
                (fallback_date, fallback_path, now_iso(), target_date.isoformat(), ticker),
            )

            conn.execute(
                """
                INSERT INTO backlog (ticker, unresolved_target_date, first_seen_ts, last_seen_ts, reason, is_open)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(ticker, unresolved_target_date) DO UPDATE SET
                    last_seen_ts=excluded.last_seen_ts,
                    reason=excluded.reason,
                    is_open=1
                """,
                (ticker, target_date.isoformat(), now_iso(), now_iso(), f"used fallback from {fallback_date}"),
            )
        else:
            conn.execute(
                """
                UPDATE files
                SET usable=0, fallback_used=0, fallback_from_date='', fallback_csv_path='', updated_at=?
                WHERE target_date=? AND ticker=?
                """,
                (now_iso(), target_date.isoformat(), ticker),
            )
            conn.execute(
                """
                INSERT INTO backlog (ticker, unresolved_target_date, first_seen_ts, last_seen_ts, reason, is_open)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(ticker, unresolved_target_date) DO UPDATE SET
                    last_seen_ts=excluded.last_seen_ts,
                    reason=excluded.reason,
                    is_open=1
                """,
                (ticker, target_date.isoformat(), now_iso(), now_iso(), "missing fresh file and no fallback"),
            )
    conn.commit()


def close_backlog_for_latest(conn: sqlite3.Connection, target_date: date) -> None:
    rows = conn.execute(
        "SELECT ticker, is_latest FROM files WHERE target_date=?",
        (target_date.isoformat(),)
    ).fetchall()
    for ticker, is_latest in rows:
        if is_latest:
            conn.execute(
                """
                UPDATE backlog
                SET is_open=0, last_seen_ts=?, reason='resolved'
                WHERE ticker=? AND unresolved_target_date=?
                """,
                (now_iso(), ticker, target_date.isoformat()),
            )
    conn.commit()


def build_summary(conn: sqlite3.Connection, target_date: date, fresh_threshold: float, usable_threshold: float) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM files WHERE target_date=?", (target_date.isoformat(),)).fetchone()[0]
    fresh = conn.execute("SELECT COUNT(*) FROM files WHERE target_date=? AND is_latest=1", (target_date.isoformat(),)).fetchone()[0]
    usable = conn.execute("SELECT COUNT(*) FROM files WHERE target_date=? AND usable=1", (target_date.isoformat(),)).fetchone()[0]
    fallback = conn.execute("SELECT COUNT(*) FROM files WHERE target_date=? AND fallback_used=1", (target_date.isoformat(),)).fetchone()[0]

    # 关键修正：
    # missing 只表示“连文件都没有 / 也没有补位”，不再把 stale 误算成 missing。
    missing = conn.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE target_date=?
          AND (current_csv_path='' OR current_csv_path IS NULL)
          AND fallback_used=0
        """,
        (target_date.isoformat(),)
    ).fetchone()[0]

    # stale 表示“文件拿到了，也识别出日期了，但不是目标日期”
    stale = conn.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE target_date=?
          AND probe_date!=''
          AND is_latest=0
        """,
        (target_date.isoformat(),)
    ).fetchone()[0]

    present = conn.execute(
        """
        SELECT COUNT(*) FROM files
        WHERE target_date=?
          AND current_csv_path!=''
        """,
        (target_date.isoformat(),)
    ).fetchone()[0]

    observed_dates = [
        r[0] for r in conn.execute(
            """
            SELECT DISTINCT probe_date FROM files
            WHERE target_date=? AND probe_date!=''
            ORDER BY probe_date
            """,
            (target_date.isoformat(),)
        ).fetchall()
    ]

    fresh_pct = (fresh / total * 100.0) if total else 0.0
    usable_pct = (usable / total * 100.0) if total else 0.0
    present_pct = (present / total * 100.0) if total else 0.0
    report_allowed = int(usable_pct >= usable_threshold)

    return {
        "target_date": target_date.isoformat(),
        "total_expected": total,
        "present_count": present,
        "fresh_count": fresh,
        "usable_count": usable,
        "fallback_count": fallback,
        "missing_count": missing,
        "stale_count": stale,
        "observed_probe_dates": observed_dates,
        "present_pct": round(present_pct, 2),
        "fresh_pct": round(fresh_pct, 2),
        "usable_pct": round(usable_pct, 2),
        "fresh_threshold": fresh_threshold,
        "usable_threshold": usable_threshold,
        "report_allowed": bool(report_allowed),
        "report_grade": (
            "formal"
            if fresh_pct >= fresh_threshold and usable_pct >= usable_threshold
            else ("warning" if usable_pct >= usable_threshold else "blocked")
        ),
    }


def write_summary_files(summary: dict, output_root: Path, target_date: date) -> None:
    summary_json = output_root / "_state" / f"summary_{target_date.isoformat()}.json"
    summary_md = output_root / "_state" / f"summary_{target_date.isoformat()}.md"

    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        f"# Daily Summary {summary['target_date']}",
        "",
        f"- 应到文件数: {summary['total_expected']}",
        f"- 最新文件数: {summary['fresh_count']} ({summary['fresh_pct']}%)",
        f"- 可用文件数: {summary['usable_count']} ({summary['usable_pct']}%)",
        f"- 使用旧文件补位数: {summary['fallback_count']}",
        f"- 未补位缺失数: {summary['missing_count']}",
        f"- 非最新但可用数: {summary['stale_count']}",
        f"- 报告门槛 fresh >= {summary['fresh_threshold']}%, usable >= {summary['usable_threshold']}%",
        f"- 是否允许出报告: {'是' if summary['report_allowed'] else '否'}",
        f"- 质量等级: {summary['report_grade']}",
    ]
    summary_md.write_text("\n".join(md), encoding="utf-8")


async def run_downloader_round(
    downloader,
    jobs_subset,
    output_current_dir: Path,
    args: argparse.Namespace,
    round_no: int,
    target_date: date,
    conn: sqlite3.Connection,
):
    if not jobs_subset:
        return []

    session = downloader.build_session()
    sem = asyncio.Semaphore(max(1, int(args.concurrency)))
    dl_args = SimpleNamespace(
        overwrite=args.overwrite,
        no_dynamic=args.no_dynamic,
        debug=args.debug,
        keep_raw=args.keep_raw,
    )
    tasks = [
        downloader.process_single_job(idx, len(jobs_subset), job, output_current_dir, session, dl_args, sem)
        for idx, job in enumerate(jobs_subset, start=1)
    ]
    results = await asyncio.gather(*tasks)

    for res in results:
        ticker = res.page_name
        ok = 1 if res.ok else 0
        conn.execute(
            """
            UPDATE files
            SET attempts = attempts + 1,
                last_round = ?,
                download_status = ?,
                current_csv_path = CASE WHEN ? THEN ? ELSE current_csv_path END,
                last_error = CASE WHEN ? THEN '' ELSE ? END,
                updated_at = ?
            WHERE target_date=? AND ticker=?
            """,
            (
                round_no,
                "success" if res.ok else "failed",
                ok,
                res.saved_path,
                ok,
                res.note,
                now_iso(),
                target_date.isoformat(),
                ticker,
            ),
        )
    conn.commit()
    return results


def probe_after_round(conn: sqlite3.Connection, current_dir: Path, raw_root: Path, target_date: date, probe_lines: int) -> None:
    rows = conn.execute(
        """
        SELECT ticker, current_csv_path, download_status
        FROM files
        WHERE target_date=?
        """,
        (target_date.isoformat(),)
    ).fetchall()

    for ticker, current_csv_path, download_status in rows:
        csv_path = Path(current_csv_path) if current_csv_path else (current_dir / f"{ticker}.csv")
        if not csv_path.exists():
            conn.execute(
                """
                UPDATE files
                SET probe_status='missing', is_latest=0, usable=0, updated_at=?
                WHERE target_date=? AND ticker=?
                """,
                (now_iso(), target_date.isoformat(), ticker),
            )
            continue

        probe_date, probe_source = probe_date_from_csv(csv_path, probe_lines=probe_lines)
        is_latest = 1 if probe_date == target_date.isoformat() else 0

        raw_csv_path = ""
        if probe_date:
            raw_day_dir = raw_root / probe_date
            raw_day_dir.mkdir(parents=True, exist_ok=True)
            raw_csv = raw_day_dir / f"{ticker}.csv"
            shutil.copy2(csv_path, raw_csv)
            raw_csv_path = str(raw_csv)

        conn.execute(
            """
            UPDATE files
            SET current_csv_path=?,
                probe_date=?,
                probe_source=?,
                probe_status=?,
                is_latest=?,
                usable=CASE WHEN ? THEN 1 ELSE 0 END,
                archive_csv_path=CASE WHEN ? != '' THEN ? ELSE archive_csv_path END,
                download_status=CASE
                    WHEN ? AND ? THEN 'fresh'
                    WHEN ? AND ? THEN 'stale'
                    ELSE download_status
                END,
                updated_at=?
            WHERE target_date=? AND ticker=?
            """,
            (
                str(csv_path),
                probe_date,
                probe_source,
                "ok" if probe_date else "unknown",
                is_latest,
                is_latest,
                raw_csv_path,
                raw_csv_path,
                1 if str(csv_path) else 0,
                is_latest,
                1 if str(csv_path) else 0,
                1 if (probe_date and not is_latest) else 0,
                now_iso(),
                target_date.isoformat(),
                ticker,
            ),
        )
    conn.commit()


def choose_retry_jobs(
    conn: sqlite3.Connection,
    all_jobs,
    target_date: date,
    retry_stale_same_run: bool = False,
    include_stale_once: bool = False,
):
    if retry_stale_same_run:
        need = conn.execute(
            """
            SELECT ticker
            FROM files
            WHERE target_date=?
              AND (download_status IN ('failed', 'pending', 'stale', 'missing') OR is_latest=0)
            ORDER BY ticker
            """,
            (target_date.isoformat(),)
        ).fetchall()
    elif include_stale_once:
        # 允许下载的当天，先对 stale 文件主动重拉 1 次，看看上游是否已经更新成 target_date
        need = conn.execute(
            """
            SELECT ticker
            FROM files
            WHERE target_date=?
              AND (
                download_status IN ('failed', 'pending', 'missing', 'stale')
                OR (current_csv_path != '' AND is_latest=0)
              )
            ORDER BY ticker
            """,
            (target_date.isoformat(),)
        ).fetchall()
    else:
        # 默认只重试真正失败/缺失的；stale 等下一次调度再追
        need = conn.execute(
            """
            SELECT ticker
            FROM files
            WHERE target_date=?
              AND download_status IN ('failed', 'pending', 'missing')
            ORDER BY ticker
            """,
            (target_date.isoformat(),)
        ).fetchall()
    retry_tickers = {ticker for (ticker,) in need}
    return [job for job in all_jobs if job.name in retry_tickers]


def write_retry_queue(conn: sqlite3.Connection, output_root: Path, target_date: date) -> None:
    rows = conn.execute(
        """
        SELECT page_url, ticker
        FROM files
        WHERE target_date=?
          AND usable=0
        ORDER BY ticker
        """,
        (target_date.isoformat(),)
    ).fetchall()
    path = output_root / "_state" / f"retry_queue_{target_date.isoformat()}.txt"
    with path.open("w", encoding="utf-8") as f:
        for url, ticker in rows:
            f.write(f"{url}\t{ticker}\n")


def reset_report_ready(report_ready: Path) -> None:
    for p in report_ready.glob("*.csv"):
        p.unlink(missing_ok=True)


def reset_clean_input(clean_input: Path) -> None:
    for p in clean_input.glob("*.csv"):
        p.unlink(missing_ok=True)


def record_run(conn: sqlite3.Connection, args: argparse.Namespace, target_date: date, total_jobs: int, summary: dict) -> None:
    conn.execute(
        """
        INSERT INTO runs (
            run_ts, target_date, input_file, total_jobs,
            fresh_threshold, usable_threshold,
            fresh_count, usable_count, missing_count, stale_count, fallback_count,
            report_allowed, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            target_date.isoformat(),
            str(Path(args.input).resolve()),
            total_jobs,
            float(args.fresh_threshold),
            float(args.usable_threshold),
            int(summary["fresh_count"]),
            int(summary["usable_count"]),
            int(summary["missing_count"]),
            int(summary["stale_count"]),
            int(summary["fallback_count"]),
            int(summary["report_allowed"]),
            summary["report_grade"],
        ),
    )
    conn.commit()



def choose_post_clean_retry_jobs(conn: sqlite3.Connection, all_jobs, target_date: date):
    rows = conn.execute(
        """
        SELECT ticker
        FROM files
        WHERE target_date=?
          AND (fallback_used=1 OR usable=0)
        ORDER BY ticker
        """,
        (target_date.isoformat(),)
    ).fetchall()
    tickers = {ticker for (ticker,) in rows}
    return [job for job in all_jobs if job.name in tickers]



def get_beijing_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        # Fallback: use UTC+8 naive conversion
        return datetime.utcnow() + timedelta(hours=8)

def is_beijing_download_day(now_dt: datetime) -> bool:
    # Python weekday: Mon=0 ... Sun=6
    # Allow download only on Beijing Tue-Sat => 1..5
    return now_dt.weekday() in {1, 2, 3, 4, 5}

def write_schedule_skip_files(output_root: Path, target_date: date, bj_now: datetime, reason: str) -> None:
    state_dir = output_root / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_date": target_date.isoformat(),
        "beijing_now": bj_now.strftime("%Y-%m-%d %H:%M:%S"),
        "weekday": bj_now.strftime("%A"),
        "download_skipped": True,
        "reason": reason,
    }
    (state_dir / f"schedule_skip_{target_date.isoformat()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def should_start_clean_phase(summary: dict, args: argparse.Namespace) -> tuple[bool, str]:
    fresh_pct = float(summary.get("fresh_pct", 0.0))
    if getattr(args, "force_fallback_clean", False):
        return True, f"force-fallback-clean enabled (fresh_pct={fresh_pct}%)"
    if fresh_pct >= float(args.start_clean_threshold):
        return True, f"fresh_pct {fresh_pct}% >= start_clean_threshold {args.start_clean_threshold}%"
    return False, f"fresh_pct {fresh_pct}% < start_clean_threshold {args.start_clean_threshold}%"


def should_run_post_clean_repair(args: argparse.Namespace) -> tuple[bool, str]:
    mode = getattr(args, "post_clean_repair_mode", "auto")
    force_fallback = getattr(args, "force_fallback_clean", False)

    if mode == "on":
        return True, "post-clean-repair-mode=on"
    if mode == "off":
        return False, "post-clean-repair-mode=off"
    # auto
    if force_fallback:
        return False, "post-clean-repair-mode=auto and force-fallback-clean=True"
    return True, "post-clean-repair-mode=auto and normal clean flow"

def write_clean_phase_decision(output_root: Path, target_date: date, summary: dict, allow_clean: bool, reason: str) -> None:
    state_dir = output_root / "_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_date": target_date.isoformat(),
        "allow_clean_phase": allow_clean,
        "reason": reason,
        "fresh_count": summary.get("fresh_count"),
        "fresh_pct": summary.get("fresh_pct"),
        "usable_count": summary.get("usable_count"),
        "usable_pct": summary.get("usable_pct"),
        "fallback_count": summary.get("fallback_count"),
        "missing_count": summary.get("missing_count"),
        "stale_count": summary.get("stale_count"),
        "force_fallback_clean": bool(getattr(summary, "force_fallback_clean", False)) if not isinstance(summary, dict) else None,
    }
    (state_dir / f"clean_phase_decision_{target_date.isoformat()}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

async def main_async() -> int:
    args = parse_args()
    output_root = Path(args.output).expanduser().resolve()
    paths = ensure_dirs(output_root)

    downloader_path = Path(args.downloader)
    if not downloader_path.is_absolute():
        downloader_path = (Path.cwd() / downloader_path).resolve()
    if not downloader_path.exists():
        # fall back to same dir as wrapper
        alt = (Path(__file__).resolve().parent / args.downloader).resolve()
        if alt.exists():
            downloader_path = alt

    downloader = load_downloader(downloader_path)
    target_date = resolve_target_date(args, downloader)
    bj_now = get_beijing_now()
    allow_download_today = True
    if args.beijing_download_window and not args.ignore_beijing_window:
        allow_download_today = is_beijing_download_day(bj_now)
    input_file = Path(args.input).expanduser().resolve()
    all_jobs = downloader.parse_jobs(input_file)

    conn = connect_db(paths["manifest"])
    upsert_expected_jobs(conn, all_jobs, target_date)
    probe_existing_current_files(conn, paths["current"], target_date, probe_lines=args.probe_lines)

    all_round_logs = []
    prev_fresh_count = None
    if not allow_download_today:
        print(f"⏸ 当前北京时间 {bj_now.strftime('%Y-%m-%d %H:%M:%S')}，不在下载窗口（仅周二到周六下载），本次跳过下载阶段。")
        write_schedule_skip_files(output_root, target_date, bj_now, "outside Beijing Tue-Sat download window")
    for round_no in range(0, int(args.repair_rounds) + 1):
        jobs_subset = choose_retry_jobs(
            conn,
            all_jobs,
            target_date,
            retry_stale_same_run=bool(args.retry_stale_same_run and round_no > 0),
            include_stale_once=bool(args.refresh_stale_on_download_day and allow_download_today and round_no == 0),
        )

        if not allow_download_today:
            jobs_subset = []

        if jobs_subset:
            print(f"\n[ROUND {round_no}] 需要处理 {len(jobs_subset)} 个文件")
            results = await run_downloader_round(
                downloader=downloader,
                jobs_subset=jobs_subset,
                output_current_dir=paths["current"],
                args=args,
                round_no=round_no,
                target_date=target_date,
                conn=conn,
            )
            all_round_logs.extend(results)
            probe_after_round(conn, paths["current"], paths["raw"], target_date, probe_lines=args.probe_lines)
        else:
            print(f"\n[ROUND {round_no}] 无需下载，直接对账")

        fresh_only_summary = build_summary(conn, target_date, args.fresh_threshold, args.usable_threshold)
        export_manifest_csv(conn, paths["state"] / f"manifest_{target_date.isoformat()}.csv", target_date)
        write_retry_queue(conn, output_root, target_date)
        write_summary_files(fresh_only_summary, output_root, target_date)

        allow_clean_now, clean_reason = should_start_clean_phase(fresh_only_summary, args)
        if allow_clean_now:
            print(f"[ROUND {round_no}] 进入清洗阶段: {clean_reason}")
            break

        if prev_fresh_count is not None and int(fresh_only_summary["fresh_count"]) <= int(prev_fresh_count) and args.stop_if_no_fresh_progress:
            print(f"[ROUND {round_no}] 最新文件数没有提升（fresh_count={fresh_only_summary['fresh_count']}），停止后续补救下载，等待下一次调度再追最新。")
            break

        prev_fresh_count = int(fresh_only_summary["fresh_count"])

        if round_no < int(args.repair_rounds):
            print(f"[ROUND {round_no}] 最新完整度 {fresh_only_summary['fresh_pct']}%，继续补救重下载...")
        else:
            print(f"[ROUND {round_no}] 已到补救轮数上限，结束下载阶段。")

    # 达到 fresh 阈值，或者显式启用 --force-fallback-clean 时，进入补位+清洗阶段
    pre_clean_summary = build_summary(conn, target_date, args.fresh_threshold, args.usable_threshold)
    allow_clean_phase, clean_reason = should_start_clean_phase(pre_clean_summary, args)
    write_clean_phase_decision(output_root, target_date, pre_clean_summary, allow_clean_phase, clean_reason)

    if allow_clean_phase:
        print(f"[CLEAN PHASE] 启动补位+清洗阶段: {clean_reason}")
        reset_clean_input(paths["clean_input"])
        apply_fallbacks(conn, paths["raw"], paths["clean_input"], target_date, max_days=args.max_fallback_days)
        close_backlog_for_latest(conn, target_date)

        run_post_clean_repair, repair_reason = should_run_post_clean_repair(args)
        print(f"[POST-CLEAN REPAIR] 配置判定: {repair_reason}")

        if run_post_clean_repair:
            # 清洗后再做一次缺失文件补救下载（这里用 fallback_used / unusable 作为补救队列）
            for extra_round in range(1, int(args.post_clean_repair_rounds) + 1):
                post_jobs = choose_post_clean_retry_jobs(conn, all_jobs, target_date)
                if not post_jobs:
                    break
                print(f"\n[POST-CLEAN REPAIR {extra_round}] 需要补救 {len(post_jobs)} 个文件")
                results = await run_downloader_round(
                    downloader=downloader,
                    jobs_subset=post_jobs,
                    output_current_dir=paths["current"],
                    args=args,
                    round_no=100 + extra_round,
                    target_date=target_date,
                    conn=conn,
                )
                all_round_logs.extend(results)
                probe_after_round(conn, paths["current"], paths["raw"], target_date, probe_lines=args.probe_lines)
                reset_clean_input(paths["clean_input"])
                apply_fallbacks(conn, paths["raw"], paths["clean_input"], target_date, max_days=args.max_fallback_days)
                close_backlog_for_latest(conn, target_date)
        else:
            print("[POST-CLEAN REPAIR] 本次跳过清洗后立即补救下载。")

        # 当前模板里，report_ready 直接等于 clean_input（后续可替换成正式清洗输出）
        reset_report_ready(paths["report_ready"])
        for csv_file in paths["clean_input"].glob("*.csv"):
            shutil.copy2(csv_file, paths["report_ready"] / csv_file.name)
    else:
        print(f"[CLEAN PHASE] 本次不进入清洗阶段: {clean_reason}")

    final_summary = build_summary(conn, target_date, args.fresh_threshold, args.usable_threshold)
    record_run(conn, args, target_date, len(all_jobs), final_summary)

    # export a simple run log from downloader results
    run_log_path = output_root / "_state" / f"download_log_{target_date.isoformat()}.csv"
    with run_log_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["page_name", "page_url", "ok", "saved_path", "file_url", "via", "note"])
        for r in all_round_logs:
            writer.writerow([
                getattr(r, "page_name", ""),
                getattr(r, "page_url", ""),
                "Y" if getattr(r, "ok", False) else "N",
                getattr(r, "saved_path", ""),
                getattr(r, "file_url", ""),
                getattr(r, "via", ""),
                getattr(r, "note", ""),
            ])

    print("\n=== DAILY SYSTEM SUMMARY ===")
    print(f"beijing_now: {bj_now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"download_window_allowed: {allow_download_today}")
    print(f"force_fallback_clean: {getattr(args, 'force_fallback_clean', False)}")
    print(f"post_clean_repair_mode: {getattr(args, 'post_clean_repair_mode', 'auto')}")
    print(json.dumps(final_summary, ensure_ascii=False, indent=2))
    print(f"manifest: {paths['manifest']}")
    print(f"current csv: {paths['current']}")
    print(f"report ready: {paths['report_ready']}")
    print(f"state files: {paths['state']}")

    conn.close()
    return 0 if final_summary["report_allowed"] else 2


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n用户中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
