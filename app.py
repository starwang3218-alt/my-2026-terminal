import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 动态配置 (包含你今天提到的所有 2026 核心标的) ---
CONFIG_FILE = "strategy_terminal_v2.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "量子/康波底座": ["IONQ", "XNDU", "RGTI", "QBTS"],
            "AI算力/物理层": ["NVDA", "AVGO", "VICR", "TTMI", "CRDO", "AMD"],
            "军工/航电精工": ["BBAI", "ISSC", "LOAR", "TTM"],
            "AI应用/SaaS": ["HUBS", "PEGA", "GDYN", "TUYA"],
            "数字媒体/AdTech": ["TTD", "MGNI", "SRAD"],
            "身份安全/基建": ["MITK", "TSSI"],
            "周期/能源/居住": ["MP", "AMPY", "KE"]
        },
        "benchmarks": {
            "量子/康波底座": "ARKK", "AI算力/物理层": "SOXX", "军工/航电精工": "ITA", 
            "AI应用/SaaS": "IGV", "数字媒体/AdTech": "XLC", "身份安全/基建": "QQQ", "周期/能源/居住": "XOP"
        },
        "notes": {}
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 核心引擎：财务指标抓取 ---
def get_financials(ticker_obj):
    try:
        # 获取季度利润表
        q_fin = ticker_obj.quarterly_financials
        if q_fin.empty: return "N/A", "N/A"
        
        # 1. 计算 TTM 营收增率
        rev_label = 'Total Revenue' if 'Total Revenue' in q_fin.index else q_fin.index[0]
        rev_series = q_fin.loc[rev_label]
        ttm_growth = "N/A"
        if len(rev_series) >= 8:
            cur_ttm = rev_series.iloc[0:4].sum()
            pri_ttm = rev_series.iloc[4:8].sum()
            ttm_growth = f"{((cur_ttm - pri_ttm) / pri_ttm) * 100:+.1f}%"
        
        # 2. 获取摊薄 EPS (TTM 或最新季)
        eps_val = "N/A"
        if 'Diluted EPS' in q_fin.index:
            latest_eps = q_fin.loc['Diluted EPS'].iloc[0:4].sum()
            eps_val = f"${latest_eps:.2f}"
            
        return ttm_growth, eps_val
    except:
        return "N/A", "N/A"

# --- 3. 初始化 ---
st.set_page_config(page_title="2026 战略终端 2.0", layout="wide")
st_autorefresh(interval=600000, key="fixed_ref") # 10分钟刷新一次

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_benchmarks = cfg["benchmarks"]
    st.session_state.my_notes = cfg.get("notes", {})

# --- 4. 侧边栏：控制与笔记 (已找回并优化) ---
with st.sidebar:
    st.title("🛡️ 终端控制台")
    if st.button("🔄 强制同步全球数据", type="primary", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    
    st.divider()
    st.subheader("📝 投资笔记编辑器")
    all_tickers = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    if all_tickers:
        target = st.selectbox("选择标的记录逻辑", all_tickers)
        note_content = st.text_area("288日长线博弈逻辑", value=st.session_state.my_notes.get(target, ""), height=200)
        if st.button("💾 保存笔记", use_container_width=True):
            st.session_state.my_notes[target] = note_content
            save_config(); st.success("同步成功")

# --- 5. 数据处理 ---
@st.cache_data(ttl=600)
def fetch_all_data(sectors, benchmarks):
    m_data = []
    b_res = {}
    
    # 抓取 Benchmark
    for b_sym in set(benchmarks.values()):
        try:
            d = yf.download(b_sym, period="2d", interval="15m", progress=False)
            if not d.empty:
                c_last, c_prev = d['Close'].iloc[-1], d['Close'].iloc[0]
                b_res[b_sym] = ((c_last - c_prev) / c_prev) * 100
        except: b_res[b_sym] = 0.0

    # 抓取个股
    for s_name, tickers in sectors.items():
        b_chg = b_res.get(benchmarks.get(s_name), 0.0)
        for t in tickers:
            try:
                obj = yf.Ticker(t)
                h = obj.history(period="2y")
                if h.empty: continue
                l_c = h['Close'].iloc[-1]
                t_chg = ((l_c - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                # 获取财务指标
                ttm, eps = get_financials(obj)
                m_data.append({
                    "ticker": t, "sector": s_name, "price": l_c, "change": t_chg, "rs": t_chg - b_chg,
                    "ttm": ttm, "eps": eps,
                    "5d": ((l_c - h['Close'].iloc[-6]) / h['Close'].iloc[-6]) * 100 if len(h)>6 else 0,
                    "288d": ((l_c - h['Close'].iloc[0]) / h['Close'].iloc[0]) * 100
                })
            except: pass
    return m_data

m_res = fetch_all_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

# --- 6. 主界面渲染 ---
st.header("🏟️ 2026 战略资产实时矩阵")

if st.session_state.my_sectors:
    tabs = st.tabs(list(st.session_state.my_sectors.keys()))
    for i, s_name in enumerate(st.session_state.my_sectors.keys()):
        with tabs[i]:
            cols = st.columns(2) # 每行显示两个个股卡片
            for idx, s in enumerate([x for x in m_res if x['sector'] == s_name]):
                with cols[idx % 2]:
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 2])
                        with c1:
                            color = "green" if s['change'] >= 0 else "red"
                            st.markdown(f"### {s['ticker']}")
                            st.markdown(f"<h2 style='color:{color};'>${s['price']:.2f}</h2>", unsafe_allow_html=True)
                            st.markdown(f"当日: **{s['change']:+.2f}%**")
                            st.markdown(f"相对强度: <span style='color:{'green' if s['rs']>0 else 'red'};'>{s['rs']:+.2f}%</span>", unsafe_allow_html=True)
                            
                            tv_link = f"https://www.tradingview.com/chart/MdN4tzco/?symbol={s['ticker']}"
                            st.link_button("📈 实战图表", tv_link)
                            
                        with c2:
                            st.markdown(f"**📊 核心财务指标**")
                            st.info(f"TTM营收增率: **{s['ttm']}**\n\n摊薄每股收益: **{s['eps']}**")
                            st.markdown(f"**⏳ 周期战力**")
                            st.write(f"5日: {s['5d']:+.1f}% | 288日: {s['288d']:+.1f}%")
                            with st.expander("📖 深度投资逻辑"):
                                st.write(st.session_state.my_notes.get(s['ticker'], "暂无笔记，请在侧边栏添加。"))