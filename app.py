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
st.set_page_config(page_title="2026 深度行情终端", layout="wide")
st_autorefresh(interval=300000, key="data_pull") 
st.title("🏛️ 智能行情监控终端 (实战稳定版)")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_notes = cfg["notes"]

# --- 3. 核心工具函数：强制数据展平 ---
def clean_df(df):
    """处理 yfinance 返回的 MultiIndex 问题，强制转为单级列名"""
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # 确保数据不是空的序列
    return df

# --- 4. 真实数据引擎 ---
@st.cache_data(ttl=300)
def get_real_sector_radar():
    etfs = {
        "半导体 (SOXX)": "SOXX", "人工智能 (AIQ)": "AIQ", 
        "金融 (XLF)": "XLF", "能源 (XLE)": "XLE",
        "医疗 (XLV)": "XLV", "科技 (QQQ)": "QQQ"
    }
    results = []
    # 使用单个 progress bar 提示进度
    for name, symbol in etfs.items():
        try:
            data = yf.download(symbol, period="2d", interval="15m", progress=False)
            data = clean_df(data)
            if data is not None and len(data) > 1:
                # 提取最后一行和第一行，强制转为 float
                c_last = float(data['Close'].iloc[-1])
                c_first = float(data['Close'].iloc[0])
                v_sum = float(data['Volume'].sum())
                
                flow_val = (c_last - c_first) * v_sum / 1e10 # 缩放处理
                chg_val = ((c_last - c_first) / c_first) * 100
                results.append({"name": name, "flow": flow_val, "chg": chg_val})
            else:
                results.append({"name": name, "flow": 0.0, "chg": 0.0})
        except:
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
        hist = clean_df(hist)
        
        if hist is None or hist.empty: return None

        latest_c = float(hist['Close'].iloc[-1])
        prev_c = float(hist['Close'].iloc[-2])
        today_chg = ((latest_c - prev_c) / prev_c) * 100
        
        history_5d = []
        subset_5d = hist.tail(6)
        for i in range(1, len(subset_5d)):
            c = float(subset_5d['Close'].iloc[i])
            p = float(subset_5d['Close'].iloc[i-1])
            history_5d.append({
                "date": subset_5d.index[i].strftime("%m-%d"),
                "s_chg": ((c - p) / p) * 100,
                "b_chg": float(bench_chg) / 5,
                "close": c
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

# --- 5. 界面渲染 ---
# 顶部雷达
with st.status("正在同步全球实时行情...", expanded=False) as status:
    st.write("获取板块资金雷达...")
    sectors_data = get_real_sector_radar()
    st.write("个股周期回测中...")
    master_data = []
    for sec_name, tickers in st.session_state.my_sectors.items():
        for t in tickers:
            d = fetch_stock_full_data(t, sectors_data[0]['chg'])
            if d:
                d['sector'] = sec_name
                master_data.append(d)
    status.update(label="数据同步完成！", state="complete", expanded=False)

# 渲染板块雷达卡片
s_cols = st.columns(6)
for idx, sec in enumerate(sectors_data):
    with s_cols[idx]:
        color = "green" if sec['chg'] >= 0 else "red"
        st.markdown(f"""
        <div style="border: 1px solid #ddd; padding: 10px; border-radius: 10px; text-align: center; background: white;">
            <div style="font-size: 0.8rem; font-weight: bold; color: #555;">{sec['name']}</div>
            <div style="font-size: 1.1rem; color: {color}; font-weight: 900;">{sec['chg']:+.2f}%</div>
            <div style="font-size: 0.7rem; color: #999;">流向指引: {sec['flow']:+.1f}</div>
        </div>""", unsafe_allow_html=True)

st.divider()

# 主内容与排行榜
l_col, r_col = st.columns([4.2, 1.3])

with l_col:
    if not st.session_state.my_sectors:
        st.info("← 请先在侧边栏创建板块并添加代码")
    elif not master_data:
        st.warning("⚠️ 无法获取个股数据，请检查代码格式是否正确（例如：CRDO, NVDA, 600519）")
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
                        with c2: st.write(""); st.write("**🗓️ 5日细节**")
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
                                <span>📊 5日: <b>{s['total_5d']:+.2f}%</b> | 144日: <b>{s['total_144d']:+.1f}%</b> | 288日: <b>{s['total_288d']:+.1f}%</b></span>
                                <a href="https://tw.tradingview.com/chart/MdN4tzco/?symbol=NASDAQ:{s['ticker']}" target="_blank" style="text-decoration:none; background:#2962FF; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:bold;">📈 K线详情</a>
                            </div>""", unsafe_allow_html=True)
                        with c4:
                            if st.button("🗑️", key=f"del_{s['ticker']}"): 
                                st.session_state.my_sectors[s_name].remove(s['ticker'])
                                save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力排行")
    b_tabs = st.tabs(["今日", "5日", "144日", "288日"])
    def render_rank(data, key):
        sorted_data = sorted(data, key=lambda x: x[key], reverse=True)
        for idx, item in enumerate(sorted_data):
            st.markdown(f"<div style='display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #eee;'><span>{idx+1}. <b>{item['ticker']}</b></span><span style='color:{'green' if item[key]>=0 else 'red'}; font-weight:bold;'>{item[key]:+.2f}%</span></div>", unsafe_allow_html=True)
    if master_data:
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
        st.session_state.my_sectors[first_sec].append(nt.upper())
        save_config(); st.rerun()
    st.divider()
    all_edit = [t for ts in st.session_state.my_sectors.values() for t in ts]
    edit_t = st.selectbox("编辑笔记", options=list(set(all_edit)))
    note = st.text_area("投资笔记", value=st.session_state.my_notes.get(edit_t, ""), height=150)
    if st.button("保存笔记"): 
        st.session_state.my_notes[edit_t] = note
        save_config(); st.success("已保存")