import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 ---
CONFIG_FILE = "my_terminal_config_2026.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "AI/算力核心": ["NVDA", "AVGO", "APP", "VICR", "CRDO"],
            "军工/航电": ["BBAI", "ISSC", "LOAR"],
            "量子/康波底座": ["IONQ", "XNDU"],
            "周期/资产": ["MP", "AMPY", "KE"]
        },
        "benchmarks": {
            "AI/算力核心": "SOXX", "军工/航电": "ITA", "量子/康波底座": "ARKK", "周期/资产": "XOP"
        },
        "notes": {}
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 初始化 ---
st.set_page_config(page_title="2026 战略终端", layout="wide")
st_autorefresh(interval=300000, key="global_fixed_refresh")

RADAR_NAMES = {"SOXX": "半导体/芯片", "AIQ": "人工智能/AI", "XLI": "工业/机械", "XLU": "核能/公用事业", "KWEB": "中概互联", "REMX": "稀土/战略金属"}

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg.get("benchmarks", {}), cfg.get("notes", {})

# --- 3. 核心工具 ---
def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    w, h = 160, 40
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = [f"{(i/(len(prices)-1))*w:.1f},{h-((p-p_min)/(p_max-p_min)*h):.1f}" for i,p in enumerate(prices)]
    path_data = " ".join(pts)
    return f'<svg width="{w}" height="{h}" style="display:block;margin:5px 0;"><path d="M 0,{h} L {path_data} L {w},{h} Z" fill="{color}" fill-opacity="0.1" stroke="none"/><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

@st.cache_data(ttl=300)
def fetch_terminal_data(sector_cfg, bench_cfg):
    bench_results = {}
    core_radar = ["SOXX", "AIQ", "XLI", "XLU", "KWEB", "REMX"]
    all_needed_bench = set(core_radar) | set(bench_cfg.values())
    
    for b_sym in all_needed_bench:
        try:
            d = yf.download(b_sym, period="2d", interval="15m", progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            c_last = float(d['Close'].iloc[-1])
            c_first = float(d['Close'].iloc[0])
            bench_results[b_sym] = {"chg": ((c_last-c_first)/c_first)*100}
        except: bench_results[b_sym] = {"chg": 0.0}
    
    m_data = []
    sector_strength = {} # 用于计算板块强度
    
    for sec_name, tickers in sector_cfg.items():
        b_sym = bench_cfg.get(sec_name, "SPY")
        b_chg = bench_results.get(b_sym, {"chg": 0.0})["chg"]
        sec_chgs = []
        
        for t in tickers:
            try:
                obj = yf.Ticker(t)
                h = obj.history(period="2y")
                intra = obj.history(period="1d", interval="15m")
                if isinstance(h.columns, pd.MultiIndex): h.columns = h.columns.get_level_values(0)
                if isinstance(intra.columns, pd.MultiIndex): intra.columns = intra.columns.get_level_values(0)
                
                latest_c = float(h['Close'].iloc[-1])
                prev_c = float(h['Close'].iloc[-2])
                today_chg = ((latest_c - prev_c)/prev_c)*100
                sec_chgs.append(today_chg)
                
                m_data.append({
                    "ticker": t, "sector": sec_name, "bench": b_sym, "price": latest_c, "change": today_chg, "rs": today_chg - b_chg,
                    "spark": get_sparkline_svg(intra['Close'].tolist(), "green" if today_chg>=0 else "red"),
                    "history": h.tail(6), 
                    "total_5d": ((latest_c - h['Close'].iloc[-6])/h['Close'].iloc[-6])*100,
                    "total_144d": ((latest_c - h['Close'].iloc[-145])/h['Close'].iloc[-145])*100 if len(h)>=145 else 0,
                    "total_288d": ((latest_c - h['Close'].iloc[0])/h['Close'].iloc[0])*100 if len(h)>=288 else 0
                })
            except: pass
        
        # 计算该板块的平均表现
        if sec_chgs:
            avg_chg = sum(sec_chgs) / len(sec_chgs)
            sector_strength[sec_name] = {"avg_chg": avg_chg, "alpha": avg_chg - b_chg}
            
    return bench_results, m_data, sector_strength

# --- 4. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    if st.button("🔄 刷新数据", type="primary", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.divider()
    
    with st.expander("📁 板块管理"):
        c_sec, c_ben = st.text_input("新建板块"), st.text_input("对标 ETF")
        if st.button("创建板块"):
            if c_sec and c_ben: st.session_state.my_sectors[c_sec] = []; st.session_state.my_benchmarks[c_sec] = c_ben.upper(); save_config(); st.rerun()
        st.divider()
        if st.session_state.my_sectors:
            target_sec = st.selectbox("选择板块", list(st.session_state.my_sectors.keys()))
            new_ticker = st.text_input("添加股票")
            if st.button("确认加入"):
                if new_ticker: st.session_state.my_sectors[target_sec].append(new_ticker.upper()); save_config(); st.rerun()

    st.divider()
    st.subheader("📝 投资笔记")
    all_t = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    if all_t:
        e_t = st.selectbox("选择个股", all_t)
        n_n = st.text_area("288日博弈逻辑", value=st.session_state.my_notes.get(e_t, ""), height=150)
        if st.button("💾 保存笔记"):
            st.session_state.my_notes[e_t] = n_n; save_config(); st.success("已保存")

# --- 5. 主渲染 ---
st.write("### 🏛️ 战略资产监控终端 (2026)")
with st.status("正在同步实时数据...", expanded=False):
    b_res, m_res, s_strength = fetch_terminal_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

# 顶部雷达
r_cols = st.columns(6)
for idx, sym in enumerate(["SOXX", "AIQ", "XLI", "XLU", "KWEB", "REMX"]):
    with r_cols[idx]:
        d = b_res.get(sym, {"chg": 0.0})
        st.markdown(f"<div style='text-align:center; border:1px solid #eee; border-radius:10px; padding:8px;'><div style='font-size:0.8rem; font-weight:bold;'>{RADAR_NAMES[sym]}</div><div style='font-size:1rem; color:{'green' if d['chg']>=0 else 'red'}; font-weight:700;'>{d['chg']:+.2f}%</div></div>", unsafe_allow_html=True)

# 🌟 板块强度雷达 (找回的部分)
st.subheader("📡 板块战力雷达 (Sector Alpha)")
s_cols = st.columns(len(s_strength) if s_strength else 1)
for idx, (name, val) in enumerate(s_strength.items()):
    with s_cols[idx]:
        st.markdown(f"<div style='text-align:center; background:#f8f9fa; border-radius:10px; padding:10px; border-left:5px solid {'green' if val['alpha']>=0 else 'red'};'><div style='font-size:0.85rem; font-weight:bold;'>{name}</div><div style='font-size:1.1rem; color:{'green' if val['avg_chg']>=0 else 'red'}; font-weight:900;'>{val['avg_chg']:+.2f}%</div><div style='font-size:0.75rem; color:gray;'>Alpha: {val['alpha']:+.2f}%</div></div>", unsafe_allow_html=True)

st.divider()

l_col, r_col = st.columns([4.2, 1.3])
with l_col:
    if st.session_state.my_sectors:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                for s in [x for x in m_res if x['sector'] == s_name]:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.6, 4.4, 0.4])
                        with c1:
                            st.markdown(f"<div style='line-height:1.2;'><div style='font-size:1.6rem; font-weight:800;'>{s['ticker']}</div><div style='margin:5px 0;'>{s['spark']}</div><div style='font-size:1.3rem; font-weight:700;'>${s['price']:.2f}</div><div style='color:{'green' if s['change']>=0 else 'red'}; font-weight:bold;'>{s['change']:+.2f}%</div></div>", unsafe_allow_html=True)
                            st.link_button("📈 实战图表", f"https://www.tradingview.com/chart/MdN4tzco/?symbol={s['ticker']}")
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = s['history'].iloc[idx], s['history'].iloc[idx-1]
                                    d_chg = ((cur['Close']-pre['Close'])/pre['Close'])*100
                                    st.markdown(f"<div style='text-align:center; background:rgba(0,0,0,0.02); border-radius:5px; padding:3px;'><div style='font-size:0.7rem; color:gray;'>{s['history'].index[idx].strftime('%m-%d')}</div><div style='color:{'green' if d_chg>=0 else 'red'}; font-weight:bold;'>{d_chg:+.1f}%</div></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px; padding:6px; background:rgba(0,0,0,0.03); border-radius:6px; font-size:0.85rem;'>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("📖 笔记逻辑"):
                                st.write(st.session_state.my_notes.get(s['ticker'], "暂无笔记。"))
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
                st.markdown(f"<div style='display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid #f9f9f9; font-size:0.9rem;'><span>{i+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[key]>=0 else 'red'}; font-weight:bold;'>{item[key]:+.1f}%</span></div>", unsafe_allow_html=True)