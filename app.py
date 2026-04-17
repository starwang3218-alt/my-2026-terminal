import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理 ---
CONFIG_FILE = "strategy_terminal_v12.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "量子主权": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源稀土": ["LAC", "MP", "UAMY", "UUUU", "OKLO", "SMR", "BWXT", "CEG", "VST", "CW"],
            "军工国防": ["ESP", "KTOS", "PKE", "PLTR", "BBAI", "FLY", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY"],
            "半导体/算力": ["ADI", "NVMI", "SIMO", "FN", "SWKS", "AAOI", "SITM", "RMBS", "AMKR", "LSCC", "MTSI", "TSEM", "WOLF", "VICR", "TTMI"],
            "航空/维修": ["VSEC", "TATT", "YSS", "FTAI", "AXON", "HEI", "AIR", "LOAR", "ISSC", "ATRO"]
        },
        "benchmarks": {
            "量子主权": "QTUM", "能源稀土": "URA", "军工国防": "ITA", "半导体/算力": "SOXX", "航空/维修": "XAR"
        },
        "notes": {}
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 初始化 ---
st.set_page_config(page_title="2026 战略终端 V12", layout="wide")
st_autorefresh(interval=300000, key="global_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg["benchmarks"], cfg.get("notes", {})
if 'current_page' not in st.session_state: st.session_state.current_page = "Dashboard"
if 'selected_stock' not in st.session_state: st.session_state.selected_stock = None

def to_scalar(val):
    if isinstance(val, (pd.Series, pd.DataFrame)):
        return float(val.iloc[0]) if not val.empty else 0.0
    return float(val)

@st.cache_data(ttl=600)
def fetch_basic_data(sectors, benchmarks):
    all_t = list(set([t for ts in sectors.values() for t in ts]))
    all_b = list(set(benchmarks.values()) | {"SOXX", "ITA", "URA", "QTUM", "XAR", "XLI"})
    data = yf.download(all_t + all_b, period="2y", interval="1d", group_by='ticker', progress=False)
    results, b_res = [], {}
    for b in all_b:
        try:
            h = data[b].dropna()
            b_res[b] = {"chg": ((to_scalar(h['Close'].iloc[-1]) - to_scalar(h['Close'].iloc[-2])) / to_scalar(h['Close'].iloc[-2])) * 100}
        except: b_res[b] = {"chg": 0.0}
    for sec, ts in sectors.items():
        bc = b_res.get(benchmarks.get(sec, "SPY"), {"chg":0})["chg"]
        for t in ts:
            try:
                h = data[t].dropna()
                if h.empty: continue
                p, pre = to_scalar(h['Close'].iloc[-1]), to_scalar(h['Close'].iloc[-2])
                results.append({
                    "ticker": t, "sector": sec, "price": p, "change": ((p-pre)/pre)*100, "rs": ((p-pre)/pre)*100 - bc,
                    "t_5d": ((p-to_scalar(h['Close'].iloc[-6]))/to_scalar(h['Close'].iloc[-6]))*100 if len(h)>6 else 0,
                    "t_144d": ((p-to_scalar(h['Close'].iloc[-145]))/to_scalar(h['Close'].iloc[-145]))*100 if len(h)>=145 else 0,
                    "t_288d": ((p - to_scalar(h['Close'].iloc[-289]))/to_scalar(h['Close'].iloc[-289]))*100 if len(h)>=289 else 0,
                    "history": h.tail(6)
                })
            except: pass
    return b_res, results

def render_stock_page(ticker):
    st.button("⬅️ 返回主盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    t_obj = yf.Ticker(ticker)
    info = t_obj.info
    st.title(f"{ticker} - {info.get('longName', '')}")
    st.metric("Price", f"${info.get('currentPrice', 0)}", f"{info.get('regularMarketChangePercent', 0):+.2f}%")
    st.divider()
    st.components.v1.html(f'<div style="height:600px;"><div id="tv_chart"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{ticker}", "interval": "D", "theme": "light", "style": "1", "locale": "zh_CN", "container_id": "tv_chart"}});</script></div>', height=620)

# --- 4. 侧边栏与主程序 ---
with st.sidebar:
    st.header("⚙️ 战略管理")
    if st.button("🚀 刷新数据", type="primary", use_container_width=True): st.cache_data.clear(); st.rerun()
    with st.expander("📁 板块编辑"):
        target_s = st.selectbox("当前板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("添加代码")
        if st.button("➕ 添加"):
            if nt: st.session_state.my_sectors[target_s].append(nt.upper()); save_config(); st.rerun()
        st.divider()
        ns = st.text_input("新板块名")
        nb = st.text_input("对标 ETF")
        if st.button("📂 创建"):
            if ns: st.session_state.my_sectors[ns] = []; st.session_state.my_benchmarks[ns] = nb.upper(); save_config(); st.rerun()
        if st.button("🗑️ 删除该板块", type="secondary"):
            del st.session_state.my_sectors[target_s]; save_config(); st.rerun()
    st.divider()
    all_ts = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    edit_t = st.selectbox("笔记编辑", all_ts)
    st.session_state.my_notes[edit_t] = st.text_area("记录逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=100)
    if st.button("💾 保存笔记", use_container_width=True): save_config()

b_res, m_res = fetch_basic_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

if st.session_state.current_page == "StockPage":
    render_stock_page(st.session_state.selected_stock)
else:
    # 顶部指数
    idx_cols = st.columns(len(b_res))
    for i, (sym, val) in enumerate(b_res.items()):
        with idx_cols[i]: st.metric(sym, f"{val['chg']:+.2f}%")
    
    l, r = st.columns([3.5, 1.5])
    with l:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                stocks = [x for x in m_res if x['sector'] == s_name]
                for s in stocks:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.5, 4.5, 0.5])
                        with c1:
                            st.markdown(f"### {s['ticker']}")
                            st.markdown(f"## ${s['price']:.2f}")
                            st.markdown(f"<b style='color:{'#28a745' if s['change']>=0 else '#dc3545'}; font-size:1.4rem;'>{s['change']:+.2f}%</b>", unsafe_allow_html=True)
                            # 回归：K线链接
                            st.link_button("📈 K线链接", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
                        with c2:
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                    d_chg = ((cur - pre) / pre) * 100
                                    color = "#28a745" if d_chg >= 0 else "#dc3545"
                                    st.markdown(f"<div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 10px; border-radius: 12px; background-color: #f8fafc;'><b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br><small>${cur:.1f}</small></div>", unsafe_allow_html=True)
                            # 回归：五日走势下方原状
                            st.markdown(f"<div style='margin-top:10px; padding:8px; background:#f1f5f9; border-radius:8px;'><b>288日战力: {s['t_288d']:+.1f}%</b> | RS: {s['rs']:+.2f}%</div>", unsafe_allow_html=True)
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

    with r:
        st.subheader("🏆 战力排行")
        # 增加 144日 维度
        rt = st.tabs(["日内", "5日", "144d", "288d"])
        with st.container(height=800):
            for i, key in enumerate(['change', 't_5d', 't_144d', 't_288d']):
                with rt[i]:
                    for j, item in enumerate(sorted(m_res, key=lambda x: x[key], reverse=True)):
                        v_col = "#dc3545" if item[key] < 0 else "#28a745"
                        # 紧凑型布局：缩小行距
                        c_rank, c_val = st.columns([3, 2])
                        with c_rank:
                            if st.button(f"{j+1}. {item['ticker']}", key=f"rk_{key}_{item['ticker']}"):
                                st.session_state.selected_stock = item['ticker']
                                st.session_state.current_page = "StockPage"
                                st.rerun()
                        with c_val:
                            st.markdown(f"<div style='text-align:right; color:{v_col}; font-weight:bold; padding-top:10px;'>{item[key]:+.1f}%</div>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)