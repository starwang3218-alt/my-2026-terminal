import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. 数据持久化 ---
CONFIG_FILE = "my_terminal_config_2026.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"sectors": {"光通信": ["CRDO", "AAOI"], "AI算力": ["NVDA", "AMD"]}, "notes": {}}

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 页面配置 ---
st.set_page_config(page_title="2026 真实数据终端", layout="wide")
st_autorefresh(interval=300000, key="data_pull") # 每5分钟更新一次真实数据
st.title("🏛️ 智能行情监控终端 (全真实数据版)")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg["notes"]

# --- 3. 真实数据引擎：板块 & 个股 ---
def fix_ticker(ticker):
    """自动修正 A 股代码后缀"""
    if ticker.isdigit():
        return f"{ticker}.SS" if ticker.startswith('6') else f"{ticker}.SZ"
    return ticker.upper()

@st.cache_data(ttl=300)
def get_real_sector_radar():
    """计算 6 大板块 ETF 的真实资金流向 (简易 Money Flow 模型)"""
    etfs = {
        "半导体 (SOXX)": "SOXX", "人工智能 (AIQ)": "AIQ", 
        "金融 (XLF)": "XLF", "能源 (XLE)": "XLE",
        "医疗 (XLV)": "XLV", "科技 (QQQ)": "QQQ"
    }
    results = []
    for name, symbol in etfs.items():
        try:
            data = yf.download(symbol, period="2d", interval="15m", progress=False)
            if len(data) > 1:
                # 资金流逻辑：(收盘价-开盘价) * 成交量
                flow = ((data['Close'] - data['Open']) * data['Volume']).sum() / 1e6
                chg = ((data['Close'].iloc[-1] - data['Close'].iloc[0]) / data['Close'].iloc[0]) * 100
                results.append({"name": name, "flow": flow, "chg": chg, "symbol": symbol})
        except:
            results.append({"name": name, "flow": 0, "chg": 0, "symbol": symbol})
    return results

@st.cache_data(ttl=600)
def fetch_stock_full_data(ticker, bench_chg):
    """抓取个股真实历史，计算 5/144/288 周期"""
    try:
        t_real = fix_ticker(ticker)
        obj = yf.Ticker(t_real)
        hist = obj.history(period="2y") # 抓取2年数据确保 288 日计算
        if hist.empty: return None
        
        latest = hist.iloc[-1]
        prev = hist.iloc[-2]
        today_chg = ((latest['Close'] - prev['Close']) / prev['Close']) * 100
        
        # 5日细节
        history_5d = []
        subset_5d = hist.tail(6)
        for i in range(1, len(subset_5d)):
            c, p = subset_5d.iloc[i], subset_5d.iloc[i-1]
            history_5d.append({
                "date": subset_5d.index[i].strftime("%m-%d"),
                "s_chg": ((c['Close'] - p['Close']) / p['Close']) * 100,
                "b_chg": bench_chg / 5, # 粗略对比
                "close": c['Close'],
                "vol": (c['Close'] * c['Volume']) / 1e6
            })
            
        return {
            "ticker": ticker, "price": latest['Close'], "change": today_chg,
            "rs": today_chg - (bench_chg / 5),
            "history": history_5d,
            "total_5d": ((latest['Close'] - subset_5d.iloc[0]['Open']) / subset_5d.iloc[0]['Open']) * 100,
            "total_144d": ((latest['Close'] - hist.iloc[-144]['Open']) / hist.iloc[-144]['Open']) * 100 if len(hist) >= 144 else 0,
            "total_288d": ((latest['Close'] - hist.iloc[-288]['Open']) / hist.iloc[-288]['Open']) * 100 if len(hist) >= 288 else 0,
            "desc": st.session_state.my_notes.get(ticker.upper(), "暂无介绍。")
        }
    except: return None

# --- 4. 界面渲染 ---
with st.spinner("正在从全球市场抓取真实数据..."):
    sectors_data = get_real_sector_radar()

# 顶部雷达
st.subheader("📡 美股核心板块资金流向 (真实数据)")
s_cols = st.columns(6)
for idx, sec in enumerate(sectors_data):
    with s_cols[idx]:
        color = "green" if sec['flow'] > 0 else "red"
        st.markdown(f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 10px; text-align: center; background: white;">
            <div style="font-size: 0.8rem; font-weight: bold; color: #555;">{sec['name']}</div>
            <div style="font-size: 1.1rem; color: {color}; font-weight: 900;">{sec['flow']:+.0f}M</div>
            <div style="font-size: 0.8rem; color: {color};">今日: {sec['chg']:+.2f}%</div>
        </div>""", unsafe_allow_html=True)

st.divider()

# 数据汇总
master_data = []
for sec_name, tickers in st.session_state.my_sectors.items():
    for t in tickers:
        d = fetch_stock_full_data(t, sectors_data[0]['chg'])
        if d:
            d['sector'] = sec_name
            master_data.append(d)

# 侧边栏与主界面布局 (保持之前的 UI 逻辑)
l_col, r_col = st.columns([4.2, 1.3])

with l_col:
    if not master_data: st.warning("未抓取到数据，请检查代码输入是否正确（如 NVDA）。")
    else:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                stocks = [s for s in master_data if s['sector'] == s_name]
                for s in stocks:
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([1.3, 0.6, 4.2, 0.3])
                        with c1:
                            st.markdown(f"<div style='font-size:1.7rem; font-weight:800;'>{s['ticker']}</div>", unsafe_allow_html=True)
                            st.metric(label="", value=f"${s['price']:.2f}", delta=f"{s['change']:.2f}%")
                            rs_color = "green" if s['rs'] > 0 else "red"
                            st.markdown(f"<span style='color:{rs_color}; font-weight:bold;'>对比板块: {s['rs']:+.2f}%</span>", unsafe_allow_html=True)
                        with c3:
                            h_cols = st.columns(5)
                            for idx, day in enumerate(s["history"]):
                                with h_cols[idx]:
                                    color = "green" if day['s_chg'] >= 0 else "red"
                                    border = "2px solid #FFD700" if day['s_chg'] > day['b_chg'] else "1px solid #eee"
                                    st.markdown(f"""<div style="background-color:rgba(0,0,0,0.02); border:{border}; padding:8px 4px; border-radius:8px; text-align:center;">
                                      <div style="font-size:0.75rem; color:gray;">{day['date']}</div>
                                      <div style="color:{color}; font-weight:900; font-size:1.1rem;">{day['s_chg']:+.1f}%</div>
                                      <div style="font-size:0.85rem; font-weight:bold;">${day['close']:.1f}</div>
                                    </div>""", unsafe_allow_html=True)
                            st.markdown(f"""<div style="margin-top:10px; padding:10px; background:rgba(0,0,0,0.03); border-radius:8px; border:1px dashed gray; display:flex; justify-content:space-between; align-items:center;">
                                <span>📊 5日总幅: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></span>
                                <a href="https://tw.tradingview.com/chart/?symbol={s['ticker']}" target="_blank" style="text-decoration:none; background:#2962FF; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:bold;">K线详情</a>
                            </div>""", unsafe_allow_html=True)
                            with st.expander("📖 逻辑笔记"): st.write(s['desc'])
                        with c4:
                            if st.button("🗑️", key=f"del_{s['ticker']}"): st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力排行")
    b_tabs = st.tabs(["今日", "5日", "144日", "288日"])
    def render_rank(data, key):
        sorted_data = sorted(data, key=lambda x: x[key], reverse=True)
        for idx, item in enumerate(sorted_data):
            st.markdown(f"<div style='display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #eee;'><span>{idx+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[key]>=0 else 'red'}; font-weight:bold;'>{item[key]:+.2f}%</span></div>", unsafe_allow_html=True)
    with b_tabs[0]: render_rank(master_data, 'change')
    with b_tabs[1]: render_rank(master_data, 'total_5d')
    with b_tabs[2]: render_rank(master_data, 'total_144d')
    with b_tabs[3]: render_rank(master_data, 'total_288d')

# 侧边栏
with st.sidebar:
    st.header("⚙️ 终端控制")
    nt = st.text_input("添加股票代码")
    if st.button("确定添加"):
        first_sec = list(st.session_state.my_sectors.keys())[0]
        st.session_state.my_sectors[first_sec].append(nt.upper()); save_config(); st.rerun()