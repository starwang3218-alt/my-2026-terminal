import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 配置管理：100+ 标的与深度笔记强耦合 ---
CONFIG_FILE = "strategy_terminal_ultra_pro.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    
    # 默认初始化：整合 CSV 清单与 Word 解析
    return {
        "sectors": {
            "量子": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源稀土": ["LAC", "MP", "USAR", "ALOY", "UAMY", "UUUU", "NEXA", "NB", "OKLO", "SMR", "BWXT", "CEG", "VST", "CW"],
            "军工国防": ["ESP", "KTOS", "PKE", "PLTR", "BBAI", "FLY", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY"],
            "半导体": ["ADI", "NVMI", "SIMO", "FN", "SWKS", "AAOI", "SITM", "RMBS", "AMKR", "LSCC", "MTSI", "TSEM", "WOLF", "VICR", "TTMI"],
            "数字媒体": ["RDVT", "TRAK", "OPRA", "MGNI"],
            "AI算力/应用": ["ADEA", "EXLS", "ANET", "DGII", "AEHR", "SOUN", "CRDO", "HUBS", "PEGA"],
            "电力基建": ["IESC", "BELFA", "ITRI", "ESE", "FSLR", "AROC", "LNG", "KGS", "HUBB"],
            "航空精工": ["VSEC", "TATT", "YSS", "FTAI", "AXON", "HEI", "AIR", "LOAR", "ISSC", "ATRO"],
            "通信/电池": ["VEON", "DY", "EOSE", "ENVX", "QS", "KULR", "SLDP"],
            "自动驾驶": ["INDI", "ARBE", "PDYN"],
            "金融/系统": ["SEZL", "INTU", "PRGS", "AGYS", "NOW", "ASAN", "LZ", "BKSY", "SNPS"]
        },
        "benchmarks": {
            "量子": "QTUM", "能源稀土": "URA", "军工国防": "ITA", "半导体": "SOXX", 
            "数字媒体": "XLC", "AI算力/应用": "IGV", "电力基建": "XLI", "航空精工": "XAR"
        },
        "notes": {
            "CRDO": "算力网络‘神经纤维’。命门在 800G/1.6T 升级周期。只要 TTM 营收年增率保持 40%+ 即可。",
            "HUBS": "SMB 数字大脑。Breeze AI 驱动 AI Agents，‘按效果付费’颠覆传统 SaaS 模式。",
            "VICR": "GPU 供血泵。VPD 垂直供电解决 1000W+ 功耗瓶颈，EPS 弹性极大。",
            "ADEA": "AI 基础协议领主。IP 授权模式，边际成本极低，估值重构期。",
            "ANET": "数字交通部。以太网架构对 InfiniBand 的平稳替代。",
            "NVMI": "物理量测垄断者。光学计量领导者，服务收入占比高，‘税收型’资产。",
            "SWKS": "新质生产力心脏。智能城市通讯模块，处于深坑修复期。",
            "LUNR": "地月物流总包。掌握 9 亿订单，2026 营收翻 5 倍，构建空间数据网。",
            "MRCY": "防御 AI 算力核心。困境反转，FCF 转正，高超音速追踪大脑。",
            "BWXT": "核能心脏。垄断海军堆，Pele 微堆即将临界，AI 能源终极期权。",
            "FTAI": "算力救急电源。退役航发改地面涡轮，Q4 交付为关键奇点。",
            "LOAR": "利基零件领主。40% EBITDA 利润率，通胀转嫁能力极强。"
        }
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 核心渲染初始化 ---
st.set_page_config(page_title="2026 战略终端 (Ultra Pro)", layout="wide")
st_autorefresh(interval=300000, key="global_refresh")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors, st.session_state.my_benchmarks, st.session_state.my_notes = cfg["sectors"], cfg["benchmarks"], cfg.get("notes", {})

def to_scalar(val):
    if isinstance(val, (pd.Series, pd.DataFrame)):
        return float(val.iloc[0]) if not val.empty else 0.0
    return float(val)

@st.cache_data(ttl=600)
def fetch_all_data(sectors, benchmarks):
    all_tickers = list(set([t for ts in sectors.values() for t in ts]))
    all_bench = list(set(benchmarks.values()) | {"SOXX", "XAR", "ITA", "URA", "XLI", "QTUM"})
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
                if h.empty: continue
                price = to_scalar(h['Close'].iloc[-1])
                prev = to_scalar(h['Close'].iloc[-2])
                day_chg = ((price - prev) / prev) * 100
                results.append({
                    "ticker": t, "sector": sec_name, "price": price, "change": day_chg, "rs": day_chg - b_chg,
                    "t_5d": ((price - to_scalar(h['Close'].iloc[-6]))/to_scalar(h['Close'].iloc[-6]))*100 if len(h)>6 else 0,
                    "t_144d": ((price - to_scalar(h['Close'].iloc[-145]))/to_scalar(h['Close'].iloc[-145]))*100 if len(h)>=145 else 0,
                    "t_288d": ((price - to_scalar(h['Close'].iloc[0]))/to_scalar(h['Close'].iloc[0]))*100 if len(h)>=288 else 0,
                    "history": h.tail(6)
                })
            except: pass
    return b_res, results

# --- 3. 界面布局 ---
st.title("🏛️ 2026 战略终端 (Ultra Pro) - 物理底座全监控")

with st.sidebar:
    st.header("⚙️ 终端管理")
    if st.button("🚀 刷新实时战力"): st.cache_data.clear(); st.rerun()
    
    with st.expander("📁 板块/代码编辑"):
        ns = st.text_input("新增板块")
        nb = st.text_input("对标 ETF")
        if st.button("创建板块"):
            if ns: st.session_state.my_sectors[ns] = []; st.session_state.my_benchmarks[ns] = nb.upper(); save_config(); st.rerun()
        
        target_s = st.selectbox("目标板块", list(st.session_state.my_sectors.keys()))
        nt = st.text_input("新增代码")
        if st.button("添加标的"):
            if nt: st.session_state.my_sectors[target_s].append(nt.upper()); save_config(); st.rerun()

    st.divider()
    all_ts = sorted(list(set([t for ts in st.session_state.my_sectors.values() for t in ts])))
    edit_t = st.selectbox("博弈逻辑记录", all_ts)
    st.session_state.my_notes[edit_t] = st.text_area("核心解析", value=st.session_state.my_notes.get(edit_t, ""), height=150)
    if st.button("💾 永久固化笔记"): save_config()

# 数据获取
b_res, m_res = fetch_all_data(st.session_state.my_sectors, st.session_state.my_benchmarks)

# 顶部雷达
r_cols = st.columns(len(b_res))
for i, (sym, val) in enumerate(b_res.items()):
    with r_cols[i]: st.metric(sym, f"{val['chg']:+.2f}%")

st.divider()

# 主区域排版
l_col, r_col = st.columns([4, 1.2])

with l_col:
    tabs = st.tabs(list(st.session_state.my_sectors.keys()))
    for i, s_name in enumerate(st.session_state.my_sectors.keys()):
        with tabs[i]:
            sector_stocks = [x for x in m_res if x['sector'] == s_name]
            for s in sector_stocks:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([1.5, 4, 0.5])
                    with c1:
                        st.markdown(f"### {s['ticker']}")
                        st.markdown(f"<h2 style='margin:0;'>${s['price']:.2f}</h2>", unsafe_allow_html=True)
                        st.markdown(f"<b style='color:{'#28a745' if s['change']>=0 else '#dc3545'}; font-size:1.2rem;'>{s['change']:+.2f}%</b>", unsafe_allow_html=True)
                        st.link_button("📈 K线链接", f"https://www.tradingview.com/chart/?symbol={s['ticker']}")
                    
                    with c2:
                        # 五日涨跌幅 K 线模拟
                        h_cols = st.columns(5)
                        for idx in range(1, 6):
                            with h_cols[idx-1]:
                                cur, pre = to_scalar(s['history']['Close'].iloc[idx]), to_scalar(s['history']['Close'].iloc[idx-1])
                                d_chg = ((cur - pre) / pre) * 100
                                color = "#28a745" if d_chg >= 0 else "#dc3545"
                                st.markdown(f"<div style='text-align:center;'><small>{s['history'].index[idx].strftime('%m-%d')}</small><br><b style='color:{color};'>{d_chg:+.1f}%</b><br><small>${cur:.1f}</small></div>", unsafe_allow_html=True)
                        
                        st.markdown(f"<div style='background:rgba(0,0,0,0.03); padding:8px; border-radius:5px; margin-top:15px;'><b>5日线: {s['t_5d']:+.2f}%</b> | 144日: <b>{s['t_144d']:+.1f}%</b> | 288日: <b>{s['t_288d']:+.1f}%</b></div>", unsafe_allow_html=True)
                        with st.expander("💡 深度解析"): st.write(st.session_state.my_notes.get(s['ticker'], "等待录入..."))
                    
                    with c3:
                        if st.button("🗑️", key=f"del_{s['ticker']}"):
                            st.session_state.my_sectors[s_name].remove(s['ticker']); save_config(); st.rerun()

with r_col:
    st.subheader("🏆 战力排行")
    rank_tabs = st.tabs(["日内", "5日", "144d", "288d"])
    rank_keys = [('change', '今日'), ('t_5d', '5日'), ('t_144d', '144d'), ('t_288d', '288d')]
    for i, (key, label) in enumerate(rank_keys):
        with rank_tabs[i]:
            sorted_m = sorted(m_res, key=lambda x: x[key], reverse=True)
            for j, item in enumerate(sorted_m[:20]):
                st.markdown(f"{j+1}. **{item['ticker']}** `{item[key]:+.1f}%`")