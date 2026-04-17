import os
import json
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 全量配置管理：强耦合清单与文档 ---
CONFIG_FILE = "strategy_terminal_v6_total.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    
    # 核心：根据您的 CSV 和 Word 文档生成的全量初始字典
    return {
        "sectors": {
            "量子": ["SKYT", "IONQ", "RGTI", "QBTS", "QUBT", "LAES", "XNDU"],
            "能源稀土": ["LAC", "MP", "USAR", "ALOY", "UAMY", "UUUU", "NEXA", "NB", "OKLO", "SMR", "BWXT", "CEG", "VST", "CW"],
            "军工国防": ["ESP", "KTOS", "PKE", "PLTR", "BBAI", "FLY", "LUNR", "RDW", "DCO", "KRMN", "DRS", "TXT", "TDY", "MRCY"],
            "半导体": ["ADI", "NVMI", "SIMO", "FN", "SWKS", "AAOI", "SITM", "RMBS", "AMKR", "LSCC", "MTSI", "TSEM", "WOLF", "VICR"],
            "数字媒体": ["RDVT", "TRAK", "OPRA", "MGNI"],
            "AI算力/应用": ["ADEA", "EXLS", "ANET", "DGII", "AEHR", "SOUN", "CRDO", "HUBS", "PEGA"],
            "电力基建": ["IESC", "BELFA", "ITRI", "ESE", "FSLR", "AROC", "LNG", "KGS", "HUBB"],
            "航空/维修": ["VSEC", "TATT", "YSS", "FTAI", "AXON", "HEI", "AIR", "LOAR", "ISSC", "ATRO"],
            "通信/新能": ["VEON", "DY", "EOSE", "ENVX", "QS", "KULR", "SLDP"],
            "自动驾驶": ["INDI", "ARBE", "PDYN"]
        },
        "benchmarks": {
            "量子": "QTUM", "能源稀土": "URA", "军工国防": "ITA", "半导体": "SOXX", 
            "数字媒体": "XLC", "AI算力/应用": "IGV", "电力基建": "XLI", "航空/维修": "XAR"
        },
        "notes": {
            # --- 以下内容全量提取自您的《股票介绍.docx》 ---
            "CRDO": "算力网络‘神经纤维’。命门在 800G/1.6T 升级周期。只要 TTM 营收年增率保持在 40% 以上即为强势。",
            "HUBS": "SMB 数字大脑。Breeze AI 驱动 AI Agents 转型，‘按效果付费’颠覆传统 SaaS 订阅模式。",
            "PEGA": "企业级 AI 重装装甲。LPA 自动引擎，Rule of 40 俱乐部成员，高毛利高粘性。",
            "VICR": "GPU 供血泵。VPD 垂直供电解决 1000W+ 功耗瓶颈，EPS 弹性极大，288日周期处于上升段。",
            "ADEA": "AI 基础协议领主。IP 授权模式，边际成本极低，与 AMD 和解后进入估值重构期。",
            "ANET": "数字交通部。以太网架构对 InfiniBand 的平稳替代，数据中心扩产的刚需标的。",
            "NVMI": "物理量测垄断者。光学计量领导者，服务收入占比高，属于‘税收型’防御资产。",
            "SWKS": "新质生产力心脏。智能城市通讯模块，处于果链依赖向 5G/AI 基建转型的深坑修复期。",
            "LUNR": "地月物流总包。掌握 9 亿订单，2026 营收翻 5 倍，正构建地月空间数据网络。",
            "FLY": "中轻型运力。‘蓝鬼’登月成功确立其稀缺性，SpaceX 的唯一民营备份。",
            "YSS": "卫星标准化产线。卫星界的台积电，S-CLASS 平台打破定制化魔咒，实现星座暴力部署。",
            "RDW": "太空工厂。唯一能提供 iROSA 柔性太阳翼和微重力 3D 打印，量子安全卫星物理层。",
            "XNDU": "量子算力先锋。虽然 P/S 极高，但靠‘Aurora’和主权级合同支撑起 2029 容错量子预期。",
            "MRCY": "防御 AI 算力核心。困境反转，FCF 转正，掌握高超音速导弹追踪的边缘大脑。",
            "TDY": "全能物理视网膜。Teledyne Space 整合完成，掌握深海到深空的 1.6T 感测核心。",
            "AXON": "公共安全 OS。AI Assistant 执法逻辑，软件订阅占比突破 40%，$400 为核心支撑。",
            "DCO": "导弹电子神经。彻底去波音化，掌握 11 亿积压订单，受益全球补库大年。",
            "CW": "防御翻译官。边缘 5G 路由领主，解决战场极端环境下的 AI 数据通信链路。",
            "BWXT": "核能心脏。垄断海军堆，‘Pele 计划’微堆即将临界运行，数据中心脱网能源终极期权。",
            "FTAI": "算力救急电源。退役航发改地面涡轮，直供数据中心，Q4 交付为关键奇点。",
            "DRS": "海军电气化先锋。哥伦比亚级核潜艇超静音电机供应商，激光武器电源管理唯一解。",
            "KTOS": "可消耗无人机领主。XQ-58A 量产元年，将‘精英防务’降维打击为‘低成本饱和攻击’。",
            "TXT": "垂直起降霸权。V-280 正式命名确立未来 20 年更新周期，重型机器人投送平台。",
            "HEI": "航空零件影子领主。PMA 模式在 2026 高通胀下无敌，通过收购天线资产切入电子战。",
            "AIR": "航材分销之王。Trax 平台普及带动毛利暴击，资产轻量化转型成功的典范。",
            "ATRO": "机舱智能化。Qi2 无线充电和 100W USB-C 换代潮唯一受益者，订单积压创新高。",
            "KRMN": "高超音速母机。垂直整合复合材料与弹药底座，海陆空天全域统治力。",
            "BKSY": "空间侦察大脑。Gen-3 卫星 90 分钟自动交付，主权级订阅制收益，高频情报 OS。",
            "LOAR": "利基零件领主。40% EBITDA 利润率，并购垄断策略极佳，通胀转嫁能力强。",
            "ISSC": "防御电子专家。为导弹和卫星提供关键互联部件，订单随地缘波动非线性爆发。"
        }
    }

def save_config():
    cfg = {"sectors": st.session_state.my_sectors, "benchmarks": st.session_state.my_benchmarks, "notes": st.session_state.my_notes}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=4)

# --- 2. 界面渲染逻辑 ---
st.set_page_config(page_title="2026 战略终端 (Total Notes)", layout="wide")
st_autorefresh(interval=300000, key="refresh_all")

if 'my_sectors' not in st.session_state:
    cfg = load_config()
    st.session_state.my_sectors = cfg["sectors"]
    st.session_state.my_benchmarks = cfg["benchmarks"]
    st.session_state.my_notes = cfg.get("notes", {})

@st.cache_data(ttl=600)
def fetch_all(sectors, benchmarks):
    all_t = list(set([t for ts in sectors.values() for t in ts]))
    all_b = list(set(benchmarks.values()))
    data = yf.download(all_t + all_b, period="2y", interval="1d", group_by='ticker', progress=False)
    results, b_res = [], {}
    for b in all_b:
        try:
            h = data[b].dropna()
            b_res[b] = {"chg": ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100}
        except: b_res[b] = {"chg": 0.0}
    for s_name, ts in sectors.items():
        b_chg = b_res.get(benchmarks.get(s_name), {"chg": 0})["chg"]
        for t in ts:
            try:
                h = data[t].dropna()
                if h.empty: continue
                price = float(h['Close'].iloc[-1])
                chg = ((price - float(h['Close'].iloc[-2])) / float(h['Close'].iloc[-2])) * 100
                results.append({
                    "ticker": t, "sector": s_name, "price": price, "change": chg, "rs": chg - b_chg,
                    "t_144d": ((price - float(h['Close'].iloc[-145]))/float(h['Close'].iloc[-145]))*100 if len(h)>=145 else 0,
                    "t_288d": ((price - float(h['Close'].iloc[0]))/float(h['Close'].iloc[0]))*100 if len(h)>=288 else 0
                })
            except: pass
    return results

# 数据展示
m_res = fetch_all(st.session_state.my_sectors, st.session_state.my_benchmarks)

st.title("🏛️ 2026 战略终端：物理底座与 AI 新秩序")
with st.sidebar:
    if st.button("🔄 同步 100+ 标的数据"): st.cache_data.clear(); st.rerun()
    st.divider()
    edit_t = st.selectbox("编辑博弈笔记", sorted(st.session_state.my_notes.keys()))
    st.session_state.my_notes[edit_t] = st.text_area("修改逻辑", value=st.session_state.my_notes.get(edit_t, ""), height=150)
    if st.button("💾 保存配置"): save_config()

# 按板块分栏展示
tabs = st.tabs(list(st.session_state.my_sectors.keys()))
for i, s_name in enumerate(st.session_state.my_sectors.keys()):
    with tabs[i]:
        stocks = [x for x in m_res if x['sector'] == s_name]
        for s in stocks:
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 2, 1])
                c1.metric(s['ticker'], f"${s['price']:.2f}", f"{s['change']:+.2f}%")
                c2.info(f"**博弈笔记：** {st.session_state.my_notes.get(s['ticker'], '正在根据 CSV 名单等待深度补全...')}")
                c3.write(f"Alpha: {s['rs']:+.2f}%")
                c3.progress(min(max((s['t_288d']+100)/200, 0.0), 1.0), text=f"288日战力: {s['t_288d']:+.1f}%")