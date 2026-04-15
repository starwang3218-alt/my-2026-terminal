import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 ---
CONFIG_FILE = "strategy_terminal_v4_perf.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "AI/算力核心": ["NVDA", "AVGO", "APP", "VICR", "CRDO"],
            "军工/航行电子": ["BBAI", "ISSC", "LOAR", "TTMI"],
            "量子/前沿科技": ["IONQ", "XNDU", "RGTI"],
            "硬资产/战略金属": ["MP", "ARE"],
            "中概/价值修复": ["KE", "TUYA"]
        },
        "benchmarks": {
            "AI/算力核心": "SOXX", "军工/航行电子": "ITA", "量子/前沿科技": "QTUM", 
            "硬资产/战略金属": "REMX", "能源/困境反转": "XOP", "中概/价值修复": "KWEB"
        },
        "notes": {}
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 初始化 ---
st.set_page_config(page_title="2026 战略终端 (Turbo)", layout="wide")
st_autorefresh(interval=300000, key="global_fixed_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg["benchmarks"], cfg.get("notes", {})

# --- 3. 核心计算工具 ---
def to_scalar(val):
    if isinstance(val, (pd.Series, pd.DataFrame)):
        return float(val.iloc[0]) if not val.empty else 0.0
    return float(val)

def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    w, h = 160, 40
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = [f"{(i/(len(prices)-1))*w:.1f},{h-((p-p_min)/(p_max-p_min)*h):.1f}" for i,p in enumerate(prices)]
    path_data = " ".join(pts)
    return f'<svg width="{w}" height="{h}"><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2"/></svg>'

@st.cache_data(ttl=600)
def fetch_all_sync(sectors, benchmarks):
    all_tickers = list(set([t for ts in sectors.values() for t in ts]))
    # ✅ 修复 TypeError: 使用 set().union 或直接对两个 set 使用 |
    all_bench = list(set(benchmarks.values()) | {"SOXX", "AIQ", "XLI", "QTUM", "KWEB", "REMX"})
    
    # 批量下载 2 年历史 (1次请求)
    full_data = yf.download(all_tickers + all_bench, period="2y", interval="1d", group_by='ticker', progress=False)
    # 批量下载 15 分钟分时 (1次请求)
    intra_data = yf.download(all_tickers, period="1d", interval="15m", group_by='ticker', progress=False)

    results = []
    b_res = {}
    s_strength = {}

    # 1. 解析 Benchmark
    for b in all_bench:
        try:
            hist = full_data[b].dropna() if b in full_data else pd.DataFrame()
            if len(hist) >= 2:
                c_last = to_scalar(hist['Close'].iloc[-1])
                c_prev = to_scalar(hist['Close'].iloc[-2])
                b_res[b] = {"chg": ((c_last - c_prev) / c_prev) * 100}
            else: b_res[b] = {"chg": 0.0}
        except: b_res[b] = {"chg": 0.0}

    # 2. 解析个股
    for sec_name, tickers in sectors.items():
        b_sym = benchmarks.get(sec_name, "SPY")
        b_chg = b_res.get(b_sym, {"chg": 0.0})["chg"]
        sec_chgs = []

        for t in tickers:
            try:
                h = full_data[t].dropna() if t in full_data else pd.DataFrame()
                if h.empty: continue
                
                # 分时数据
                it = intra_data[t].dropna() if t in intra_data else pd.DataFrame()
                
                price = to_scalar(h['Close'].iloc[-1])
                day_chg = ((price - to_scalar(h['Close'].iloc[-2])) / to_scalar(h['Close'].iloc[-2])) * 100
                sec_chgs.append(day_chg)

                results.append({
                    "ticker": t, "sector": sec_name, "price": price, "change": day_chg, "rs": day_chg - b_chg,
                    "spark": get_sparkline_svg(it['Close'].tolist(), "green" if day_chg>=0 else "red"),
                    "total_5d": ((price - to_scalar(h['Close'].iloc[-6]))/to_scalar(h['Close'].iloc[-6]))*100 if len(h)>6 else 0,
                    "total_144d": ((price - to_scalar(h['Close'].iloc[-145]))/to_scalar(h['Close'].iloc[-145]))*100 if len(h)>=145 else 0,
                    "total_288d": ((price - to_scalar(h['Close'].iloc[0]))/to_scalar(h['Close'].iloc[0]))*100 if len(h)>=288 else 0,
                    "history": h.tail(6)
                })
            except: pass
        
        if sec_chgs:
            avg_chg = sum(sec_chgs)/len(sec_chgs)
            s_strength[sec_name] = {"avg_chg": avg_chg, "alpha": avg_chg - b_chg, "bench": b_sym}

    return b_res, results, s_strength

# --- 4. UI 渲染 ---
st.title("🏛️ 战略资产监控终端 (Turbo 2.1)")

with st.sidebar:
    if st.button("🚀 强制刷新", type="primary", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.divider()
    with st.expander("📁 架构管理"):
        ns, nb = st.text_input("新建板块"), st.text_input("对标 ETF")
        if st.button("增加"):
            if ns and nb: st.session_state.my_sectors[ns]=[]; st.session_state.my_benchmarks[ns]=nb.upper(); save_config(); st.rerun()
        if st.session_state.my_sectors:
            ts = st.selectbox("选择板块", list(st.session_state.my_sectors.keys()))
            nt = st.text_input("代码")
            if st.button("添加"):
                if nt: st.session_state.my_sectors[ts].append(nt.upper()); save_config(); st.rerun()
    st.divider()
    all_t = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    if all_t:
        e_t = st.selectbox("笔记标的", all_t)
        st.session_state.my_notes[e_t] = st.text_area("博弈逻辑", value=st.session_state.my_notes.get(e_t, ""), height=150)
        if st.button("💾 保存"): save_config(); st.success("已同步")

# 数据同步
b_res, m_res, s_strength = fetch_all_sync(st.session_state.my_sectors, st.session_state.my_benchmarks)

# 顶部大盘雷达
RADAR_NAMES = {"SOXX":"芯片","AIQ":"AI","XLI":"工业","QTUM":"量子","KWEB":"中概","REMX":"稀土"}
r_cols = st.columns(len(RADAR_NAMES))
for i, sym in enumerate(RADAR_NAMES.keys()):
    with r_cols[i]:
        chg = b_res.get(sym, {"chg":0})["chg"]
        st.metric(RADAR_NAMES[sym], f"{chg:+.2f}%")

# 板块战力强度
st.subheader("📡 板块战力雷达 (Sector Alpha)")
if s_strength:
    s_cols = st.columns(len(s_strength))
    for i, (name, v) in enumerate(s_strength.items()):
        with s_cols[i]:
            st.markdown(f"<div style='background:#f0f2f6; padding:10px; border-radius:10px; border-left:5px solid {'green' if v['alpha']>0 else 'red'};'><b>{name}</b><br><span style='font-size:1.2rem; color:{'green' if v['avg_chg']>0 else 'red'};'>{v['avg_chg']:+.2f}%</span><br><small>vs {v['bench']}: {v['alpha']:+.2f}%</small></div>", unsafe_allow_html=True)

st.divider()

# 主赛道与排行
l, r = st.columns([4, 1.3])
with l:
    if st.session_state.my_sectors:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                for s in [x for x in m_res if x['sector'] == s_name]:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.5, 4, 0.5])
                        with c1:
                            st.markdown(f"### {s['ticker']}\n{s['spark']}\n## ${s['price']:.2f}\n**{s['change']:+.2f}%**", unsafe_allow_html=True)
                            st.link_button("📈 图表", f"https://www.tradingview.com/chart/MdN4tzco/?symbol={s['ticker']}")
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    val_cur = to_scalar(s['history']['Close'].iloc[idx])
                                    val_pre = to_scalar(s['history']['Close'].iloc[idx-1])
                                    d_chg = ((val_cur - val_pre) / val_pre) * 100
                                    st.markdown(f"<small>{s['history'].index[idx].strftime('%m-%d')}</small><br><b style='color:{'green' if d_chg>0 else 'red'};'>{d_chg:+.1f}%</b>", unsafe_allow_html=True)
                            st.markdown(f"<div style='background:#eee; padding:5px; margin-top:10px; font-size:0.9rem;'>5日: {s['total_5d']:+.1f}% | 144日: {s['total_144d']:+.1f}% | 288日: {s['total_288d']:+.1f}%</div>", unsafe_allow_html=True)
                            with st.expander("逻辑"): st.write(st.session_state.my_notes.get(s['ticker'], ""))
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"): st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r:
    st.subheader("🏆 战力排行")
    b_t = st.tabs(["今日", "5日", "144日", "288日"])
    keys = ['change', 'total_5d', 'total_144d', 'total_288d']
    for idx, k in enumerate(keys):
        with b_t[idx]:
            sorted_m = sorted(m_res, key=lambda x: x[k], reverse=True)
            for i, item in enumerate(sorted_m):
                st.write(f"{i+1}. **{item['ticker']}** {item[k]:+.1f}%")