#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BLOCK_HINTS = [
    "access denied",
    "akamai",
    "forbidden",
    "temporarily unavailable",
    "request unsuccessful",
    "bot",
    "captcha",
]


@dataclass
class Job:
    url: str
    name: str
    original_url: str = ""


@dataclass
class DownloadResult:
    ok: bool
    page_url: str
    page_name: str
    saved_path: str = ""
    file_url: str = ""
    via: str = ""
    note: str = ""


def get_last_trading_date_string() -> str:
    from datetime import datetime, timedelta
    today = datetime.now()
    if today.weekday() == 0:
        last_trading_day = today - timedelta(days=3)
    elif today.weekday() == 6:
        last_trading_day = today - timedelta(days=2)
    else:
        last_trading_day = today - timedelta(days=1)
    return last_trading_day.strftime("%Y%m%d")


def safe_name(text: str, max_len: int = 120) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(text))
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text[:max_len].strip() or "fund"


def parse_input_line(line: str) -> Job | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    parts = [p.strip() for p in re.split(r"\t+|\s{2,}", raw) if p.strip()]
    if not parts:
        return None
    if parts[0].startswith("http://") or parts[0].startswith("https://"):
        url = parts[0]
        name = parts[-1] if len(parts) >= 2 else Path(url).name
        return Job(name=name.upper(), url=url, original_url=url)
    return None


def parse_jobs(input_file: Path) -> list[Job]:
    jobs = []
    for line in input_file.read_text(encoding="utf-8").splitlines():
        job = parse_input_line(line)
        if job:
            jobs.append(job)
    return jobs


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }
    )
    return s


async def save_debug(page, output_dir: Path, name: str, prefix: str) -> None:
    debug_dir = output_dir.parent / "_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_name(name)
    try:
        html = await page.content()
        (debug_dir / f"{stem}_{prefix}.html").write_text(html, encoding="utf-8")
    except Exception:
        pass
    try:
        text = await page.text_content("body") or ""
        (debug_dir / f"{stem}_{prefix}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass
    try:
        await page.screenshot(path=str(debug_dir / f"{stem}_{prefix}.png"), full_page=True)
    except Exception:
        pass


async def find_all_holdings_modal_url(page) -> str:
    hrefs = await page.eval_on_selector_all(
        "a[href]",
        "els => els.map(a => a.href || a.getAttribute('href') || '').filter(Boolean)"
    )

    patterns = [
        re.compile(r"all-holdings", re.I),
        re.compile(r"holdings", re.I),
    ]

    for href in hrefs:
        h = href.lower()
        if "wisdomtree.com" not in h:
            continue
        if any(p.search(h) for p in patterns):
            return href

    html = await page.content()
    regexes = [
        r'https://www\.wisdomtree\.com/[^"\']*all-holdings[^"\']*',
        r'https://www\.wisdomtree\.com/[^"\']*holdings[^"\']*',
        r'(/global/etf-details/modals/all-holdings\?id=[^"\']+)',
        r'(/global/etf-details/modals/[^"\']*holdings[^"\']*)',
    ]
    for pat in regexes:
        m = re.search(pat, html, re.I)
        if m:
            matched = m.group(1) if m.lastindex else m.group(0)
            return urljoin(page.url, matched)
    return ""


async def open_view_all_holdings_inline(page) -> bool:
    patterns = [
        re.compile(r"View All Holdings", re.I),
        re.compile(r"All Holdings", re.I),
        re.compile(r"Holdings", re.I),
    ]
    for pat in patterns:
        locators = [
            page.get_by_role("button", name=pat),
            page.get_by_role("link", name=pat),
            page.get_by_text(pat),
        ]
        for locator in locators:
            try:
                if await locator.first.count() == 0:
                    continue
                try:
                    await locator.first.click(timeout=6000)
                except Exception:
                    await locator.first.click(timeout=6000, force=True)
                await page.wait_for_timeout(3000)
                return True
            except Exception:
                continue
    return False


def extract_as_of_from_text(text: str) -> str:
    if not text:
        return ""
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    for line in lines[:80]:
        m = re.search(r"As of\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", line, re.I)
        if m:
            return m.group(1).strip()
    m = re.search(r"As of\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.I)
    if m:
        return m.group(1).strip()
    return ""


def flatten_columns(cols) -> list[str]:
    if not isinstance(cols, pd.MultiIndex):
        return [str(c).strip() for c in cols]
    out: list[str] = []
    for tup in cols:
        parts: list[str] = []
        for x in tup:
            s = str(x).strip()
            if s and s.lower() != "nan" and s not in parts:
                parts.append(s)
        out.append(parts[-1] if parts else "")
    return out


def normalize_header_name(name: str) -> str:
    s = re.sub(r"\s+", " ", str(name or "")).strip()
    s_low = s.lower()
    mapping = {
        "security name": "Security_Name",
        "holding ticker": "Holding_Ticker",
        "ticker": "Holding_Ticker",
        "identifier": "Identifier",
        "country": "Country",
        "quantity": "Quantity",
        "shares": "Quantity",
        "weight": "Weight",
        "market value": "Market_Value",
        "asset class": "Asset_Class",
        "sedol": "SEDOL",
        "cusip": "CUSIP",
        "isin": "ISIN",
        "figi": "FIGI",
        "security type": "Security_Type",
    }
    return mapping.get(s_low, re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_") or "col")


def parse_tables_safely(html: str) -> list[pd.DataFrame]:
    all_dfs: list[pd.DataFrame] = []
    seen_signatures: set[tuple] = set()
    for header in ([0, 1, 2], [0, 1], 0, None):
        try:
            dfs = pd.read_html(StringIO(html), header=header)
        except Exception:
            continue
        for df in dfs:
            try:
                df = df.copy()
                df.columns = flatten_columns(df.columns)
                df.columns = [normalize_header_name(c) for c in df.columns]
                df = df.dropna(how="all")
                if df.empty:
                    continue
                signature = (tuple(df.columns), len(df))
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                all_dfs.append(df)
            except Exception:
                continue
    return all_dfs


def choose_best_table(dfs: list[pd.DataFrame]) -> pd.DataFrame | None:
    keywords = [
        "security_name", "holding_ticker", "ticker", "figi", "identifier",
        "country", "quantity", "weight", "market_value"
    ]
    scored: list[tuple[int, pd.DataFrame]] = []
    for df in dfs:
        try:
            probe = df.copy()
            probe.columns = [str(c).strip() for c in probe.columns]
            probe = probe.dropna(how="all")
            if probe.empty:
                continue
            cols = " | ".join([str(c).lower() for c in probe.columns])
            score = len(probe) + len(probe.columns) * 10
            for kw in keywords:
                if kw in cols:
                    score += 100
            if len(probe) >= 20:
                score += 100
            if "weight" in cols:
                score += 80
            scored.append((score, probe))
        except Exception:
            continue
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def clean_table(df: pd.DataFrame, task: Job, modal_url: str, as_of: str) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalize_header_name(c) for c in out.columns]
    if "Holding_Ticker" in out.columns:
        out = out[out["Holding_Ticker"].astype(str).str.strip().str.lower() != "ticker"]
        out = out[out["Holding_Ticker"].astype(str).str.strip().str.lower() != "holding ticker"]
    if "Security_Name" in out.columns:
        out = out[out["Security_Name"].astype(str).str.strip().str.lower() != "security name"]
    out = out.dropna(axis=1, how="all")
    out = out.dropna(axis=0, how="all").reset_index(drop=True)
    out.insert(0, "ETF_Ticker", task.name)
    out.insert(1, "Record_Date", as_of.replace("-", "/") if as_of else "")
    out.insert(2, "Source_URL", task.url)
    out.insert(3, "Modal_URL", modal_url)
    return out


def looks_blocked(text: str) -> bool:
    t = (text or "").lower()
    return any(hint in t for hint in BLOCK_HINTS)


async def try_export_holdings(page, output_dir: Path, name: str) -> Path | None:
    patterns = [
        re.compile(r"Export Holdings", re.I),
        re.compile(r"Export", re.I),
        re.compile(r"Download", re.I),
    ]
    for pat in patterns:
        locators = [
            page.get_by_role("link", name=pat),
            page.get_by_role("button", name=pat),
            page.get_by_text(pat),
        ]
        for locator in locators:
            try:
                if await locator.first.count() == 0:
                    continue
                for _ in range(2):
                    try:
                        async with page.expect_download(timeout=12000) as download_info:
                            try:
                                await locator.first.click(timeout=5000)
                            except Exception:
                                await locator.first.click(timeout=5000, force=True)
                        download = await download_info.value
                        suggested = download.suggested_filename or f"{safe_name(name)}.csv"
                        if not suggested.lower().endswith((".csv", ".xlsx", ".xls")):
                            suggested = f"{Path(suggested).stem}.csv"
                        save_path = output_dir.parent / "_tmp" / suggested
                        save_path.parent.mkdir(parents=True, exist_ok=True)
                        await download.save_as(str(save_path))
                        return save_path
                    except Exception:
                        await page.wait_for_timeout(1500)
                        continue
            except Exception:
                continue
    return None


async def try_parse_and_save(page, task: Job, output_dir: Path, csv_path: Path, modal_url: str) -> DownloadResult | None:
    body_text = await page.text_content("body") or ""
    as_of = extract_as_of_from_text(body_text)

    export_path = await try_export_holdings(page, output_dir, task.name)
    if export_path is not None and export_path.exists():
        try:
            if export_path.suffix.lower() == ".csv":
                try:
                    df = pd.read_csv(export_path, dtype=str)
                except Exception:
                    df = pd.read_csv(export_path, dtype=str, encoding="latin1")
            else:
                last_error = None
                df = None
                for engine in [None, "openpyxl", "xlrd"]:
                    try:
                        df = pd.read_excel(export_path, dtype=str, engine=engine)
                        break
                    except Exception as e:
                        last_error = e
                if df is None:
                    raise RuntimeError(f"读取导出文件失败: {last_error}")
            df = clean_table(df, task, modal_url, as_of)
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            export_path.unlink(missing_ok=True)
            return DownloadResult(True, task.url, task.name, saved_path=str(csv_path), file_url=modal_url, via="wisdomtree-export", note=f"账期: {as_of or 'unknown'}")
        except Exception:
            pass

    html = await page.content()
    dfs = parse_tables_safely(html)
    best = choose_best_table(dfs) if dfs else None
    if best is not None and not best.empty:
        best = clean_table(best, task, modal_url, as_of)
        best.to_csv(csv_path, index=False, encoding="utf-8-sig")
        return DownloadResult(True, task.url, task.name, saved_path=str(csv_path), file_url=modal_url, via="wisdomtree-table-parse", note=f"账期: {as_of or 'unknown'}")

    if looks_blocked(body_text):
        await save_debug(page, output_dir, task.name, "modal_blocked")
        return DownloadResult(False, task.url, task.name, note="holdings 页面被拦截")

    await save_debug(page, output_dir, task.name, "modal_no_table")
    return DownloadResult(False, task.url, task.name, note="modal 页面未识别到持仓表")


async def fetch_one_once(task: Job, output_dir: Path, overwrite: bool, show: bool) -> DownloadResult:
    csv_path = output_dir / f"{safe_name(task.name)}.csv"
    if csv_path.exists() and not overwrite:
        return DownloadResult(True, task.url, task.name, saved_path=str(csv_path), via="pre-cache", note="已存在，跳过")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not show)
        page = await browser.new_page(user_agent=USER_AGENT)
        try:
            print(f"[START] {task.name} -> {task.url}", flush=True)
            await page.goto(task.url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            await page.wait_for_timeout(4000)

            modal_url = await find_all_holdings_modal_url(page)
            if not modal_url:
                clicked = await open_view_all_holdings_inline(page)
                if clicked:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000)
                    result = await try_parse_and_save(page, task, output_dir, csv_path, page.url)
                    if result is not None:
                        return result
                await save_debug(page, output_dir, task.name, "fund_page_no_modal")
                return DownloadResult(False, task.url, task.name, note="未找到 All Holdings modal 链接")

            modal_page = await browser.new_page(user_agent=USER_AGENT)
            try:
                await modal_page.goto(modal_url, wait_until="domcontentloaded", timeout=45000)
                try:
                    await modal_page.wait_for_load_state("networkidle", timeout=12000)
                except Exception:
                    pass
                await modal_page.wait_for_timeout(4000)
                return await try_parse_and_save(modal_page, task, output_dir, csv_path, modal_url)
            finally:
                await modal_page.close()

        except PlaywrightTimeoutError:
            return DownloadResult(False, task.url, task.name, note="页面超时")
        except Exception as e:
            return DownloadResult(False, task.url, task.name, note=f"异常: {e}")
        finally:
            await page.close()
            await browser.close()


async def fetch_one(task: Job, output_dir: Path, overwrite: bool, show: bool, retries: int) -> DownloadResult:
    total_attempts = retries + 1
    last_result: DownloadResult | None = None
    for attempt in range(1, total_attempts + 1):
        result = await fetch_one_once(task, output_dir, overwrite, show)
        if result.ok:
            return result
        last_result = result
        if attempt < total_attempts:
            print(f"[RETRY] {task.name} attempt {attempt}/{total_attempts} failed: {result.note}", flush=True)
            await asyncio.sleep(2)
    return last_result or DownloadResult(False, task.url, task.name, note="未知失败")


async def process_single_job(idx: int, total: int, job: Job, output_dir: Path, session: requests.Session, args: argparse.Namespace, sem: asyncio.Semaphore) -> DownloadResult:
    async with sem:
        result = await fetch_one(
            task=job,
            output_dir=output_dir,
            overwrite=bool(getattr(args, "overwrite", False)),
            show=bool(getattr(args, "show", False)),
            retries=1,
        )
        if result.ok:
            print(f"[{idx:03d}/{total}] ✅ 成功 | {job.name} -> {result.saved_path}", flush=True)
        else:
            print(f"[{idx:03d}/{total}] ❌ 失败 | {job.name} | {result.note}", flush=True)
        return result


def build_parser():
    parser = argparse.ArgumentParser(description="WisdomTree v13-compatible downloader")
    parser.add_argument("-i", "--input", required=True, help="输入文件：基金详情页 URL")
    parser.add_argument("-o", "--output", default="wisdomtree_holdings", help="输出目录")
    parser.add_argument("--concurrency", type=int, default=1, help="并发数，默认 1")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在文件")
    parser.add_argument("--show", action="store_true", help="显示浏览器")
    parser.add_argument("--debug", action="store_true", help="调试输出")
    return parser


async def _standalone_async(args):
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = parse_jobs(input_path)
    print(f"读取到 {len(jobs)} 个任务", flush=True)
    if not jobs:
        print("输入文件中没有有效任务", flush=True)
        return 2
    sem = asyncio.Semaphore(max(1, args.concurrency))
    session = build_session()
    results = []
    for idx, job in enumerate(jobs, start=1):
        results.append(await process_single_job(idx, len(jobs), job, output_dir, session, args, sem))
    log_path = output_dir / "download_log.csv"
    with log_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["page_name", "page_url", "ok", "saved_path", "file_url", "via", "note"])
        for r in results:
            writer.writerow([r.page_name, r.page_url, "Y" if r.ok else "N", r.saved_path, r.file_url, r.via, r.note])
    ok_count = sum(1 for r in results if r.ok)
    print(f"\n✨ 完成：{ok_count}/{len(results)} 成功。日志已写入: {log_path}")
    return 0 if ok_count == len(results) else 2


def main():
    args = build_parser().parse_args()
    return asyncio.run(_standalone_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
