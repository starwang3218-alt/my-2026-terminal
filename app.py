import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 全量配置与深度笔记 ---
CONFIG_FILE = "strategy_terminal_stock_pages.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {
        "sectors": {
            "量子": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源核能": ["BWXT", "OKLO", "SMR", "CEG", "VST", "CW", "UUUU", "MP"],
            "军工国防": ["KTOS", "PLTR", "BBAI", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY"],
            "半导体/算力": ["VICR", "CRDO", "NVMI", "SIMO", "SWKS", "RMBS", "ANET", "ADEA", "AEHR"],
            "航空/维修": ["FTAI", "HEI", "AIR", "LOAR", "VSEC", "TATT", "ATRO", "AXON"],
            "电力/基建": ["IESC", "BELFA", "ITRI", "ESE", "HUBB", "AROC"],
            "软件/系统": ["HUBS", "PEGA", "NOW", "ASAN", "BKSY", "SNPS"]
        },
        "benchmarks": {
            "量子": "QTUM", "能源核能": "URA", "军工国防": "ITA", "半导体/算力": "SOXX", "航空/维修": "XAR"
        },
        "notes": {
            "BWXT": "核能心脏。垄断海军核动力堆，‘Pele 计划’微堆原型即将临界运行。逻辑：AI 算力的终点是核能，它是脱网能源的唯一物理底座。",
            "VICR": "GPU 供血泵。VPD 垂直供电技术解决 1000W+ 功耗瓶颈。逻辑：只要单芯片功耗不下降，VICR 的物理壁垒就不可逾越。",
            "CRDO": "算力网络‘神经纤维’。命门在 1.6T 升级周期。逻辑：数据中心内部连接的成本奇点。",
            "FTAI": "算力救急电源。退役航发改地面涡轮。逻辑：用‘航空废墟’建立‘算力新秩序’，Q4 交付是核心奇点。",
            "LUNR": "地月物流总包。掌握 9 亿订单，2026 营收预期翻 5 倍。逻辑：空间主权竞争的物理搬运工。"
        }
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 界面初始化 ---
st.set_page_config(page_title="2026 战略终端 - 独立研报版", layout="wide")
st_autorefresh(interval=300000, key="global_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg["benchmarks"], cfg.get("notes", {})
if 'current_page' not in st.session_state:
    st.session_state.current_page = "Dashboard"
if 'selected_stock' not in st.session_state:
    st.session_state.selected_stock = None

def to_scalar(val):
    if isinstance(val, (pd.Series, pd.DataFrame)):
        return float(val.iloc[0]) if not val.empty else 0.0
    return float(val)

@st.cache_data(ttl=600)
def fetch_basic_data(sectors, benchmarks):
    all_t = list(set([t for ts in sectors.values() for t in ts]))
    all_b = list(set(benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM"})
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
                    "t_288d": ((p-to_scalar(h['Close'].iloc[0]))/to_scalar(h['Close'].iloc[0]))*100 if len(h)>=288 else 0,
                    "history": h.tail(6)
                })
            except: pass
    return b_res, results

# --- 3. 详情页函数 (Independent Page) ---
def render_stock_page(ticker):
    st.button("⬅️ 返回战略大盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    
    t_obj = yf.Ticker(ticker)
    info = t_obj.info
    
    # 头部：代码与核心逻辑
    c1, c2 = st.columns([1, 2])
    with c1:
        st.title(f"{ticker}")
        st.subheader(info.get('longName', ''))
        st.metric("实时股价", f"${info.get('currentPrice', 0)}", f"{info.get('regularMarketChangePercent', 0):+.2f}%")
    with c2:
        st.markdown(f"### 🛡️ 战略博弈逻辑")
        st.info(st.session_state.my_notes.get(ticker, "该标的尚未录入深度解析，请在侧边栏完善。"))

    st.divider()
    
    # 第一排：财报与关键指标
    i1, i2, i3, i4 = st.columns(4)
    with i1:
        # 获取财报日期
        cal = t_obj.calendar
        next_earnings = "未知"
        if cal is not None and not cal.empty:
            next_earnings = cal.get('Earnings Date', [datetime.now()])[0].strftime('%Y-%m-%d')
        st.markdown(f"<div style='border:2px solid #3b82f6; padding:20px; border-radius:15px; text-align:center;'><h4>📅 下次财报</h4><h2 style='color:#3b82f6;'>{next_earnings}</h2></div>", unsafe_allow_html=True)
    
    with i2:
        st.markdown(f"<div style='border:1px solid #e2e8f0; padding:20px; border-radius:15px; text-align:center;'><h4>💰 市值 (B)</h4><h2>{info.get('marketCap', 0)/1e9:.2f}B</h2></div>", unsafe_allow_html=True)
    with i3:
        st.markdown(f"<div style='border:1px solid #e2e8f0; padding:20px; border-radius:15px; text-align:center;'><h4>📈 市盈率 (PE)</h4><h2>{info.get('forwardPE', 'N/A')}</h2></div>", unsafe_allow_html=True)
    with i4:
        st.markdown(f"<div style='border:1px solid #e2e8f0; padding:20px; border-radius:15px; text-align:center;'><h4>💧 现金流 (FCF)</h4><h2>{info.get('freeCashflow', 0)/1e6:.1f}M</h2></div>", unsafe_allow_html=True)

    # 第二排：大尺寸 TradingView K 线
    st.markdown("### 📊 实时战力演化 (TradingView)")
    st.components.v1.html(f"""
        <div class="tradingview-widget-container" style="height:500px;width:100%">
          <div id="tradingview_chart"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "autosize": true, "symbol": "{ticker}", "interval": "D", "timezone": "Etc/UTC",
            "theme": "light", "style": "1", "locale": "zh_CN", "toolbar_bg": "#f1f3f6",
            "enable_publishing": false, "allow_symbol_change": true, "container_id": "tradingview_chart"
          }});
          </script>
        </div>
    """, height=520)

# --- 4. 主程序控制 ---
b_res, m_res = fetch_basic_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

if st.session_state.current_page == "StockPage" and st.session_state.selected_stock:
    render_stock_page(st.session_state.selected_stock)
else:
    # --- 全局巡航模式 ---
    l_col, r_col = st.columns([3.5, 1.5])
    with l_col:
        st.subheader("📡 2026 战略巡航模式")
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                stocks = [x for x in m_res if x['sector'] == s_name]
                for s in stocks:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.5, 4.5, 0.5])
                        with c1:
                            st.markdown(f"### {s['ticker']}")
                            st.markdown(f"<h2 style='margin:0;'>${s['price']:.2f}</h2>", unsafe_allow_html=True)
                            # 增加点击跳转功能
                            if st.button(f"🔍 进入独立页面", key=f"page_{s['ticker']}"):
                                st.session_state.selected_stock = s['ticker']
                                st.session_state.current_page = "StockPage"
                                st.rerun()
                        with c2:
                            # 方框 UI 走势
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                    d_chg = ((cur - pre) / pre) * 100
                                    color = "#28a745" if d_chg >= 0 else "#dc3545"
                                    st.markdown(f"<div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 10px; border-radius: 10px; background-color: #f8fafc;'><b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br><small>${cur:.1f}</small></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:10px;'><b>288日战力: {s['t_288d']:+.1f}%</b> | {st.session_state.my_notes.get(s['ticker'], '未录入...')[:50]}...</div>", unsafe_allow_html=True)

    with r_col:
        st.subheader("🏆 全量战力排行")
        # 增加搜索直达
        search_t = st.selectbox("快速搜索/直达独立页", [""] + sorted([x['ticker'] for x in m_res]))
        if search_t:
            st.session_state.selected_stock = search_t
            st.session_state.current_page = "StockPage"
            st.rerun()
        
        rt = st.tabs(["日内", "5日", "288d"])
        with st.container(height=800):
            for i, key in enumerate(['change', 't_5d', 't_288d']):
                with rt[i]:
                    for j, item in enumerate(sorted(m_res, key=lambda x: x[key], reverse=True)):
                        v_col = "#dc3545" if item[key] < 0 else "#28a745"
                        st.markdown(f"<div style='display:flex; justify-content:space-between;'><span>{j+1}. <b>{item['ticker']}</b></span><span style='color:{v_col}; font-weight:bold;'>{item[key]:+.1f}%</span></div>", unsafe_allow_html=True)