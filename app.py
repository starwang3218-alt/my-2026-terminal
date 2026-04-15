import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 (数据保险箱：写死你的核心标的) ---
CONFIG_FILE = "my_terminal_config_2026.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "光通信/AI算力": ["CRDO", "AAOI", "NVDA", "AMD"],
            "工业/机械": ["MKSI"],
            "量子科技/康波底座": ["IONQ", "XNDU", "RGTI", "QBTS"],
            "稀土/战略金属": ["MP", "UAMY", "USAR", "ALM"],
            "军工AI/决策软件": ["BBAI"]
        },
        "benchmarks": {
            "光通信/AI算力": "SOXX", "工业/机械": "XLI", "量子科技/康波底座": "ARKK", "稀土/战略金属": "REMX", "军工AI/决策软件": "ITA"
        },
        "notes": {
            "BBAI": "3.32附近震荡，属于决策AI。国防订单确定性高。",
            "UAMY": "美国本土锑业，军工咽喉资源，2027限制令直接受益。"
        }
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 初始化 ---
st.set_page_config(page_title="2026 战略终端", layout="wide")
st_autorefresh(interval=300000, key="global_fixed_refresh")

RADAR_NAMES = {"SOXX": "半导体/芯片", "AIQ": "人工智能/AI", "XLI": "工业/机械", "XLU": "核能/公用事业", "KWEB": "中概互联/科技", "REMX": "稀土/战略金属"}

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg.get("benchmarks", {}), cfg.get("notes", {})

# --- 3. 核心引擎：SVG 分时曲线 ---
def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    w, h = 160, 40
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = [f"{(i/(len(prices)-1))*w:.1f},{h-((p-p_min)/(p_max-p_min)*h):.1f}" for i,p in enumerate(prices)]
    path_data = " ".join(pts)
    return f'<svg width="{w}" height="{h}" style="display:block;margin:5px 0;"><path d="M 0,{h} L {path_data} L {w},{h} Z" fill="{color}" fill-opacity="0.1" stroke="none"/><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

# --- 4. 数据抓取 ---
@st.cache_data(ttl=300)
def fetch_terminal_data(sector_cfg, bench_cfg):
    bench_results = {}
    all_needed_bench = set(["SOXX", "AIQ", "XLI", "XLU", "KWEB", "REMX", "ITA", "ARKK"]) | set(bench_cfg.values())
    for b_sym in all_needed_bench:
        try:
            d = yf.download(b_sym, period="2d", interval="15m", progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            c_last, c_first = float(d['Close'].iloc[-1]), float(d['Close'].iloc[0])
            bench_results[b_sym] = {"chg": ((c_last-c_first)/c_first)*100, "flow": (c_last-c_first)*float(d['Volume'].sum())/1e10}
        except: bench_results[b_sym] = {"chg": 0.0, "flow": 0.0}
    
    m_data = []
    for sec_name, tickers in sector_cfg.items():
        b_sym, b_chg = bench_cfg.get(sec_name, "SPY"), bench_results.get(bench_cfg.get(sec_name, "SPY"), {"chg": 0.0})["chg"]
        for t in tickers:
            try:
                obj = yf.Ticker(t)
                h, intra = obj.history(period="2y"), obj.history(period="1d", interval="15m")
                if isinstance(h.columns, pd.MultiIndex): h.columns = h.columns.get_level_values(0)
                if isinstance(intra.columns, pd.MultiIndex): intra.columns = intra.columns.get_level_values(0)
                latest_c = float(h['Close'].iloc[-1])
                today_chg = ((latest_c - float(h['Close'].iloc[-2]))/float(h['Close'].iloc[-2]))*100
                m_data.append({
                    "ticker": t, "sector": sec_name, "bench": b_sym, "price": latest_c, "change": today_chg, "rs": today_chg - b_chg,
                    "spark": get_sparkline_svg(intra['Close'].tolist(), "green" if today_chg>=0 else "red"),
                    "history": h.tail(6), "total_5d": ((latest_c - h['Close'].iloc[-6])/h['Close'].iloc[-6])*100,
                    "total_144d": ((latest_c - h['Close'].iloc[-145])/h['Close'].iloc[-145])*100 if len(h)>=145 else 0,
                    "total_288d": ((latest_c - h['Close'].iloc[0])/h['Close'].iloc[0])*100 if len(h)>=288 else 0
                })
            except: pass
    return bench_results, m_data

# --- 5. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    if st.button("🔄 立即刷新数据", type="primary", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.divider()
    with st.expander("📁 板块管理"):
        ns, nb = st.text_input("板块名"), st.text_input("对标 ETF")
        if st.button("创建"):
            if ns and nb: st.session_state.my_sectors[ns] = []; st.session_state.my_benchmarks[ns] = nb.upper(); save_config(); st.rerun()
    st.subheader("➕ 添加个股")
    if st.session_state.my_sectors:
        ts, nt = st.selectbox("选择板块", list(st.session_state.my_sectors.keys())), st.text_input("代码")
        if st.button("加入"):
            if nt: st.session_state.my_sectors[ts].append(nt.upper()); save_config(); st.rerun()

# --- 6. 渲染 ---
st.write("### 🏛️ 战略资产监控终端")
with st.status("正在同步实时数据...", expanded=False):
    b_res, m_res = fetch_terminal_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

st.subheader("📡 核心板块资金雷达 (Net Flow)")
r_cols = st.columns(6)
for idx, sym in enumerate(["SOXX", "AIQ", "XLI", "XLU", "KWEB", "REMX"]):
    with r_cols[idx]:
        d = b_res.get(sym, {"chg": 0.0, "flow": 0.0})
        st.markdown(f"<div style='text-align:center; border:1px solid #eee; border-radius:12px; padding:10px; background:white;'><div style='font-size:0.85rem; font-weight:bold;'>{RADAR_NAMES[sym]}</div><div style='font-size:1.1rem; color:{'green' if d['chg']>=0 else 'red'}; font-weight:900;'>{d['chg']:+.2f}%</div><div style='font-size:0.75rem; color:#666;'>流向: <b>{d['flow']:+.1f}M</b></div></div>", unsafe_allow_html=True)

st.divider()

l_col, r_col = st.columns([4.2, 1.3])
with l_col:
    if st.session_state.my_sectors:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                for s in [x for x in m_res if x['sector'] == s_name]:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.6, 4.4, 0.3])
                        with c1:
                            # --- 【修复核心】：找回并强化 TradingView 深度链接 ---
                            d_cl, rs_cl = ("green" if s['change'] >= 0 else "red"), ("#008000" if s['rs'] > 0 else "#FF0000")
                            st.markdown(f"<div style='line-height:1.2;'><div style='font-size:1.8rem; font-weight:800;'>{s['ticker']}</div><div style='margin:5px 0;'>{s['spark']}</div><div style='display:flex; align-items:baseline; gap:8px;'><span style='font-size:1.5rem; font-weight:700;'>${s['price']:.2f}</span><span style='color:{d_cl}; font-weight:bold;'>{s['change']:+.2f}%</span></div><div style='font-size:0.85rem; margin-top:5px; color:{rs_cl}; font-weight:600;'>相对 {s['bench']}: {s['rs']:+.2f}%</div></div>", unsafe_allow_html=True)
                            
                            # 点击此处直接跳转到 TradingView 的 K 线图
                            st.link_button(f"📊 {s['ticker']} 深度 K 线", f"https://www.tradingview.com/symbols/{s['ticker']}/", use_container_width=True)
                            
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = s['history'].iloc[idx], s['history'].iloc[idx-1]
                                    d_chg = ((cur['Close']-pre['Close'])/pre['Close'])*100
                                    border = "2px solid #FFD700" if d_chg > (b_res.get(s['bench'], {"chg":0})['chg']/5) else "1px solid #eee"
                                    st.markdown(f"<div style='text-align:center; background:rgba(0,0,0,0.02); border:{border}; border-radius:6px; padding:5px;'><div style='font-size:0.7rem; color:gray;'>{s['history'].index[idx].strftime('%m-%d')}</div><div style='color:{'green' if d_chg>=0 else 'red'}; font-weight:bold; font-size:1.0rem;'>{d_chg:+.1f}%</div><div style='font-size:0.8rem;'>${cur['Close']:.1f}</div></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px; padding:8px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed #ccc; font-size:0.9rem;'>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("📖 深度投资逻辑"): st.write(st.session_state.my_notes.get(s['ticker'], "暂无逻辑内容。"))
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"): st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力排行")
    b_tabs = st.tabs(["今日", "5日", "144日", "288日"])
    m_keys = ['change', 'total_5d', 'total_144d', 'total_288d']
    for idx, key in enumerate(m_keys):
        with b_tabs[idx]:
            sorted_res = sorted(m_res, key=lambda x: x[key], reverse=True)
            for i, item in enumerate(sorted_res):
                st.markdown(f"<div style='display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #f0f0f0;'><span>{i+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[key]>=0 else 'red'}; font-weight:bold;'>{item[key]:+.1f}%</span></div>", unsafe_allow_html=True)