import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 全量配置管理 (集成 100+ 标的与深度笔记) ---
CONFIG_FILE = "strategy_terminal_ultra_final.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    # 默认全量清单初始化
    return {
        "sectors": {
            "量子主权": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源/核能": ["BWXT", "OKLO", "SMR", "CEG", "VST", "CW", "UUUU", "MP", "LAC", "NEXA"],
            "军工/防御": ["KTOS", "PLTR", "BBAI", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY", "ESP"],
            "半导体/算力": ["VICR", "CRDO", "NVMI", "SIMO", "SWKS", "RMBS", "ANET", "ADEA", "AEHR", "ADI", "SITM", "AMKR", "LSCC"],
            "航空/维修": ["FTAI", "HEI", "AIR", "LOAR", "VSEC", "TATT", "ATRO", "AXON", "YSS"],
            "电力/基建": ["IESC", "BELFA", "ITRI", "ESE", "HUBB", "AROC", "LNG", "FSLR"],
            "软件/系统": ["HUBS", "PEGA", "NOW", "ASAN", "BKSY", "SNPS", "PRGS", "AGYS"],
            "电池/自动驾驶": ["EOSE", "ENVX", "QS", "KULR", "SLDP", "INDI", "ARBE", "PDYN"]
        },
        "benchmarks": {
            "量子主权": "QTUM", "能源/核能": "URA", "军工/防御": "ITA", "半导体/算力": "SOXX", "航空/维修": "XAR"
        },
        "notes": {
            "BWXT": "核能心脏。垄断海军核动力堆，‘Pele 计划’微堆原型即将临界运行。AI 算力的终点是核能。",
            "VICR": "GPU 供血泵。VPD 垂直供电技术解决 1000W+ 功耗瓶颈。物理层不可逾越的壁垒。",
            "CRDO": "算力网络‘神经纤维’。命门在 1.6T 升级周期，RS 战力极强。",
            "FTAI": "算力救急电源。退役航发改地面涡轮。用‘航空废墟’建立‘算力新秩序’。",
            "UAMY": "锑矿资源垄断。美国本土唯一冶炼商。国防补库与光伏双重驱动。"
        }
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 界面初始化 ---
st.set_page_config(page_title="2026 战略终端 (Ultra Pro)", layout="wide")
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
                    # --- 修复逻辑：取倒数第 289 个元素，即正好 288 个交易日前 ---
                    "t_288d": ((p - to_scalar(h['Close'].iloc[-289]))/to_scalar(h['Close'].iloc[-289]))*100 if len(h)>=289 else 0,
                    "history": h.tail(6)
                })
            except: pass
    return b_res, results

# --- 3. 独立详情页渲染 ---
def render_stock_page(ticker):
    st.button("⬅️ 返回战略大盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    t_obj = yf.Ticker(ticker)
    info = t_obj.info
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.title(f"{ticker}")
        st.subheader(info.get('longName', ''))
        st.metric("实时价格", f"${info.get('currentPrice', 0)}", f"{info.get('regularMarketChangePercent', 0):+.2f}%")
    with c2:
        st.markdown(f"### 🛡️ 战略博弈逻辑")
        st.info(st.session_state.my_notes.get(ticker, "该标的博弈逻辑待更新。"))

    st.divider()
    i1, i2, i3, i4 = st.columns(4)
    with i1:
        cal = t_obj.calendar
        next_earn = cal.get('Earnings Date', [datetime.now()])[0].strftime('%Y-%m-%d') if cal is not None and not cal.empty else "待定"
        st.markdown(f"<div style='border:2px solid #3b82f6; padding:15px; border-radius:15px; text-align:center;'><h4>📅 下次财报</h4><h2 style='color:#3b82f6;'>{next_earn}</h2></div>", unsafe_allow_html=True)
    with i2: st.markdown(f"<div style='border:1px solid #e2e8f0; padding:15px; border-radius:15px; text-align:center;'><h4>💰 市值</h4><h2>{info.get('marketCap', 0)/1e9:.1f}B</h2></div>", unsafe_allow_html=True)
    with i3: st.markdown(f"<div style='border:1px solid #e2e8f0; padding:15px; border-radius:15px; text-align:center;'><h4>📈 远期 PE</h4><h2>{info.get('forwardPE', 'N/A')}</h2></div>", unsafe_allow_html=True)
    with i4: st.markdown(f"<div style='border:1px solid #e2e8f0; padding:15px; border-radius:15px; text-align:center;'><h4>💧 现金流</h4><h2>{info.get('freeCashflow', 0)/1e6:.1f}M</h2></div>", unsafe_allow_html=True)

    st.markdown("### 📊 实时 K 线分析")
    st.components.v1.html(f'<div class="tradingview-widget-container" style="height:500px;"><div id="tv_chart"></div><script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script><script type="text/javascript">new TradingView.widget({{"autosize": true, "symbol": "{ticker}", "interval": "D", "timezone": "Etc/UTC", "theme": "light", "style": "1", "locale": "zh_CN", "container_id": "tv_chart"}});</script></div>', height=520)

# --- 4. 主程序流程 ---
with st.sidebar:
    st.header("⚙️ 战略管理")
    if st.button("🚀 刷新全量战力", type="primary", use_container_width=True): st.cache_data.clear(); st.rerun()
    
    with st.expander("📁 板块与代码编辑"):
        # 板块编辑功能
        target_s = st.selectbox("目标板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("新增个股代码")
        if st.button("添加标的"):
            if nt: st.session_state.my_sectors[target_s].append(nt.upper()); save_config(); st.rerun()
        st.divider()
        ns = st.text_input("新建板块名称")
        nb = st.text_input("对标 ETF (如 ITA)")
        if st.button("创建板块"):
            if ns: st.session_state.my_sectors[ns] = []; st.session_state.my_benchmarks[ns] = nb.upper(); save_config(); st.rerun()
        if st.button("🗑️ 删除当前板块", type="secondary"):
            del st.session_state.my_sectors[target_s]; save_config(); st.rerun()

    st.divider()
    all_ts = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    edit_t = st.selectbox("深度笔记编辑 (100+)", all_ts)
    st.session_state.my_notes[edit_t] = st.text_area("博弈核心逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=150)
    if st.button("💾 保存笔记", use_container_width=True): save_config()

b_res, m_res = fetch_basic_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

if st.session_state.current_page == "StockPage":
    render_stock_page(st.session_state.selected_stock)
else:
    # 顶部指数
    idx_cols = st.columns(len(b_res))
    for i, (sym, val) in enumerate(b_res.items()):
        with idx_cols[i]: st.metric(sym, f"{val['chg']:+.2f}%")
    
    l_col, r_col = st.columns([3.5, 1.5])
    with l_col:
        st.subheader("📡 全域战略巡航")
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
                            st.markdown(f"<b style='color:{'#28a745' if s['change']>=0 else '#dc3545'}; font-size:1.4rem;'>{s['change']:+.2f}%</b>", unsafe_allow_html=True)
                            if st.button(f"🔍 研报页", key=f"btn_{s['ticker']}"):
                                st.session_state.selected_stock = s['ticker']; st.session_state.current_page = "StockPage"; st.rerun()
                        with c2:
                            # 方框 UI：字体加大且圈起
                            h_cols = st.columns(5)
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                    d_chg = ((cur - pre) / pre) * 100
                                    color = "#28a745" if d_chg >= 0 else "#dc3545"
                                    st.markdown(f"""
                                        <div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 12px; border-radius: 12px; background-color: #f8fafc;'>
                                            <small style='color:#64748b;'>{s['history'].index[idx].strftime('%m-%d')}</small><br>
                                            <b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br>
                                            <small style='font-weight:bold;'>${cur:.1f}</small>
                                        </div>
                                    """, unsafe_allow_html=True)
                            st.markdown(f"<div style='margin-top:12px; padding:10px; background:#f1f5f9; border-radius:8px;'><b>288日真实战力: {s['t_288d']:+.1f}%</b> | RS: {s['rs']:+.2f}%</div>", unsafe_allow_html=True)
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

    with r_col:
        st.subheader("🏆 全量战力排行")
        rt = st.tabs(["日内", "5日", "288d"])
        with st.container(height=800):
            for i, key in enumerate(['change', 't_5d', 't_288d']):
                with rt[i]:
                    for j, item in enumerate(sorted(m_res, key=lambda x: x[key], reverse=True)):
                        v_col = "#dc3545" if item[key] < 0 else "#28a745"
                        st.markdown(f"<div style='display:flex; justify-content:space-between; border-bottom:1px solid #f1f5f9; padding:5px 0;'><span>{j+1}. <b>{item['ticker']}</b></span><span style='color:{v_col}; font-weight:bold;'>{item[key]:+.1f}%</span></div>", unsafe_allow_html=True)