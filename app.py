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
CONFIG_FILE = "strategy_terminal_ultra_pro_v21.json"

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
            "沙盘推演": ["ELPW"] 
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

def get_return(history_df, days_back):
    if len(history_df) >= days_back + 1:
        curr = to_scalar(history_df['Close'].iloc[-1])
        prev = to_scalar(history_df['Close'].iloc[-(days_back+1)])
        if prev != 0: return ((curr - prev) / prev) * 100
    return 0.0

@st.cache_data(ttl=600)
def fetch_all_data(sectors, benchmarks):
    all_tickers = list(set([t for ts in sectors.values() for t in ts]))
    all_bench = list(set(benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM", "SPY"})
    full_data = yf.download(all_tickers + all_bench, period="2y", interval="1d", group_by='ticker', progress=False)
    
    results, b_res, b_history = [], {}, {}

    # 预计算并存储所有基准 ETF 的历史数据，用于跨周期比对
    for b in all_bench:
        try:
            h = full_data[b].dropna()
            b_history[b] = h
            b_res[b] = {"chg": get_return(h, 1)}
        except: pass

    for sec_name, tickers in sectors.items():
        b_sym = benchmarks.get(sec_name, "SPY")
        b_h = b_history.get(b_sym)
        b_ret_1 = get_return(b_h, 1) if b_h is not None else 0
        b_ret_5 = get_return(b_h, 5) if b_h is not None else 0
        b_ret_30 = get_return(b_h, 30) if b_h is not None else 0
        b_ret_144 = get_return(b_h, 144) if b_h is not None else 0

        for t in tickers:
            try:
                h = full_data[t].dropna()
                if len(h) < 30: continue 
                
                price = to_scalar(h['Close'].iloc[-1])
                s_ret_1 = get_return(h, 1)
                s_ret_5 = get_return(h, 5)
                s_ret_30 = get_return(h, 30)
                s_ret_144 = get_return(h, 144)
                
                h['MA5'] = h['Close'].rolling(window=5).mean()
                h['MA12'] = h['Close'].rolling(window=12).mean()
                h['MA30'] = h['Close'].rolling(window=30).mean()
                h['MA144'] = h['Close'].rolling(window=144).mean()
                h['MA288'] = h['Close'].rolling(window=288).mean()
                
                v_ma5 = to_scalar(h['Volume'].rolling(5).mean().iloc[-1])
                v_ma30 = to_scalar(h['Volume'].rolling(30).mean().iloc[-1])
                vol_dry_ratio = (v_ma5 / v_ma30) if v_ma30 > 0 else 1.0

                ma_spread = 999
                if len(h) >= 144:
                    ma_vals = [to_scalar(h['MA5'].iloc[-1]), to_scalar(h['MA12'].iloc[-1]), to_scalar(h['MA30'].iloc[-1]), to_scalar(h['MA144'].iloc[-1])]
                    if all(v > 0 for v in ma_vals):
                        ma_spread = (max(ma_vals) - min(ma_vals)) / min(ma_vals)

                # --- 核心更新：计算多周期相对强度 RS ---
                rs_1d = s_ret_1 - b_ret_1
                rs_5d = s_ret_5 - b_ret_5
                rs_30d = s_ret_30 - b_ret_30
                rs_144d = s_ret_144 - b_ret_144
                
                # 满分 RS 抗跌要求：5日和30日同时跑赢基准
                is_rs_strong = (rs_5d > 0) and (rs_30d > 0)
                is_vol_dry = vol_dry_ratio < 0.8
                is_uptrend = price > to_scalar(h['MA144'].iloc[-1]) if len(h)>=144 else False

                results.append({
                    "ticker": t, "sector": sec_name, "price": price, "change": s_ret_1, "rs": rs_1d,
                    "t_5d": s_ret_5, "t_144d": s_ret_144, 
                    "t_288d": ((price - to_scalar(h['Close'].iloc[-289]))/to_scalar(h['Close'].iloc[-289]))*100 if len(h)>=289 else 0,
                    "history": h.tail(6),
                    "ma5": to_scalar(h['MA5'].iloc[-1]), "ma12": to_scalar(h['MA12'].iloc[-1]),
                    "ma30": to_scalar(h['MA30'].iloc[-1]), "ma144": to_scalar(h['MA144'].iloc[-1]) if len(h)>=144 else 0,
                    "ma288": to_scalar(h['MA288'].iloc[-1]) if len(h)>=288 else 0,
                    "ma_spread": ma_spread, "vol_ratio": vol_dry_ratio,
                    "is_rs_strong": is_rs_strong, "is_vol_dry": is_vol_dry, "is_uptrend": is_uptrend,
                    "rs_5d": rs_5d, "rs_30d": rs_30d, "rs_144d": rs_144d, "b_sym": b_sym
                })
            except: pass
    return b_res, results

# --- 新增：带有深度诊断的独立研报页 ---
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
            
            tags = []
            if s['ma_spread'] < 0.05: tags.append("<span style='background:#fef08a; color:#854d0e; padding:3px 6px; border-radius:4px;'>🎯 均线极度粘合</span>")
            if s['is_rs_strong']: tags.append("<span style='background:#dcfce7; color:#166534; padding:3px 6px; border-radius:4px;'>🛡️ 30日RS硬核托底</span>")
            if s['is_vol_dry']: tags.append("<span style='background:#e0e7ff; color:#3730a3; padding:3px 6px; border-radius:4px;'>🤫 成交量极度萎缩</span>")
            if s['is_uptrend']: tags.append("<span style='background:#dbeafe; color:#1e40af; padding:3px 6px; border-radius:4px;'>⛰️ 处于长线之上</span>")
            
            tags_html = " ".join(tags) if tags else "<span style='color:#64748b;'>未检测到明显吸筹特征</span>"
            dev_288 = ((price - ma288) / ma288 * 100) if ma288 > 0 else 0

            # 渲染全新的多周期 RS 面板
            c_rs5 = "#dc3545" if s['rs_5d'] < 0 else "#28a745"
            c_rs30 = "#dc3545" if s['rs_30d'] < 0 else "#28a745"
            c_rs144 = "#dc3545" if s['rs_144d'] < 0 else "#28a745"

            st.markdown(f"""
            <div style='background:#ffffff; border:1.5px solid #e2e8f0; padding:12px; border-radius:8px; margin-top:10px;'>
                <div style='margin-bottom:8px; font-size:0.95rem;'><b>主力行为：</b> {tags_html}</div>
                <div style='margin-bottom:8px; font-size:0.9rem; color:#475569;'>偏离 288日均线: <b style='color:{"#dc3545" if dev_288 < 0 else "#28a745"};'>{dev_288:+.2f}%</b> (量缩比: {s['vol_ratio']:.2f})</div>
                
                <div style='display:flex; justify-content:space-between; align-items:center; background:#f8fafc; padding:8px; border-radius:6px; margin-bottom:8px;'>
                    <span style='font-size:0.85rem; color:#64748b; font-weight:bold;'>对比基准: {s['b_sym']}</span>
                    <span style='font-size:0.9rem;'>RS 5日: <b style='color:{c_rs5};'>{s['rs_5d']:+.1f}%</b></span>
                    <span style='font-size:0.9rem;'>RS 30日: <b style='color:{c_rs30};'>{s['rs_30d']:+.1f}%</b></span>
                    <span style='font-size:0.9rem;'>RS 144日: <b style='color:{c_rs144};'>{s['rs_144d']:+.1f}%</b></span>
                </div>

                <div style='display:flex; justify-content:space-between; font-size:0.9rem; color:#475569; font-family:monospace;'>
                    <span>MA5: <b>${ma5:.2f}</b></span> | <span>MA12: <b>${ma12:.2f}</b></span> | <span>MA30: <b>${ma30:.2f}</b></span> | <span>MA144: <b>${ma144:.2f}</b></span> | <span>MA288: <b>${ma288:.2f}</b></span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.divider()
    current_note = st.session_state.my_notes.get(ticker, "")
    col_edit, col_preview = st.columns([1, 1])
    with col_edit:
        new_note = st.text_area(f"撰写 {ticker} 的博弈逻辑：", value=current_note, height=500)
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
    st.title("🏛️ 2026 战略资产终端 (多周期引擎)")
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
        st.subheader("🏆 战力排行榜")
        rank_tabs = st.tabs(["日内", "5日", "144d", "288d", "🎯 潜伏"])
        rank_keys = [('change', '今日'), ('t_5d', '5日'), ('t_144d', '144d'), ('t_288d', '288d')]
        
        with st.container(height=900): 
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
            
            with rank_tabs[4]:
                st.markdown("<small style='color:#64748b;'>* 扫描多均线粘合，且 5日/30日 必须双重跑赢大盘的硬核标的</small>", unsafe_allow_html=True)
                
                sniper_list = []
                for x in m_res:
                    if x['ma_spread'] < 0.05: 
                        score = 0
                        if x['is_rs_strong']: score += 1
                        if x['is_vol_dry']: score += 1
                        if x['is_uptrend']: score += 1
                        
                        if score >= 2:
                            x['sniper_score'] = score
                            sniper_list.append(x)
                
                sniper_list = sorted(sniper_list, key=lambda x: (x['sniper_score'], x['rs_30d']), reverse=True)
                
                if not sniper_list:
                    st.info("目前没有满足严苛吸筹条件的标的。保持耐心。")
                else:
                    for j, item in enumerate(sniper_list):
                        c_rank, c_val = st.columns([2.5, 1.5])
                        with c_rank:
                            if st.button(f"🎯 {item['ticker']}", key=f"rk_coil_{item['ticker']}"):
                                st.session_state.selected_stock = item['ticker']
                                st.session_state.current_page = "StockPage"
                                st.rerun()
                        with c_val:
                            stars = "⭐" * item['sniper_score']
                            st.markdown(f"<div style='text-align:right; color:#854d0e; font-size:0.8rem; padding-top:6px;'>{stars}</div>", unsafe_allow_html=True)
                        st.markdown("<hr style='margin:0; border:none; border-bottom:1px solid #f1f5f9;'>", unsafe_allow_html=True)