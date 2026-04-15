import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 ---
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
st_autorefresh(interval=300000, key="data_pull") 
st.title("🏛️ 智能行情监控终端 (全真实数据版)")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg["notes"]

# --- 3. 核心修复：确保获取的是标量数值 (Scalar) ---
@st.cache_data(ttl=300)
def get_real_sector_radar():
    etfs = {
        "半导体 (SOXX)": "SOXX", "人工智能 (AIQ)": "AIQ", 
        "金融 (XLF)": "XLF", "能源 (XLE)": "XLE",
        "医疗 (XLV)": "XLV", "科技 (QQQ)": "QQQ"
    }
    results = []
    for name, symbol in etfs.items():
        try:
            # 下载数据并强制展平列名
            data = yf.download(symbol, period="2d", interval="15m", progress=False)
            if data.columns.nlevels > 1:
                data.columns = data.columns.get_level_values(0)
                
            if len(data) > 1:
                # 确保计算结果转换为标量 float
                raw_flow = ((data['Close'] - data['Open']) * data['Volume']).sum()
                flow_val = float(raw_flow.iloc[0]) if isinstance(raw_flow, pd.Series) else float(raw_flow)
                
                # 计算涨跌幅
                c_last = float(data['Close'].iloc[-1])
                c_first = float(data['Close'].iloc[0])
                chg_val = ((c_last - c_first) / c_first) * 100
                
                results.append({"name": name, "flow": flow_val / 1e6, "chg": chg_val})
        except Exception as e:
            results.append({"name": name, "flow": 0.0, "chg": 0.0})
    return results

@st.cache_data(ttl=600)
def fetch_stock_full_data(ticker, bench_chg):
    try:
        t_real = ticker.upper()
        if ticker.isdigit():
            t_real = f"{ticker}.SS" if ticker.startswith('6') else f"{ticker}.SZ"
            
        obj = yf.Ticker(t_real)
        hist = obj.history(period="2y") 
        if hist.empty: return None
        
        # 强制展平可能存在的多级列
        if hist.columns.nlevels > 1:
            hist.columns = hist.columns.get_level_values(0)

        latest_c = float(hist['Close'].iloc[-1])
        prev_c = float(hist['Close'].iloc[-2])
        today_chg = ((latest_c - prev_c) / prev_c) * 100
        
        history_5d = []
        subset_5d = hist.tail(6)
        for i in range(1, len(subset_5d)):
            c = float(subset_5d['Close'].iloc[i])
            p = float(subset_5d['Close'].iloc[i-1])
            v = float(subset_5d['Volume'].iloc[i])
            history_5d.append({
                "date": subset_5d.index[i].strftime("%m-%d"),
                "s_chg": ((c - p) / p) * 100,
                "b_chg": float(bench_chg) / 5,
                "close": c,
                "vol": (c * v) / 1e6
            })
            
        return {
            "ticker": ticker, "price": latest_c, "change": today_chg,
            "rs": today_chg - (float(bench_chg) / 5),
            "history": history_5d,
            "total_5d": ((latest_c - float(subset_5d['Open'].iloc[0])) / float(subset_5d['Open'].iloc[0])) * 100,
            "total_144d": ((latest_c - float(hist['Open'].iloc[-144])) / float(hist['Open'].iloc[-144])) * 100 if len(hist) >= 144 else 0,
            "total_288d": ((latest_c - float(hist['Open'].iloc[-288])) / float(hist['Open'].iloc[-288])) * 100 if len(hist) >= 288 else 0,
            "desc": st.session_state.my_notes.get(ticker.upper(), "暂无介绍。")
        }
    except: return None

# --- 后续界面渲染逻辑保持不变 ---
# (请沿用你之前的界面渲染代码，注意把 master_data 排序部分也加上 float 转换以防万一)