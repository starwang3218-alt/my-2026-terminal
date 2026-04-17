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
CONFIG_FILE = "strategy_terminal_ultra_pro_v24.json"

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
            "全球供应链": ["RBNE"], 
            "沙盘推演": ["ELPW"] 
        },
        "benchmarks": {
            "量子": "QTUM", "能源稀土": "URA", "军工国防": "ITA", "半导体": "SOXX", 
            "数字媒体": "XLC", "AI算力/应用": "IGV", "电力基建": "XLI", "航空精工/维修": "XAR", "全球供应链": "SPY", "沙盘推演": "SPY"
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
def fetch_raw_data(all_tickers):
    return yf.download(all_tickers, period="2y", interval="1d", group_by='ticker', progress=False)

def compute_all_metrics(sectors, benchmarks, full_data, def_win):
    results, b_res, b_history = [], {}, {}
    all_bench = list(set(benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM", "SPY"})
    
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
        b_ret_30_today = get_return(b_h, 30) if b_h is not None else 0
        # 计算基准昨日的30日收益，用于判定RS金叉
        b_ret_30_yesterday = get_return(b_h.iloc[:-1], 30) if (b_h is not None and len(b_h)>31) else 0
        b_ret_144 = get_return(b_h, 144) if b_h is not None else 0

        for t in tickers:
            try:
                h = full_data[t].dropna().copy()
                if len(h) < 32: continue 
                
                price = to_scalar(h['Close'].iloc[-1])
                s_ret_1 = get_return(h, 1)
                s_ret_5 = get_return(h, 5)
                s_ret_30_today = get_return(h, 30)
                # 计算个股昨日的30日收益
                s_ret_30_yesterday = get_return(h.iloc[:-1], 30)
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

                rs_1d = s_ret_1 - b_ret_1
                rs_5d = s_ret_5 - b_ret_5
                rs_30_today = s_ret_30_today - b_ret_30_today
                rs_30_yesterday = s_ret_30_yesterday - b_ret_30_yesterday
                rs_144d = s_ret_144 - b_ret_144
                
                is_rs_strong = (rs_5d > 0) and (rs_30_today > 0)
                is_vol_dry = vol_dry_ratio < 0.8
                is_uptrend = price > to_scalar(h['MA144'].iloc[-1]) if len(h)>=144 else False
                
                # --- 核心新增：判定 RS 30d 零轴金叉 ---
                is_rs_gold_cross = (rs_30_yesterday <= 0) and (rs_30_today > 0)

                defense_rate = 0.0
                if b_h is not None and len(h) >= def_win and len(b_h) >= def_win:
                    s_daily_returns = h['Close'].tail(def_win + 1).pct_change().dropna()
                    b_daily_returns = b_h['Close'].tail(def_win + 1).pct_change().dropna()
                    common_idx = s_daily_returns.index.intersection(b_daily_returns.index)
                    s_aligned = s_daily_returns.loc[common_idx]
                    b_aligned = b_daily_returns.loc[common_idx]
                    down_days_mask = b_aligned < 0
                    total_down_days = down_days_mask.sum()
                    if total_down_days > 0:
                        outperform_down_days = (s_aligned[down_days_mask] > b_aligned[down_days_mask]).sum()
                        defense_rate = (outperform_down_days / total_down_days) * 100

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
                    "rs_5d": rs_5d, "rs_30d": rs_30_today, "rs_30d_prev": rs_30_yesterday, "rs_144d": rs_144d, "b_sym": b_sym,
                    "defense_rate": defense_rate, "is_rs_gold_cross": is_rs_gold_cross,
                    "full_hist": h.tail(300), "b_hist": b_h.tail(300) if b_h is not None else None
                })
            except: pass
    return b_res, results

def find_ignition_points(h, b_h):
    if b_h is None or len(h) < 144: return []
    try:
        idx = h.index.intersection(b_h.index)
        hist = h.loc[idx].copy()
        b_hist = b_h.loc[idx].copy()
        hist['RS_30_hist'] = (hist['Close'].pct_change(30) - b_hist['Close'].pct_change(30)) * 100
        hist['Vol_Ratio_hist'] = hist['Volume'].rolling(5).mean() / hist['Volume'].rolling(30).mean()
        ma_cols = ['MA5', 'MA12', 'MA30', 'MA144']
        hist['MA_Max'] = hist[ma_cols].max(axis=1)
        hist['MA_Min'] = hist[ma_cols].min(axis=1)
        hist['Spread_hist'] = (hist['MA_Max'] - hist['MA_Min']) / hist['MA_Min']
        ignitions = []
        for i in range(144, len(hist)):
            vol_spike = hist['Vol_Ratio_hist'].iloc[i] > 1.5
            rs_turned = hist['RS_30_hist'].iloc[i] > 0
            tight_yesterday = hist['Spread_hist'].iloc[i-1] < 0.1
            up_trend = hist['Close'].iloc[i] > hist['MA144'].iloc[i]
            if vol_spike and rs_turned and tight_yesterday and up_trend:
                ignitions.append({"Date": hist.index[i].strftime('%Y-%m-%d'), "Price": float(hist['Close'].iloc[i]), "Vol_Ratio": float(hist['Vol_Ratio_hist'].iloc[i]), "RS_30": float(hist['RS_30_hist'].iloc[i])})
        filtered = []
        last_dt = None
        for ig in ignitions:
            dt_obj = datetime.strptime(ig['Date'], '%Y-%m-%d')
            if last_dt is None or (dt_obj - last_dt).days > 20: filtered.append(ig); last_dt = dt_obj
        return filtered[-5:]
    except: return []

def render_stock_page(ticker, m_res, def_win):
    st.button("⬅️ 返回战略大盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    s = next((x for x in m_res if x['ticker'] == ticker), None)
    if not s: st.error("⚠️ 数据加载失败。"); return
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
                        st.markdown(f"<div style='text-align:center; border: 1.5px solid #e2e8f0; padding: 10px; border-radius: 10px; background-color: #f8fafc; margin: 2px;'><small style='color:#64748b;'>{dt_str}</small><br><b style='color:{color}; font-size: 1.4rem;'>{d_chg:+.1f}%</b><br><small style='font-weight:bold; font-size: 1.1rem;'>${cur:.1f}</small></div>", unsafe_allow_html=True)
            st.markdown(f"<div style='background:#f1f5f9; padding:10px; border-radius:8px; margin-top:15px; font-size:1rem; border-left:4px solid #3b82f6;'><b>5日累积: {s['t_5d']:+.2f}%</b> | 144日: <b>{s['t_144d']:+.1f}%</b> | 288日战力: <b>{s['t_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
            ma5, ma12, ma30, ma144, ma288, price = s['ma5'], s['ma12'], s['ma30'], s['ma144'], s['ma288'], s['price']
            tags = []
            if s['ma_spread'] < 0.05: tags.append("<span style='background:#fef08a; color:#854d0e; padding:3px 6px; border-radius:4px;'>🎯 均线粘合</span>")
            if s['is_rs_strong']: tags.append("<span style='background:#dcfce7; color:#166534; padding:3px 6px; border-radius:4px;'>🛡️ RS硬核托底</span>")
            if s['is_vol_dry']: tags.append("<span style='background:#e0e7ff; color:#3730a3; padding:3px 6px; border-radius:4px;'>🤫 成交量萎缩</span>")
            if s['is_uptrend']: tags.append("<span style='background:#dbeafe; color:#1e40af; padding:3px 6px; border-radius:4px;'>⛰️ 长线之上</span>")
            tags_html = " ".join(tags) if tags else "<span style='color:#64748b;'>未检测到明显特征</span>"
            dev_288 = ((price - ma288) / ma288 * 100) if ma288 > 0 else 0
            c_rs5, c_rs30, c_rs144 = ("#28a745" if s['rs_5d']>=0 else "#dc3545"), ("#28a745" if s['rs_30d']>=0 else "#dc3545"), ("#28a745" if s['rs_144d']>=0 else "#dc3545")
            c_def = "#28a745" if s['defense_rate'] >= 60 else ("#854d0e" if s['defense_rate'] >= 40 else "#dc3545")
            html_content = f"""<div style='background:#ffffff; border:1.5px solid #e2e8f0; padding:12px; border-radius:8px; margin-top:10px;'><div style='margin-bottom:8px; font-size:0.95rem;'><b>主力行为：</b> {tags_html}</div><div style='margin-bottom:8px; font-size:0.9rem; color:#475569;'>偏离 288日均线: <b style='color:{"#dc3545" if dev_288 < 0 else "#28a745"};'>{dev_288:+.2f}%</b> (量缩比: {s['vol_ratio']:.2f})</div><div style='display:flex; justify-content:space-between; align-items:center; background:#f8fafc; padding:8px; border-radius:6px; margin-bottom:8px;'><span style='font-size:0.85rem; color:#64748b; font-weight:bold;'>基准: {s['b_sym']}</span><span style='font-size:0.9rem;'>逆风护盘率 ({def_win}日): <b style='color:{c_def}; background:#f1f5f9; padding:2px 4px; border-radius:4px;'>{s['defense_rate']:.0f}%</b></span><span style='font-size:0.9rem;'>RS 5日: <b style='color:{c_rs5};'>{s['rs_5d']:+.1f}%</b></span><span style='font-size:0.9rem;'>RS 30日: <b style='color:{c_rs30};'>{s['rs_30d']:+.1f}%</b></span><span style='font-size:0.9rem;'>RS 144日: <b style='color:{c_rs144};'>{s['rs_144d']:+.1f}%</b></span></div><div style='display:flex; justify-content:space-between; font-size:0.9rem; color:#475569; font-family:monospace;'><span>MA5: <b>${ma5:.2f}</b></span> | <span>MA12: <b>${ma12:.2f}</b></span> | <span>MA30: <b>${ma30:.2f}</b></span> | <span>MA144: <b>${ma144:.2f}</b></span> | <span>MA288: <b>${ma288:.2f}</b></span></div></div>"""
            st.markdown(html_content, unsafe_allow_html=True)
    st.divider()
    col_hist, col_edit = st.columns([1, 1])
    with col_hist:
        st.markdown("### ⏳ 历史起爆点回测 (时光机)")
        ignitions = find_ignition_points(s['full_hist'], s['b_hist'])
        if ignitions:
            for ig in ignitions:
                st.markdown(f"<div style='border-left: 4px solid #f59e0b; background:#fffbeb; padding: 10px; border-radius: 4px; margin-bottom: 8px;'><b style='color:#b45309;'>点火日: {ig['Date']}</b> <br><span style='font-size:0.9rem; color:#475569;'>突破发车价: <b>${ig['Price']:.2f}</b></span> | <span style='font-size:0.9rem; color:#475569;'>资金爆量: <b>{ig['Vol_Ratio']:.1f}倍</b></span> | <span style='font-size:0.9rem; color:#28a745;'>RS转强: <b>+{ig['RS_30']:.1f}%</b></span></div>", unsafe_allow_html=True)
            st.success(f"📈 自最初起爆点 (${ignitions[0]['Price']:.2f}) 至今，该股已拉升 **{((s['price']-ignitions[0]['Price'])/ignitions[0]['Price'])*100:+.1f}%**。")
        else: st.info("🕒 过去 300 天内未扫描到完美的『平地起爆』信号。")
    with col_edit:
        st.markdown("### 📝 博弈逻辑与剧本")
        new_note = st.text_area(f"撰写 {ticker} 的交易剧本：", value=st.session_state.my_notes.get(ticker, ""), height=250)
        if st.button("💾 保存解析内容"): st.session_state.my_notes[ticker] = new_note; save_config(); st.success("✅ 笔记已保存！")

# --- 3. 界面布局 ---
with st.sidebar:
    st.header("⚙️ 终端管理")
    if st.button("🚀 刷新全量网络数据", type="primary", use_container_width=True): st.cache_data.clear(); st.rerun()
    st.divider()
    st.subheader("🛡️ 雷达参数设定")
    def_win = st.slider("逆风护盘统计周期 (天)", 10, 60, 30, 5)
    with st.expander("📁 板块编辑"):
        target_s = st.selectbox("当前板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("添加代码")
        if st.button("➕ 添加"):
            if nt: st.session_state.my_sectors[target_s].append(nt.upper()); save_config(); st.rerun()

all_tickers_flat = list(set([t for ts in st.session_state.my_sectors.values() for t in ts]))
all_bench_flat = list(set(st.session_state.my_benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM", "SPY"})
full_raw_data = fetch_raw_data(list(set(all_tickers_flat + all_bench_flat)))
b_res, m_res = compute_all_metrics(st.session_state.my_sectors, st.session_state.my_benchmarks, full_raw_data, def_win)

if st.session_state.current_page == "StockPage":
    render_stock_page(st.session_state.selected_stock, m_res, def_win)
else:
    st.title("🏛️ 2026 战略资产终端 (时光机引擎版)")
    r_cols = st.columns(len(b_res))
    for i, (sym, val) in enumerate(b_res.items()):
        with r_cols[i]: st.metric(sym, f"{val['chg']:+.2f}%")
    st.divider()
    l_col, r_col = st.columns([3.5, 1.5])
    with l_col:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                for s in [x for x in m_res if x['sector'] == s_name]:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1.5, 4.5, 0.5])
                        with c1: st.metric(s['ticker'], f"${s['price']:.2f}", f"{s['change']:+.2f}%"); st.link_button("📈 K线", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
                        with c2:
                            h_cols = st.columns(5); hist_len = len(s['history'])
                            for idx in range(1, 6):
                                with h_cols[idx-1]:
                                    if idx < hist_len:
                                        cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                        d_chg, color = (((cur - pre) / pre) * 100 if pre != 0 else 0), ("#28a745" if cur>=pre else "#dc3545")
                                        st.markdown(f"<div style='text-align:center; border: 1px solid #e2e8f0; padding: 5px; border-radius: 8px;'><small>{s['history'].index[idx].strftime('%m-%d')}</small><br><b style='color:{color};'>{d_chg:+.1f}%</b></div>", unsafe_allow_html=True)
                            st.markdown(f"<div style='background:#f1f5f9; padding:8px; border-radius:5px; margin-top:10px;'>5日累积: {s['t_5d']:+.2f}% | 144日: {s['t_144d']:+.1f}%</div>", unsafe_allow_html=True)
                        with c3:
                            if st.button("🗑️", key=f"del_{s['ticker']}"): st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()
    with r_col:
        st.subheader("🏆 战力排行榜")
        # --- 核心更新：新增了 🚨 预警 标签页 ---
        rank_tabs = st.tabs(["🚨 预警", "日内", "5日", "🛡️ 护盘", "🎯 潜伏"])
        with rank_tabs[0]:
            st.markdown("<small style='color:#64748b;'>* 过去24h内 30日RS 由负转正的标的</small>", unsafe_allow_html=True)
            alerts = [x for x in m_res if x['is_rs_gold_cross']]
            if not alerts: st.info("今日无 RS 零轴金叉信号。")
            else:
                for x in alerts:
                    if st.button(f"🔥 {x['ticker']} (RS: {x['rs_30d']:+.1f}%)", key=f"alert_{x['ticker']}", use_container_width=True):
                        st.session_state.selected_stock = x['ticker']; st.session_state.current_page = "StockPage"; st.rerun()
        with rank_tabs[1]:
            for i, item in enumerate(sorted(m_res, key=lambda x: x['change'], reverse=True)):
                if st.button(f"{i+1}. {item['ticker']} {item['change']:+.1f}%", key=f"rk_c_{item['ticker']}"): st.session_state.selected_stock = item['ticker']; st.session_state.current_page = "StockPage"; st.rerun()
        with rank_tabs[3]:
            for i, item in enumerate(sorted(m_res, key=lambda x: x['defense_rate'], reverse=True)):
                if st.button(f"{i+1}. {item['ticker']} {item['defense_rate']:.0f}%", key=f"rk_d_{item['ticker']}"): st.session_state.selected_stock = item['ticker']; st.session_state.current_page = "StockPage"; st.rerun()
        with rank_tabs[4]:
            sniper_list = sorted([x for x in m_res if x['ma_spread'] < 0.05], key=lambda x: x['defense_rate'], reverse=True)
            for i, item in enumerate(sniper_list):
                if st.button(f"🎯 {item['ticker']}", key=f"rk_coil_{item['ticker']}"): st.session_state.selected_stock = item['ticker']; st.session_state.current_page = "StockPage"; st.rerun()