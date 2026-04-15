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
    return {"sectors": {"光通信": ["CRDO", "AAOI"], "AI算力": ["NVDA", "AMD"]}, "notes": {}}

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 页面配置 ---
st.set_page_config(page_title="2026 战略终端", layout="wide")
st_autorefresh(interval=300000, key="final_fix_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg.get("notes", {})

# --- 3. 核心引擎：分时曲线 ---
def get_sparkline_svg(prices, color="green"):
    if not prices or len(prices) < 2: return ""
    width, height = 160, 40
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    pts = []
    for i, p in enumerate(prices):
        x = (i / (len(prices) - 1)) * width
        y = height - ((p - p_min) / (p_max - p_min) * height)
        pts.append(f"{x:.1f},{y:.1f}")
    path_data = " ".join(pts)
    # 修复：使用单引号定义属性，双引号定义路径，避免解析冲突
    return f'<svg width="{width}" height="{height}" style="display:block;margin:5px 0;"><path d="M 0,{height} L {path_data} L {width},{height} Z" fill="{color}" fill-opacity="0.1" stroke="none"/><polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

# --- 4. 真实数据抓取 ---
@st.cache_data(ttl=300)
def fetch_full_market_data(sector_config):
    etf_map = {"半导体(SOXX)": "SOXX", "人工智能(AIQ)": "AIQ", "科技(QQQ)": "QQQ", "金融(XLF)": "XLF", "能源(XLE)": "XLE", "中概(KWEB)": "KWEB"}
    radar_res = []
    for name, sym in etf_map.items():
        try:
            d = yf.download(sym, period="2d", interval="15m", progress=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
            c_last, c_first = float(d['Close'].iloc[-1]), float(d['Close'].iloc[0])
            flow = (c_last - c_first) * float(d['Volume'].sum()) / 1e10
            radar_res.append({"name": name, "chg": ((c_last - c_first)/c_first)*100, "flow": flow})
        except: radar_res.append({"name": name, "chg": 0.0, "flow": 0.0})
    
    m_data = []
    bench_chg = radar_res[0]['chg'] if radar_res else 0.0
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
    return radar_res, m_data

# --- 5. 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    if st.button("🔄 刷新全部行情", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    with st.expander("📁 板块管理"):
        ns = st.text_input("新建板块")
        if st.button("创建"):
            if ns: st.session_state.my_sectors[ns] = []; save_config(); st.rerun()
        ds = st.selectbox("删除板块", [""] + list(st.session_state.my_sectors.keys()))
        if st.button("执行删除"):
            if ds: del st.session_state.my_sectors[ds]; save_config(); st.rerun()
    st.subheader("➕ 添加资产")
    if st.session_state.my_sectors:
        t_sec = st.selectbox("目标板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("代码 (如: CRDO)")
        if st.button("确定加入"):
            if nt: st.session_state.my_sectors[t_sec].append(nt.upper()); save_config(); st.rerun()
    st.divider()
    st.subheader("📝 投资笔记")
    all_ts = [t for ts in st.session_state.my_sectors.values() for t in ts]
    if all_ts:
        edit_t = st.selectbox("选择股票", options=list(set(all_ts)))
        note_txt = st.text_area("核心逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=150)
        if st.button("保存笔记"):
            st.session_state.my_notes[edit_t] = note_txt; save_config(); st.success("已同步")

# --- 6. 界面渲染 ---
st.write("### 🏛️ 战略资产监控终端")
with st.status("正在同步实时数据...", expanded=False) as status:
    radar_data, m_res = fetch_full_market_data(st.session_state.my_sectors)
    status.update(label="数据已就绪", state="complete")

# --- 重新找回：板块资金雷达 ---
st.subheader("📡 板块资金流向监测")
r_cols = st.columns(6)
for idx, rd in enumerate(radar_data):
    with r_cols[idx]:
        color_val = "green" if rd['flow'] >= 0 else "red"
        st.markdown(f"""
        <div style="text-align:center; border:1px solid #eee; border-radius:10px; padding:8px; background:white;">
            <div style="font-size:0.75rem; color:gray;">{rd['name']}</div>
            <div style="font-size:1.1rem; color:{color_val}; font-weight:900;">{rd['flow']:+.1f}M</div>
            <div style="font-size:0.8rem; color:{color_val};">{rd['chg']:+.2f}%</div>
        </div>""", unsafe_allow_html=True)

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
                            # 修复引号冲突，先定义颜色变量
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
                                <div style="font-size:0.85rem; margin-top:5px; color:{rs_cl}; font-weight:600;">相对板块: {s['rs']:+.2f}%</div>
                            </div>""", unsafe_allow_html=True)
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = s['history'].iloc[idx], s['history'].iloc[idx-1]
                                    d_chg = ((cur['Close']-pre['Close'])/pre['Close'])*100
                                    box_color = "green" if d_chg >= 0 else "red"
                                    # 联动边框显示
                                    border_style = "2px solid #FFD700" if d_chg > (radar_data[0]['chg']/5) else "1px solid #eee"
                                    st.markdown(f"<div style='text-align:center; background:rgba(0,0,0,0.02); border:{border_style}; border-radius:6px; padding:5px;'><div style='font-size:0.7rem; color:gray;'>{s['history'].index[idx].strftime('%m-%d')}</div><div style='color:{box_color}; font-weight:bold; font-size:1.0rem;'>{d_chg:+.1f}%</div><div style='font-size:0.8rem;'>${cur['Close']:.1f}</div></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px; padding:8px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed #ccc; font-size:0.9rem;'>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("📖 投资笔记"): st.write(st.session_state.my_notes.get(s['ticker'], "暂无笔记内容。"))
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力榜")
    b_tab_list = st.tabs(["5日", "144日", "288日"])
    # 修复：预先定义键值，避免在 f-string 中进行复杂运算
    metric_keys = ['total_5d', 'total_144d', 'total_288d']
    for i, k in enumerate(metric_keys):
        with b_tab_list[i]:
            sorted_list = sorted(m_res, key=lambda x: x[k], reverse=True)
            for idx, item in enumerate(sorted_list):
                v_val = item[k]
                v_cl = "green" if v_val >= 0 else "red"
                st.markdown(f"<div style='display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #f0f0f0;'><span>{idx+1}. <b>{item['ticker']}</b></span><span style='color:{v_cl};'>{v_val:+.1f}%</span></div>", unsafe_allow_html=True)