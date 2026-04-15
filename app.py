import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. 数据持久化 ---
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
st.set_page_config(page_title="2026 深度行情终端", layout="wide")
st_autorefresh(interval=300000, key="spark_refresh") 
st.title("🏛️ 智能行情监控终端 (分时预览增强版)")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg["notes"]

# --- 3. 【核心新增】：SVG 分时曲线引擎 ---
def get_sparkline_svg(prices, color="green", width=140, height=40):
    """根据价格序列生成轻量级 SVG 曲线"""
    if len(prices) < 2: return ""
    
    # 数据归一化（将价格映射到画布坐标）
    p_min, p_max = min(prices), max(prices)
    if p_max == p_min: p_max += 0.01
    
    # 计算点位坐标
    pts = []
    for i, p in enumerate(prices):
        x = (i / (len(prices) - 1)) * width
        y = height - ((p - p_min) / (p_max - p_min) * height)
        pts.append(f"{x:.1f},{y:.1f}")
    
    path_data = " ".join(pts)
    
    # 颜色半透明阴影填充
    return f"""
    <svg width="{width}" height="{height}" style="margin-top:5px;">
        <path d="M 0,{height} L {path_data} L {width},{height} Z" fill="{color}" fill-opacity="0.1" stroke="none" />
        <polyline points="{path_data}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    """

# --- 4. 真实数据引擎 ---
def clean_df(df):
    if df is None or df.empty: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    return df

@st.cache_data(ttl=300)
def get_real_sector_radar():
    etfs = {"半导体(SOXX)": "SOXX", "人工智能(AIQ)": "AIQ", "金融(XLF)": "XLF", "能源(XLE)": "XLE", "中概(KWEB)": "KWEB", "科技(QQQ)": "QQQ"}
    results = []
    for name, symbol in etfs.items():
        try:
            data = clean_df(yf.download(symbol, period="2d", interval="15m", progress=False))
            if data is not None and len(data) > 1:
                c_last, c_first = float(data['Close'].iloc[-1]), float(data['Close'].iloc[0])
                results.append({"name": name, "chg": ((c_last - c_first) / c_first) * 100, "flow": (c_last - c_first) * float(data['Volume'].sum()) / 1e10})
            else: results.append({"name": name, "chg": 0.0, "flow": 0.0})
        except: results.append({"name": name, "chg": 0.0, "flow": 0.0})
    return results

@st.cache_data(ttl=600)
def fetch_stock_full_data(ticker, bench_chg):
    try:
        t_real = ticker.upper()
        if ticker.isdigit(): t_real = f"{ticker}.SS" if ticker.startswith('6') else f"{ticker}.SZ"
        obj = yf.Ticker(t_real)
        
        # 抓取2年日线 (大周期)
        hist = clean_df(obj.history(period="2y"))
        # 抓取今日分时 (分时预览)
        intraday = clean_df(obj.history(period="1d", interval="15m"))
        
        if hist is None or hist.empty: return None
        
        latest_c = float(hist['Close'].iloc[-1])
        prev_c = float(hist['Close'].iloc[-2])
        today_chg = ((latest_c - prev_c) / prev_c) * 100
        
        # 生成分时曲线数据
        spark_prices = intraday['Close'].tolist() if (intraday is not None and not intraday.empty) else [latest_c] * 10
        spark_color = "green" if today_chg >= 0 else "red"
        spark_svg = get_sparkline_svg(spark_prices, color=spark_color)

        history_5d = []
        subset_5d = hist.tail(6)
        for i in range(1, len(subset_5d)):
            c, p = float(subset_5d['Close'].iloc[i]), float(subset_5d['Close'].iloc[i-1])
            history_5d.append({"date": subset_5d.index[i].strftime("%m-%d"), "s_chg": ((c - p) / p) * 100, "b_chg": float(bench_chg)/5, "close": c, "vol": (c * float(subset_5d['Volume'].iloc[i])) / 1e6})
            
        return {
            "ticker": ticker, "price": latest_c, "change": today_chg, "rs": today_chg - (float(bench_chg)/5), "history": history_5d,
            "spark_svg": spark_svg, # 存入 SVG
            "total_5d": ((latest_c - float(hist['Close'].iloc[-6])) / float(hist['Close'].iloc[-6])) * 100,
            "total_144d": ((latest_c - float(hist['Close'].iloc[-145])) / float(hist['Close'].iloc[-145])) * 100 if len(hist) >= 145 else 0,
            "total_288d": ((latest_c - float(hist['Close'].iloc[0])) / float(hist['Close'].iloc[0])) * 100 if len(hist) >= 288 else 0,
            "desc": st.session_state.my_notes.get(ticker.upper(), "💡 暂无笔记。")
        }
    except: return None

# --- 5. 渲染逻辑 (与之前版本保持一致，微调 Column 比例) ---
with st.sidebar:
    st.header("⚙️ 终端控制")
    nt = st.text_input("添加股票代码")
    if st.button("确定添加"):
        first_s = list(st.session_state.my_sectors.keys())[0]
        st.session_state.my_sectors[first_s].append(nt.upper()); save_config(); st.rerun()
    st.divider()
    all_edit = [t for ts in st.session_state.my_sectors.values() for t in ts]
    edit_t = st.selectbox("编辑笔记", options=list(set(all_edit)))
    note = st.text_area("核心逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=100)
    if st.button("保存笔记"): st.session_state.my_notes[edit_t] = note; save_config(); st.success("已保存")

with st.status("正在刷新 288 日周期 & 分时预览...", expanded=False) as status:
    sectors_data = get_real_sector_radar()
    master_data = []
    for sec_name, tickers in st.session_state.my_sectors.items():
        for t in tickers:
            d = fetch_stock_full_data(t, sectors_data[0]['chg'])
            if d: d['sector'] = sec_name; master_data.append(d)
    status.update(label="行情数据就绪", state="complete")

# 顶部雷达渲染
s_cols = st.columns(6)
for idx, sec in enumerate(sectors_data):
    with s_cols[idx]:
        color = "green" if sec['chg'] >= 0 else "red"
        st.markdown(f"<div style='border:1px solid #ddd; padding:10px; border-radius:10px; text-align:center; background:white;'><div style='font-size:0.8rem; color:#666;'>{sec['name']}</div><div style='font-size:1.1rem; color:{color}; font-weight:900;'>{sec['chg']:+.2f}%</div></div>", unsafe_allow_html=True)

st.divider()

l_col, r_col = st.columns([4.2, 1.3])
with l_col:
    tabs = st.tabs(list(st.session_state.my_sectors.keys()))
    for i, s_name in enumerate(st.session_state.my_sectors.keys()):
        with tabs[i]:
            stocks = [s for s in master_data if s['sector'] == s_name]
            for s in stocks:
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1.5, 0.6, 4.0, 0.3]) # 微调第一列宽度
                    with c1:
                        # --- 【视觉升级】：加入分时预览曲线 ---
                        st.markdown(f"""
                        <div style='margin-bottom:-5px;'>
                            <div style='font-size:1.7rem; font-weight:800;'>{s['ticker']}</div>
                            {s['spark_svg']} 
                        </div>
                        """, unsafe_allow_html=True)
                        st.metric(label="", value=f"${s['price']:.2f}", delta=f"{s['change']:.2f}%")
                        rs_color = "green" if s['rs'] > 0 else "red"
                        st.markdown(f"<span style='color:{rs_color}; font-weight:bold; font-size:0.9rem;'>对比板块: {s['rs']:+.2f}%</span>", unsafe_allow_html=True)
                    
                    with c2: st.write(""); st.write("**🗓️ 5日细节**")
                    with c3:
                        h_cols = st.columns(5)
                        for idx, day in enumerate(s["history"]):
                            with h_cols[idx]:
                                cl = "green" if day['s_chg'] >= 0 else "red"
                                border = "2px solid #FFD700" if day['s_chg'] > day['b_chg'] else "1px solid #eee"
                                st.markdown(f"<div style='background-color:rgba(0,0,0,0.02); border:{border}; padding:8px 4px; border-radius:8px; text-align:center;'><div style='font-size:0.75rem; color:gray;'>{day['date']}</div><div style='color:{cl}; font-weight:900; font-size:1.1rem;'>{day['s_chg']:+.1f}%</div><div style='font-size:0.85rem; font-weight:bold;'>${day['close']:.1f}</div></div>", unsafe_allow_html=True)
                        st.markdown(f"<div style='margin-top:10px; padding:10px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed gray; display:flex; justify-content:space-between; align-items:center;'><span>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></span><a href='https://tw.tradingview.com/chart/?symbol={s['ticker']}' target='_blank' style='text-decoration:none; background:#2962FF; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:bold;'>📈 K线图表</a></div>", unsafe_allow_html=True)
                        with st.expander("📖 深度投资逻辑"): st.write(s['desc'])
                    with c4:
                        if st.button("🗑️", key=f"del_{s['ticker']}"): st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力排行")
    b_tabs = st.tabs(["今日", "5日", "144日", "288日"])
    def render_rank(data, key):
        sd = sorted(data, key=lambda x: x[key], reverse=True)
        for idx, item in enumerate(sd):
            st.markdown(f"<div style='display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #eee;'><span>{idx+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[key]>=0 else 'red'}; font-weight:bold;'>{item[key]:+.2f}%</span></div>", unsafe_allow_html=True)
    if master_data:
        for i, k in enumerate(['change', 'total_5d', 'total_144d', 'total_288d']):
            with b_tabs[i]: render_rank(master_data, k)