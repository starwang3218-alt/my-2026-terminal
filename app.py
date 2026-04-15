import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 (支持板块与基准绑定) ---
CONFIG_FILE = "my_terminal_config_2026.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    # 初始默认值：板块名 -> [股票列表], 以及板块名 -> 基准ETF
    return {
        "sectors": {
            "光通信": ["CRDO", "AAOI"], 
            "AI算力": ["NVDA", "AMD"],
            "工业机械": ["MKSI"] 
        },
        "benchmarks": {
            "光通信": "SOXX",
            "AI算力": "SOXX",
            "工业机械": "XLI",  # 对应你发现的工业板块
            "稀土": "REMX",
            "核能": "XLU"
        },
        "notes": {}
    }

def save_config():
    cfg = {
        "sectors": st.session_state.my_sectors, 
        "benchmarks": st.session_state.my_benchmarks,
        "notes": st.session_state.my_notes
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 初始化 ---
st.set_page_config(page_title="2026 战略终端", layout="wide")
st_autorefresh(interval=300000, key="custom_sector_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_benchmarks = cfg.get("benchmarks", {})
    st.session_state.my_notes = cfg.get("notes", {})

# --- 3. 核心引擎 (SVG 分时曲线) ---
def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    w, h = 160, 40
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = [f"{(i/(len(prices)-1))*w:.1f},{h-((p-p_min)/(p_max-p_min)*h):.1f}" for i,p in enumerate(prices)]
    path_data = " ".join(pts)
    return f'<svg width="{w}" height="{h}" style="display:block;margin:5px 0;"><path d="M 0,{h} L {path_data} L {w},{h} Z" fill="{color}" fill-opacity="0.1" stroke="none"/><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

# --- 4. 数据抓取 (动态锚定逻辑) ---
@st.cache_data(ttl=300)
def fetch_all_data(sector_config, benchmark_config):
    # 抓取所有需要的基准数据
    bench_results = {}
    all_needed_bench = set(benchmark_config.values())
    # 默认加上几个核心雷达
    all_needed_bench.update(["SOXX", "QQQ", "XLI", "KWEB", "REMX"])
    
    for b_sym in all_needed_bench:
        try:
            d = yf.download(b_sym, period="2d", interval="15m", progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            c_last, c_first = float(d['Close'].iloc[-1]), float(d['Close'].iloc[0])
            bench_results[b_sym] = {"chg": ((c_last-c_first)/c_first)*100, "flow": (c_last-c_first)*float(d['Volume'].sum())/1e10}
        except: bench_results[b_sym] = {"chg": 0.0, "flow": 0.0}

    m_data = []
    for sec_name, tickers in sector_config.items():
        b_sym = benchmark_config.get(sec_name, "SPY")
        b_chg = bench_results.get(b_sym, {"chg": 0.0})["chg"]
        
        for t in tickers:
            try:
                obj = yf.Ticker(t)
                h = obj.history(period="2y")
                intra = obj.history(period="1d", interval="15m")
                if isinstance(h.columns, pd.MultiIndex): h.columns = h.columns.get_level_values(0)
                if isinstance(intra.columns, pd.MultiIndex): intra.columns = intra.columns.get_level_values(0)
                
                latest_c = float(h['Close'].iloc[-1])
                today_chg = ((latest_c - float(h['Close'].iloc[-2]))/float(h['Close'].iloc[-2]))*100
                
                m_data.append({
                    "ticker": t, "sector": sec_name, "bench": b_sym, "price": latest_c, "change": today_chg,
                    "rs": today_chg - b_chg,
                    "spark": get_sparkline_svg(intra['Close'].tolist(), "green" if today_chg>=0 else "red"),
                    "history": h.tail(6),
                    "total_5d": ((latest_c - h['Close'].iloc[-6])/h['Close'].iloc[-6])*100,
                    "total_144d": ((latest_c - h['Close'].iloc[-145])/h['Close'].iloc[-145])*100 if len(h)>=145 else 0,
                    "total_288d": ((latest_c - h['Close'].iloc[0])/h['Close'].iloc[0])*100 if len(h)>=288 else 0
                })
            except: pass
    return bench_results, m_data

# --- 5. 侧边栏：全自定义板块管理 ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    if st.button("🔄 强制刷新行情", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.divider()
    with st.expander("📁 自定义板块与基准", expanded=False):
        new_s = st.text_input("新建板块名称 (如: 工业机械)")
        new_b = st.text_input("对标 ETF 代码 (如: XLI)")
        if st.button("立即创建"):
            if new_s and new_b:
                st.session_state.my_sectors[new_s] = []
                st.session_state.my_benchmarks[new_s] = new_b.upper()
                save_config(); st.rerun()
    
    st.subheader("➕ 添加个股")
    if st.session_state.my_sectors:
        target_s = st.selectbox("选择所属板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("股票代码 (如: MKSI)")
        if st.button("加入监控"):
            if nt:
                st.session_state.my_sectors[target_s].append(nt.upper())
                save_config(); st.rerun()

    st.divider()
    st.subheader("📝 投资笔记")
    all_ts = [t for ts in st.session_state.my_sectors.values() for t in ts]
    if all_ts:
        edit_t = st.selectbox("选择股票", options=list(set(all_ts)))
        note = st.text_area("长线逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=150)
        if st.button("保存笔记"):
            st.session_state.my_notes[edit_t] = note; save_config(); st.success("已保存")

# --- 6. 渲染界面 ---
st.write("### 🏛️ 战略资产监控终端")
with st.spinner("同步实时数据与动态基准..."):
    b_res, m_res = fetch_all_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

# 顶部雷达（显示核心 ETF 的资金流）
st.subheader("📡 核心板块资金雷达")
r_cols = st.columns(6)
core_etfs = ["SOXX", "AIQ", "XLI", "XLU", "KWEB", "REMX"]
for i, sym in enumerate(core_etfs):
    with r_cols[i]:
        data = b_res.get(sym, {"chg": 0.0, "flow": 0.0})
        color = "green" if data['chg'] >= 0 else "red"
        st.markdown(f"<div style='text-align:center; border:1px solid #eee; border-radius:10px; padding:8px; background:white;'><div style='font-size:0.75rem; color:gray;'>{sym}</div><div style='font-size:1.1rem; color:{color}; font-weight:900;'>{data['chg']:+.2f}%</div><div style='font-size:0.7rem; color:#999;'>流向:{data['flow']:+.1f}M</div></div>", unsafe_allow_html=True)

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
                            d_cl = "green" if s['change'] >= 0 else "red"
                            rs_cl = "#008000" if s['rs'] > 0 else "#FF0000"
                            st.markdown(f"""
                            <div style="line-height:1.2;">
                                <div style="font-size:1.8rem; font-weight:800;">{s['ticker']}</div>
                                <div style="margin:5px 0;">{s['spark']}</div>
                                <div style="display:flex; align-items:baseline; gap:8px;">
                                    <span style="font-size:1.5rem; font-weight:700;">${s['price']:.2f}</span>
                                    <span style="color:{d_cl}; font-weight:bold;">{s['change']:+.2f}%</span>
                                </div>
                                <div style="font-size:0.85rem; margin-top:5px; color:{rs_cl}; font-weight:600;">相对 {s['bench']}: {s['rs']:+.2f}%</div>
                            </div>""", unsafe_allow_html=True)
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = s['history'].iloc[idx], s['history'].iloc[idx-1]
                                    d_chg = ((cur['Close']-pre['Close'])/pre['Close'])*100
                                    border = "2px solid #FFD700" if d_chg > (b_res.get(s['bench'], {"chg":0})['chg']/5) else "1px solid #eee"
                                    st.markdown(f"<div style='text-align:center; background:rgba(0,0,0,0.02); border:{border}; border-radius:6px; padding:5px;'><div style='font-size:0.7rem; color:gray;'>{s['history'].index[idx].strftime('%m-%d')}</div><div style='color:{'green' if d_chg>=0 else 'red'}; font-weight:bold; font-size:1.0rem;'>{d_chg:+.1f}%</div><div style='font-size:0.8rem;'>${cur['Close']:.1f}</div></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px; padding:8px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed #ccc; font-size:0.9rem;'>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("📖 投资笔记"): st.write(st.session_state.my_notes.get(s['ticker'], "暂无笔记内容。"))
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力榜")
    b_tab_list = st.tabs(["5日", "144日", "288日"])
    keys = ['total_5d', 'total_144d', 'total_288d']
    for i, k in enumerate(keys):
        with b_tab_list[i]:
            sorted_m = sorted(m_res, key=lambda x: x[k], reverse=True)
            for idx, item in enumerate(sorted_m):
                st.markdown(f"<div style='display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #f0f0f0;'><span>{idx+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[k]>=0 else 'red'};'>{item[k]:+.1f}%</span></div>", unsafe_allow_html=True)