import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置永久保存 ---
CONFIG_FILE = "my_terminal_config_2026.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    # 默认值 (建议在 GitHub Commit 前修改此处为你的核心标的)
    return {"sectors": {"光通信": ["CRDO", "AAOI"], "AI算力": ["NVDA", "AMD"]}, "notes": {}}

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 页面配置 ---
st.set_page_config(page_title="2026 战略终端", layout="wide")
st_autorefresh(interval=300000, key="global_prod_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg.get("notes", {})

# --- 3. 核心引擎：分时曲线 ---
def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    width, height = 160, 45
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = []
    for i, p in enumerate(prices):
        x = (i / (len(prices) - 1)) * width
        y = height - ((p - p_min) / (p_max - p_min) * height)
        pts.append(f"{x:.1f},{y:.1f}")
    path_data = " ".join(pts)
    return f'<svg width="{width}" height="{height}" style="display:block;margin:5px 0;"><path d="M 0,{height} L {path_data} L {width},{height} Z" fill="{color}" fill-opacity="0.1" stroke="none"/><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

# --- 4. 真实数据抓取 (含 6 大板块雷达) ---
@st.cache_data(ttl=300)
def fetch_full_market_data(sector_config):
    # A. 抓取 6 大板块雷达数据
    etf_map = {
        "半导体(SOXX)": "SOXX", "人工智能(AIQ)": "AIQ", 
        "科技(QQQ)": "QQQ", "金融(XLF)": "XLF", 
        "能源(XLE)": "XLE", "中概(KWEB)": "KWEB"
    }
    radar_results = []
    for name, sym in etf_map.items():
        try:
            d = yf.download(sym, period="2d", interval="15m", progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            c_last, c_first = float(d['Close'].iloc[-1]), float(d['Close'].iloc[0])
            # 资金流逻辑: (末价-初价) * 总成交量
            flow_val = (c_last - c_first) * float(d['Volume'].sum()) / 1e10
            radar_results.append({"name": name, "chg": ((c_last - c_first)/c_first)*100, "flow": flow_val})
        except:
            radar_results.append({"name": name, "chg": 0.0, "flow": 0.0})
    
    # B. 抓取个股联动数据
    m_data = []
    bench_chg = radar_results[0]['chg'] # 以 SOXX 为基准算相对强度
    for sec_name, tickers in sector_config.items():
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
                    "ticker": t, "sector": sec_name, "price": latest_c, "change": today_chg,
                    "rs": today_chg - (bench_chg/5),
                    "spark": get_sparkline_svg(intra['Close'].tolist(), "green" if today_chg>=0 else "red"),
                    "history": h.tail(6),
                    "total_5d": ((latest_c - h['Close'].iloc[-6])/h['Close'].iloc[-6])*100,
                    "total_144d": ((latest_c - h['Close'].iloc[-145])/h['Close'].iloc[-145])*100 if len(h)>=145 else 0,
                    "total_288d": ((latest_c - h['Close'].iloc[0])/h['Close'].iloc[0])*100 if len(h)>=288 else 0
                })
            except: pass
    return radar_results, m_data

# --- 5. 侧边栏控制区 ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    if st.button("🔄 立即刷新数据", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    
    with st.expander("📁 板块管理"):
        new_s = st.text_input("新建板块名称")
        if st.button("创建"):
            if new_s: st.session_state.my_sectors[new_s] = []; save_config(); st.rerun()
        ds = st.selectbox("删除板块", [""] + list(st.session_state.my_sectors.keys()))
        if st.button("确定删除"):
            if ds: del st.session_state.my_sectors[ds]; save_config(); st.rerun()

    st.subheader("➕ 添加资产")
    if st.session_state.my_sectors:
        t_sec = st.selectbox("目标板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("代码 (如: CRDO)")
        if st.button("确认加入"):
            if nt: st.session_state.my_sectors[t_sec].append(nt.upper()); save_config(); st.rerun()

    st.divider()
    st.subheader("📝 投资笔记")
    all_ts = [t for ts in st.session_state.my_sectors.values() for t in ts]
    if all_ts:
        edit_t = st.selectbox("选择股票", options=list(set(all_ts)))
        note = st.text_area("核心逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=150)
        if st.button("保存笔记"):
            st.session_state.my_notes[edit_t] = note; save_config(); st.success("已同步")

# --- 6. 界面渲染 ---
st.write("### 🏛️ 战略资产监控终端")
with st.status("同步全球行情 & 6 大板块雷达...", expanded=False) as status:
    radar_data, m_res = fetch_full_market_data(st.session_state.my_sectors)
    status.update(label="数据已更新", state="complete")

# --- 【找回的核心模块】：顶部 6 大板块资金雷达 ---
st.subheader("📡 板块资金流向监测 (Sector Net Flow)")
r_cols = st.columns(6)
for idx, rd in enumerate(radar_data):
    with r_cols[idx]:
        color = "green" if rd['flow'] >= 0 else "red"
        st.markdown(f"""
        <div style="text-align:center; border:1px solid #eee; border-radius:10px; padding:10px; background:white;">
            <div style="font-size:0.8rem; color:gray; font-weight:bold;">{rd['name']}</div>
            <div style="font-size:1.2rem; color:{color}; font-weight:900; margin:5px 0;">{rd['flow']:+.1f}M</div>
            <div style="font-size:0.85rem; color:{color};">强度: {rd['chg']:+.2f}%</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# 主内容与战力排行
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
                            st.markdown(f"""
                            <div style="line-height:1.2;">
                                <div style="font-size:1.8rem; font-weight:800;">{s['ticker']}</div>
                                <div style="margin:8px 0;">{s['spark']}</div>
                                <div style="display:flex; align-items:baseline; gap:8px;">
                                    <span style="font-size:1.4rem; font-weight:700;">${s['price']:.2f}</span>
                                    <span style="color:{'green' if s['change']>=0 else 'red'}; font-weight:bold;">{s['change']:+.2f}%</span>
                                </div>
                                <div style="font-size:0.85rem; margin-top:5px; color:{'#008000' if s['rs']>0 else '#FF0000'}; font-weight:600;">相对板块: {s['rs']:+.2f}%</div>
                            </div>""", unsafe_allow_html=True)
                        with c2:
                            h_cols = st.columns(5)
                            h_data = s['history']
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = h_data.iloc[idx], h_data.iloc[idx-1]
                                    day_chg = ((cur['Close']-pre['Close'])/pre['Close'])*100
                                    border = "2px solid #FFD700" if day_chg > (radar_data[0]['chg']/5) else "1px solid #eee"
                                    st.markdown(f"<div style='text-align:center; background:rgba(0,0,0,0.02); border:{border}; border-radius:6px; padding:5px;'><div style='font-size:0.7rem; color:gray;'>{h_data.index[idx].strftime('%m-%d')}</div><div style='color:{'green' if day_chg>=0 else 'red'}; font-weight:bold; font-size:1.0rem;'>{day_chg:+.1f}%</div><div style='font-size:0.8rem;'>${cur['Close']:.1f}</div></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px; padding:8px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed #ccc; font-size:0.9rem;'>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("📖 投资笔记"): st.write(st.session_state.my_notes.get(s['ticker'], "暂无笔记内容。"))
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力榜")
    b_tab = st.tabs(["5日", "144日", "288日"])
    keys = ['total_5d',