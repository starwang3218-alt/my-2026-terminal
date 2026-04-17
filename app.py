import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. UI 配置 ---
st.set_page_config(page_title="2026 战略终端 (V25 Dual Ignition)", layout="wide")
st.markdown("""
<style>
div[data-testid="column"] { margin-bottom: -15px !important; }
div.stButton button {
    min-height: 24px !important; height: 32px !important;
    padding-top: 2px !important; padding-bottom: 2px !important;
    background-color: transparent !important; border: none !important;
    color: #1e293b !important; font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# --- 1. 配置管理 ---
CONFIG_FILE = "strategy_terminal_ultra_pro_v25.json"

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

# --- 2. 核心逻辑 ---
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

# === 核心算法：双重引爆点提取 ===
def find_dual_ignitions(h, b_h):
    if b_h is None or len(h) < 60: return []
    try:
        idx = h.index.intersection(b_h.index)
        hist = h.loc[idx].copy()
        b_hist = b_h.loc[idx].copy()
        
        hist['MA5'] = hist['Close'].rolling(5).mean()
        hist['MA12'] = hist['Close'].rolling(12).mean()
        hist['MA30'] = hist['Close'].rolling(30).mean()
        hist['MA144'] = hist['Close'].rolling(144).mean()
        
        hist['RS_30_hist'] = (hist['Close'].pct_change(30) - b_hist['Close'].pct_change(30)) * 100
        hist['Vol_Ratio_hist'] = hist['Volume'].rolling(5).mean() / hist['Volume'].rolling(30).mean()
        
        ma_cols = ['MA5', 'MA12', 'MA30', 'MA144']
        hist['MA_Max'] = hist[ma_cols].max(axis=1)
        hist['MA_Min'] = hist[ma_cols].min(axis=1)
        hist['Spread_hist'] = (hist['MA_Max'] - hist['MA_Min']) / hist['MA_Min']
        
        ignitions = []
        for i in range(30, len(hist)):
            price_i = hist['Close'].iloc[i]
            vol_i = hist['Vol_Ratio_hist'].iloc[i]
            rs_i = hist['RS_30_hist'].iloc[i]
            
            # --- 模式 A：初次引爆 (平地起惊雷) ---
            if hist['Spread_hist'].iloc[i-1] < 0.12 and vol_i > 1.6 and rs_i > 0 and price_i > hist['MA144'].iloc[i]:
                ignitions.append({"Date": hist.index[i].strftime('%Y-%m-%d'), "Type": "First", "Price": float(price_i), "Vol": vol_i, "RS": rs_i})
                continue
            
            # --- 模式 B：二次引爆 (空中加油再起航) ---
            # 条件：处于主升浪中，前10天缩量横盘(窄幅)，今天放量突破
            if price_i > hist['MA144'].iloc[i] * 1.1:
                local_range = hist['Close'].iloc[i-15:i]
                if not local_range.empty:
                    consolidation = (local_range.max() - local_range.min()) / local_range.min() < 0.12
                    vol_was_dry = hist['Vol_Ratio_hist'].iloc[i-1] < 1.1
                    breakout = price_i > local_range.max()
                    if breakout and vol_i > 1.4 and consolidation and vol_was_dry:
                        ignitions.append({"Date": hist.index[i].strftime('%Y-%m-%d'), "Type": "Secondary", "Price": float(price_i), "Vol": vol_i, "RS": rs_i})

        # 过滤重复信号
        res = []
        last_dt = None
        for ig in ignitions:
            dt_obj = datetime.strptime(ig['Date'], '%Y-%m-%d')
            if last_dt is None or (dt_obj - last_dt).days > 15:
                res.append(ig)
                last_dt = dt_obj
        return res[-5:] 
    except: return []

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
        b_ret_1 = get_return(b_h, 1)
        b_ret_5 = get_return(b_h, 5)
        b_ret_30 = get_return(b_h, 30)
        b_ret_144 = get_return(b_h, 144)

        for t in tickers:
            try:
                h = full_data[t].dropna().copy()
                if len(h) < 30: continue 
                
                price = to_scalar(h['Close'].iloc[-1])
                s_ret_1 = get_return(h, 1)
                s_ret_5 = get_return(h, 5)
                s_ret_30 = get_return(h, 30)
                s_ret_144 = get_return(h, 144)
                
                h['MA5'] = h['Close'].rolling(5).mean(); h['MA12'] = h['Close'].rolling(12).mean()
                h['MA30'] = h['Close'].rolling(30).mean(); h['MA144'] = h['Close'].rolling(144).mean()
                h['MA288'] = h['Close'].rolling(288).mean()
                
                v_ma5 = to_scalar(h['Volume'].rolling(5).mean().iloc[-1])
                v_ma30 = to_scalar(h['Volume'].rolling(30).mean().iloc[-1])
                vol_dry_ratio = (v_ma5 / v_ma30) if v_ma30 > 0 else 1.0

                ma_spread = 999
                if len(h) >= 144:
                    ma_vals = [to_scalar(h['MA5'].iloc[-1]), to_scalar(h['MA12'].iloc[-1]), to_scalar(h['MA30'].iloc[-1]), to_scalar(h['MA144'].iloc[-1])]
                    ma_spread = (max(ma_vals) - min(ma_vals)) / min(ma_vals)

                rs_1d = s_ret_1 - b_ret_1; rs_5d = s_ret_5 - b_ret_5
                rs_30d = s_ret_30 - b_ret_30; rs_144d = s_ret_144 - b_ret_144
                
                # 护城河计算
                defense_rate = 0.0
                if b_h is not None and len(h) >= def_win:
                    s_daily = h['Close'].tail(def_win+1).pct_change().dropna()
                    b_daily = b_h['Close'].pct_change().dropna()
                    common = s_daily.index.intersection(b_daily.index)
                    s_a, b_a = s_daily.loc[common], b_daily.loc[common]
                    down_days = b_a < 0
                    if down_days.sum() > 0:
                        defense_rate = (s_a[down_days] > b_a[down_days]).sum() / down_days.sum() * 100

                results.append({
                    "ticker": t, "sector": sec_name, "price": price, "change": s_ret_1, "rs": rs_1d,
                    "t_5d": s_ret_5, "t_144d": s_ret_144, "ma_spread": ma_spread, "vol_ratio": vol_dry_ratio,
                    "ma5": to_scalar(h['MA5'].iloc[-1]), "ma12": to_scalar(h['MA12'].iloc[-1]),
                    "ma30": to_scalar(h['MA30'].iloc[-1]), "ma144": to_scalar(h['MA144'].iloc[-1]),
                    "ma288": to_scalar(h['MA288'].iloc[-1]) if len(h)>=288 else 0,
                    "rs_5d": rs_5d, "rs_30d": rs_30d, "rs_144d": rs_144d, "b_sym": b_sym,
                    "defense_rate": defense_rate, "full_hist": h.tail(400), "b_hist": b_h.tail(400) if b_h is not None else None
                })
            except: pass
    return b_res, results

# --- 独立研报页 ---
def render_stock_page(ticker, m_res, def_win):
    st.button("⬅️ 返回战略大盘", on_click=lambda: setattr(st.session_state, 'current_page', 'Dashboard'))
    s = next((x for x in m_res if x['ticker'] == ticker), None)
    if not s: return
    
    st.markdown(f"## 🎯 战术锁定：{s['ticker']}")
    
    # 概览面板 (略, 同 V24)
    c1, c2 = st.columns([1, 4])
    with c1:
        st.metric(s['ticker'], f"${s['price']:.2f}", f"{s['change']:+.2f}%")
        st.link_button("📈 K线", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
    with c2:
        ma288 = s['ma288']
        dev_288 = (s['price'] - ma288) / ma288 * 100 if ma288 > 0 else 0
        c_rs30 = "#28a745" if s['rs_30d']>0 else "#dc3545"
        st.markdown(f"""
        <div style='background:#f8fafc; border:1px solid #e2e8f0; padding:15px; border-radius:10px;'>
            <b>偏离288日线: {dev_288:+.1f}%</b> | 30日RS: <b style='color:{c_rs30};'>{s['rs_30d']:+.1f}%</b> | 护盘率: <b>{s['defense_rate']:.0f}%</b><br>
            <small>MA5: ${s['ma5']:.2f} | MA30: ${s['ma30']:.2f} | MA144: ${s['ma144']:.2f}</small>
        </div>
        """, unsafe_allow_html=True)

    st.divider()
    
    # === 核心新模块：双重起爆时光机 ===
    st.markdown("### ⏳ 双重起爆时光机 (回测)")
    ignitions = find_dual_ignitions(s['full_hist'], s['b_hist'])
    if ignitions:
        for ig in ignitions:
            color = "#f59e0b" if ig['Type'] == "First" else "#3b82f6"
            label = "🚀 初次引爆 (Stage 1->2)" if ig['Type'] == "First" else "🔥 二次加速 (Base Breakout)"
            st.markdown(f"""
            <div style='border-left: 5px solid {color}; background:#ffffff; padding: 12px; border-radius: 6px; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);'>
                <b style='color:{color}; font-size:1.1rem;'>{label}</b> | <b>{ig['Date']}</b> <br>
                价格: <b>${ig['Price']:.2f}</b> | 资金放量: <b>{ig['Vol']:.1f}倍</b> | 相对强度: <b style='color:#28a745;'>+{ig['RS']:.1f}%</b>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("未发现明显引爆信号。")

# --- 3. 界面逻辑 ---
with st.sidebar:
    st.header("⚙️ 终端管理")
    if st.button("🚀 刷新全量数据", use_container_width=True): st.cache_data.clear(); st.rerun()
    st.divider()
    def_win = st.slider("护盘统计周期", 10, 60, 30, 5)

all_tickers_flat = list(set([t for ts in st.session_state.my_sectors.values() for t in ts]))
all_bench_flat = list(set(st.session_state.my_benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM", "SPY"})
full_raw_data = fetch_raw_data(list(set(all_tickers_flat + all_bench_flat)))
b_res, m_res = compute_all_metrics(st.session_state.my_sectors, st.session_state.my_benchmarks, full_raw_data, def_win)

if st.session_state.current_page == "StockPage":
    render_stock_page(st.session_state.selected_stock, m_res, def_win)
else:
    # 主面板渲染 (同 V24, 加入新排行榜等)
    st.title("🏛️ 2026 战略资产终端 (V25 双重引爆版)")
    # ... (省略重复的 UI 渲染代码, 保持核心逻辑完整)
    # 此处逻辑与 V24 保持一致，重点在于 StockPage 里的 find_dual_ignitions 调用
    
    # 快速跳转排行榜
    l_col, r_col = st.columns([3, 1])
    with r_col:
        st.subheader("🏆 战力排行")
        tab1, tab2 = st.tabs(["🛡️ 护盘", "🎯 潜伏"])
        with tab1:
            for i, x in enumerate(sorted(m_res, key=lambda k: k['defense_rate'], reverse=True)[:15]):
                if st.button(f"{i+1}. {x['ticker']} ({x['defense_rate']:.0f}%)", key=f"rk_d_{x['ticker']}"):
                    st.session_state.selected_stock = x['ticker']; st.session_state.current_page = "StockPage"; st.rerun()
        with tab2:
            sniper = [x for x in m_res if x['ma_spread'] < 0.12]
            for i, x in enumerate(sorted(sniper, key=lambda k: k['defense_rate'], reverse=True)[:15]):
                if st.button(f"🎯 {x['ticker']}", key=f"rk_s_{x['ticker']}"):
                    st.session_state.selected_stock = x['ticker']; st.session_state.current_page = "StockPage"; st.rerun()

    with l_col:
        tabs = st.tabs(list(st.session_state.my_sectors.keys()))
        for i, s_name in enumerate(st.session_state.my_sectors.keys()):
            with tabs[i]:
                for s in [x for x in m_res if x['sector'] == s_name]:
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        with c1: st.metric(s['ticker'], f"${s['price']:.2f}")
                        with c2: 
                            if st.button(f"查看 {s['ticker']} 深度研报 & 起爆回测", key=f"btn_{s['ticker']}"):
                                st.session_state.selected_stock = s['ticker']; st.session_state.current_page = "StockPage"; st.rerun()