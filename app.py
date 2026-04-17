import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 全局 UI 压缩渲染 ---
st.set_page_config(page_title="2026 战略终端 (Pro UI)", layout="wide")
st.markdown("""
<style>
div[data-testid="column"] { margin-bottom: -15px !important; }
div.stButton button {
    min-height: 24px !important; height: 32px !important;
    padding-top: 2px !important; padding-bottom: 2px !important;
    background-color: transparent !important; border: none !important;
    color: #1e293b !important; font-weight: 700 !important;
    justify-content: flex-start !important;
}
div.stButton button:hover { color: #3b82f6 !important; }
</style>
""", unsafe_allow_html=True)

# --- 1. 配置管理 ---
CONFIG_FILE = "strategy_terminal_ultra_pro_v19.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {
        "sectors": {
            "量子": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源稀土": ["LAC", "MP", "USAR", "ALOY", "UAMY", "UUUU", "NEXA", "NB", "OKLO", "SMR", "BWXT", "CEG", "VST", "CW"],
            "军工国防": ["ESP", "KTOS", "PKE", "PLTR", "BBAI", "FLY", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY"],
            "半导体": ["ADI", "NVMI", "SIMO", "FN", "SWKS", "AAOI", "SITM", "RMBS", "AMKR", "LSCC", "MTSI", "TSEM", "WOLF", "VICR", "TTMI"],
            "数字媒体": ["RDVT", "TRAK", "OPRA", "MGNI"],
            "AI算力/应用": ["ADEA", "EXLS", "ANET", "DGII", "AEHR", "SOUN", "CRDO", "HUBS", "PEGA"],
            "电力基建": ["IESC", "BELFA", "ITRI", "ESE", "FSLR", "AROC", "LNG", "KGS", "HUBB"],
            "航空精工/维修": ["VSEC", "TATT", "YSS", "FTAI", "AXON", "HEI", "AIR", "LOAR", "ISSC", "ATRO"],
            "软件/系统": ["PRGS", "AGYS", "NOW", "ASAN", "LZ", "BKSY", "SNPS"],
            "电池/新能": ["EOSE", "ENVX", "QS", "KULR", "SLDP"],
            "通信/自动驾驶": ["VEON", "DY", "INDI", "ARBE", "PDYN"],
            "金融/支付": ["SEZL", "INTU"],
            "沙盘推演": ["ELPW"] # 专门用于技术异动教学和推演
        },
        "benchmarks": {
            "量子": "QTUM", "能源稀土": "URA", "军工国防": "ITA", "半导体": "SOXX", 
            "数字媒体": "XLC", "AI算力/应用": "IGV", "电力基建": "XLI", "航空精工/维修": "XAR", "沙盘推演": "SPY"
        },
        "notes": {}
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 系统核心初始化 ---
st_autorefresh(interval=300000, key="global_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg["benchmarks"], cfg.get("notes", {})
if 'current_page' not in st.session_state: st.session_state.current_page = "Dashboard"
if 'selected_stock' not in st.session_state: st.session_state.selected_stock = None

def to_scalar(val):
    if isinstance(val, (pd.Series, pd.DataFrame)): return float(val.iloc[0]) if not val.empty else 0.0
    return float(val)

@st.cache_data(ttl=600)
def fetch_all_data(sectors, benchmarks):
    all_tickers = list(set([t for ts in sectors.values() for t in ts]))
    all_bench = list(set(benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM", "SPY"})
    full_data = yf.download(all_tickers + all_bench, period="2y", interval="1d", group_by='ticker', progress=False)
    results, b_res = [], {}

    for b in all_bench:
        try:
            h = full_data[b].dropna()
            b_res[b] = {"chg": ((to_scalar(h['Close'].iloc[-1]) - to_scalar(h['Close'].iloc[-2])) / to_scalar(h['Close'].iloc[-2])) * 100}
        except: b_res[b] = {"chg": 0.0}

    for sec_name, tickers in sectors.items():
        b_sym = benchmarks.get(sec_name, "SPY")
        b_chg = b_res.get(b_sym, {"chg": 0.0})["chg"]
        for t in tickers:
            try:
                h = full_data[t].dropna()
                if len(h) < 2: continue
                price, prev = to_scalar(h['Close'].iloc[-1]), to_scalar(h['Close'].iloc[-2])
                if prev == 0: continue
                
                h['MA5'] = h['Close'].rolling(window=5).mean()
                h['MA12'] = h['Close'].rolling(window=12).mean()
                h['MA30'] = h['Close'].rolling(window=30).mean()
                h['MA144'] = h['Close'].rolling(window=144).mean()
                h['MA288'] = h['Close'].rolling(window=288).mean()

                # --- 核心：计算均线粘合度 (MA Spread) ---
                ma_spread = 999
                if len(h) >= 144:
                    ma_vals = [to_scalar(h['MA5'].iloc[-1]), to_scalar(h['MA12'].iloc[-1]), to_scalar(h['MA30'].iloc[-1]), to_scalar(h['MA144'].iloc[-1])]
                    if all(v > 0 for v in ma_vals):
                        # 计算 5, 12, 30, 144 四根均线之间的最大离散度
                        ma_spread = (max(ma_vals) - min(ma_vals)) / min(ma_vals)

                day_chg = ((price - prev) / prev) * 100
                results.append({
                    "ticker": t, "sector": sec_name, "price": price, "change": day_chg, "rs": day_chg - b_chg,
                    "t_5d": ((price - to_scalar(h['Close'].iloc[-6]))/to_scalar(h['Close'].iloc[-6]))*100 if len(h)>=6 and to_scalar(h['Close'].iloc[-6])!=0 else 0,
                    "t_144d": ((price - to_scalar(h['Close'].iloc[-145]))/to_scalar(h['Close'].iloc[-145]))*100 if len(h)>=145 and to_scalar(h['Close'].iloc[-145])!=0 else 0,
                    "t_288d": ((price - to_scalar(h['Close'].iloc[-289]))/to_scalar(h['Close'].iloc[-289]))*100 if len(h)>=289 and to_scalar(h['Close'].iloc[-289])!=0 else 0,
                    "history": h.tail(6),
                    "ma5": to_scalar(h['MA5'].iloc[-1]) if len(h)>=5 else 0,
                    "ma12": to_scalar(h['MA12'].iloc[-1]) if len(h)>=12 else 0,
                    "ma30": to_scalar(h['MA30'].iloc[-1]) if len(h)>=30 else 0,
                    "ma144": to_scalar(h['MA144'].iloc[-1]) if len(h)>=144 else 0,
                    "ma288": to_scalar(h['MA288'].iloc[-1]) if len(h)>=288 else 0,
                    "ma_spread": ma_spread # 注入粘合度基因
                })
            except: pass
    return b_res, results

# --- 新增：带有均线雷达的独立研报页 ---
def render_stock_page(ticker, m_res):
    st.button("⬅️ 返回战略大盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    
    s = next((x for x in m_res if x['ticker'] == ticker), None)
    if not s:
        st.error("⚠️ 数据加载失败。")
        return

    st.markdown(f"## 🎯 战术锁定：{s['ticker']}")
    
    with st.container(border=True):
        c1, c2 = st.columns([1.5, 4.5])
        with c1:
            st.markdown(f"### {s['ticker']}")
            st.markdown(f"<h2 style='margin:0;'>${s['price']:.2f}</h2>", unsafe_allow_html=True)
            st.markdown(f"<b style='color:{'#28a745' if s['change']>=0 else '#dc3545'}; font-size:1.4rem;'>{s['change']:+.2f}%</b>", unsafe_allow_html=True)
            st.link_button("📈 K线直达", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
        
        with c2:
            h_cols = st.columns(5)
            hist_len = len(s['history'])
            for idx in range(1, 6):
                with h_cols[idx-1]:
                    if idx < hist_len:
                        cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                        d_chg = ((cur - pre) / pre) * 100 if pre != 0 else 0
                        color = "#28a745" if d_chg >= 0 else "#dc3545"
                        dt_str = s['history'].index[idx].strftime('%m-%d')
                        st.markdown(f"""
                            <div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 10px; border-radius: 10px; background-color: #f8fafc; margin: 2px;'>
                                <small style='color:#64748b;'>{dt_str}</small><br>
                                <b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br>
                                <small style='font-weight:bold; font-size: 1.1rem;'>${cur:.1f}</small>
                            </div>
                        """, unsafe_allow_html=True)
            
            st.markdown(f"<div style='background:#f1f5f9; padding:10px; border-radius:8px; margin-top:15px; font-size:1rem; border-left:4px solid #3b82f6;'><b>5日累积: {s['t_5d']:+.2f}%</b> | 144日: <b>{s['t_144d']:+.1f}%</b> | 288日战力: <b>{s['t_288d']:+.1f}%</b></div>", unsafe_allow_html=True)

            ma5, ma12, ma30, ma144, ma288, price = s['ma5'], s['ma12'], s['ma30'], s['ma144'], s['ma288'], s['price']
            trend_html = ""
            
            # 判断逻辑更新：加入了极度粘合的判定
            if s['ma_spread'] < 0.04:
                trend_html = "<span style='background-color:#fef08a; color:#854d0e; padding:4px 8px; border-radius:4px; font-weight:bold;'>🎯 极度粘合 (爆发前夜)</span>"
            elif ma288 > 0 and (price > ma5 > ma12 > ma30 > ma144 > ma288):
                trend_html = "<span style='background-color:#dcfce7; color:#166534; padding:4px 8px; border-radius:4px; font-weight:bold;'>🔥 战力全开 (绝对多头)</span>"
            elif ma288 > 0 and price < ma288:
                trend_html = "<span style='background-color:#fee2e2; color:#991b1b; padding:4px 8px; border-radius:4px; font-weight:bold;'>🧊 战略深水区</span>"
            else:
                trend_html = "<span style='background-color:#f1f5f9; color:#475569; padding:4px 8px; border-radius:4px; font-weight:bold;'>⚖️ 震荡整理区</span>"
            
            dev_288 = ((price - ma288) / ma288 * 100) if ma288 > 0 else 0
            dev_color = "#dc3545" if dev_288 < 0 else "#28a745"

            st.markdown(f"""
            <div style='background:#ffffff; border:1.5px solid #e2e8f0; padding:12px; border-radius:8px; margin-top:10px;'>
                <div style='margin-bottom:10px;'>{trend_html} <span style='margin-left:15px; font-size:0.95rem; color:#475569;'>当前偏离 288日均线: <b style='color:{dev_color}; font-size:1.1rem;'>{dev_288:+.2f}%</b></span></div>
                <div style='display:flex; justify-content:space-between; font-size:0.9rem; color:#475569; font-family:monospace; background:#f8fafc; padding:8px; border-radius:4px;'>
                    <span>MA5: <b>${ma5:.2f}</b></span> |
                    <span>MA12: <b>${ma12:.2f}</b></span> |
                    <span>MA30: <b>${ma30:.2f}</b></span> |
                    <span>MA144: <b>${ma144:.2f}</b></span> |
                    <span>MA288: <b>${ma288:.2f}</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    
    current_note = st.session_state.my_notes.get(ticker, "")
    col_edit, col_preview = st.columns([1, 1])
    with col_edit:
        new_note = st.text_area(f"撰写 {ticker} 的博弈逻辑 (支持 Markdown)：", value=current_note, height=500)
        if st.button("💾 保存解析内容", type="primary", use_container_width=True):
            st.session_state.my_notes[ticker] = new_note
            save_config()
            st.success("✅ 笔记已永久保存！")
    with col_preview:
        st.markdown("**🔍 渲染预览**")
        with st.container(border=True, height=500):
            if new_note: st.markdown(new_note)
            else: st.info("暂无解析内容。")

# --- 3. 界面布局 ---
with st.sidebar:
    st.header("⚙️ 终端管理")
    if st.button("🚀 刷新全量数据", type="primary", use_container_width=True): st.cache_data.clear(); st.rerun()
    
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
        if st.button("🗑️ 删除该板块"):
            del st.session_state.my_sectors[target_s]; save_config(); st.rerun()
            
    st.divider()
    all_ts = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    edit_t = st.selectbox("快速逻辑编辑", all_ts)
    st.session_state.my_notes[edit_t] = st.text_area("简易记录", value=st.session_state.my_notes.get(edit_t, ""), height=150)
    if st.button("💾 保存侧栏笔记", use_container_width=True): save_config()

b_res, m_res = fetch_all_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

if st.session_state.current_page == "StockPage":
    render_stock_page(st.session_state.selected_stock, m_res)
else:
    st.title("🏛️ 2026 战略资产终端 (终极排版)")
    r_cols = st.columns(len(b_res))
    for i, (sym, val) in enumerate(b_res.items()):
        with r_cols[i]: st.metric(sym, f"{val['chg']:+.2f}%")

    st.divider()

    l_col, r_col = st.columns([3.5, 1.5])

    with l_col:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                sector_stocks = [x for x in m_res if x['sector'] == s_name]
                for s in sector_stocks:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.5, 4.5, 0.5])
                        with c1:
                            st.markdown(f"### {s['ticker']}")
                            st.markdown(f"<h2 style='margin:0;'>${s['price']:.2f}</h2>", unsafe_allow_html=True)
                            st.markdown(f"<b style='color:{'#28a745' if s['change']>=0 else '#dc3545'}; font-size:1.4rem;'>{s['change']:+.2f}%</b>", unsafe_allow_html=True)
                            st.link_button("📈 K线", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
                        
                        with c2:
                            h_cols = st.columns(5)
                            hist_len = len(s['history'])
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    if idx < hist_len:
                                        cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                        d_chg = ((cur - pre) / pre) * 100 if pre != 0 else 0
                                        color = "#28a745" if d_chg >= 0 else "#dc3545"
                                        st.markdown(f"""
                                            <div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 10px; border-radius: 10px; background-color: #f8fafc; margin: 2px;'>
                                                <small style='color:#64748b;'>{s['history'].index[idx].strftime('%m-%d')}</small><br>
                                                <b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br>
                                                <small style='font-weight:bold; font-size: 1.1rem;'>${cur:.1f}</small>
                                            </div>
                                        """, unsafe_allow_html=True)
                            
                            st.markdown(f"<div style='background:#f1f5f9; padding:10px; border-radius:8px; margin-top:15px; font-size:1rem; border-left:4px solid #3b82f6;'><b>5日累积: {s['t_5d']:+.2f}%</b> | 144日: <b>{s['t_144d']:+.1f}%</b> | 288日: <b>{s['t_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                            with st.expander("🔍 深度解析"): st.write(st.session_state.my_notes.get(s['ticker'], "暂无解析..."))
                        
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"):
                                st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

    with r_col:
        st.subheader("🏆 全量战力排行榜")
        # --- 核心：新增潜伏雷达独立 Tab ---
        rank_tabs = st.tabs(["日内", "5日", "144d", "288d", "🎯 潜伏"])
        rank_keys = [('change', '今日'), ('t_5d', '5日'), ('t_144d', '144d'), ('t_288d', '288d')]
        
        with st.container(height=900): 
            # 渲染前四个常规排行榜
            for i, (key, label) in enumerate(rank_keys):
                with rank_tabs[i]:
                    sorted_m = sorted(m_res, key=lambda x: x[key], reverse=True)
                    for j, item in enumerate(sorted_m):
                        val_color = "#dc3545" if item[key] < 0 else "#28a745"
                        c_rank, c_val = st.columns([3, 1])
                        with c_rank:
                            if st.button(f"{j+1}. {item['ticker']}", key=f"rk_{key}_{item['ticker']}"):
                                st.session_state.selected_stock = item['ticker']
                                st.session_state.current_page = "StockPage"
                                st.rerun()
                        with c_val:
                            st.markdown(f"<div style='text-align:right; color:{val_color}; font-weight:bold; font-family: monospace; padding-top:6px;'>{item[key]:+.1f}%</div>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:0; border:none; border-bottom:1px solid #f1f5f9;'>", unsafe_allow_html=True)
            
            # --- 渲染潜伏雷达专属面板 ---
            with rank_tabs[4]:
                st.markdown("<small style='color:#64748b;'>* 扫描 MA5/12/30/144 极度粘合的标的，按RS排序</small>", unsafe_allow_html=True)
                # 筛选出均线振幅小于 4% (0.04) 的高度收敛标的
                coiled_stocks = [x for x in m_res if x['ma_spread'] < 0.04 and x['ma144'] > 0]
                coiled_stocks = sorted(coiled_stocks, key=lambda x: x['rs'], reverse=True)
                
                if not coiled_stocks:
                    st.info("目前没有均线极度粘合的标的。")
                else:
                    for j, item in enumerate(coiled_stocks):
                        c_rank, c_val = st.columns([3, 1])
                        with c_rank:
                            if st.button(f"🎯 {item['ticker']}", key=f"rk_coil_{item['ticker']}"):
                                st.session_state.selected_stock = item['ticker']
                                st.session_state.current_page = "StockPage"
                                st.rerun()
                        with c_val:
                            st.markdown(f"<div style='text-align:right; color:#854d0e; font-weight:bold; font-family: monospace; padding-top:6px;'>RS {item['rs']:+.1f}%</div>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:0; border:none; border-bottom:1px solid #f1f5f9;'>", unsafe_allow_html=True)