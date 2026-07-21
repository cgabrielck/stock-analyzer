import json
import shutil
import os
import io
from typing import Any, Dict, List, Optional

import streamlit as st
import pandas as pd
import altair as alt

from utils.constants import (
    STOCK_UNIVERSE,
    SCORING_WEIGHTS,
    SECTOR_CN_MAP,
    SECTOR_EN_MAP,
    SECTOR_TW_MAP,
    VALUATION_LABELS,
    VALUATION_RANGES,
)
from i18n import t

from agents.data_fetcher import fetch_industry_news

CUSTOM_TICKERS_PATH = os.path.join(os.path.dirname(__file__), "data", "custom_tickers.json")
WEIGHT_LABELS: Dict[str, str] = {
    "revenue_growth": "营收增长",
    "eps_growth": "EPS增长",
    "profit_margin": "净利润率",
    "peg_ratio": "PEG比率",
    "roe": "ROE",
    "debt_equity": "负债/权益比",
}


def _load_custom_tickers() -> List[str]:
    try:
        if os.path.exists(CUSTOM_TICKERS_PATH):
            with open(CUSTOM_TICKERS_PATH) as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
    except Exception:
        pass
    return []


def _save_custom_tickers(tickers: List[str]) -> None:
    os.makedirs(os.path.dirname(CUSTOM_TICKERS_PATH), exist_ok=True)
    with open(CUSTOM_TICKERS_PATH, "w") as f:
        json.dump(tickers, f)


def _stock_name(s: Dict[str, Any], lang: str) -> str:
    if lang == "en":
        return s.get("name_en", s.get("longName", s["ticker"]))
    elif lang == "zh_tw":
        return s.get("name_tw", s.get("name_cn", s["ticker"]))
    return s.get("name_cn", s.get("longName", s["ticker"]))


def _sector_name(sec: str, lang: str) -> str:
    if lang == "en":
        return SECTOR_EN_MAP.get(sec, sec)
    elif lang == "zh_tw":
        return SECTOR_TW_MAP.get(sec, sec)
    return SECTOR_CN_MAP.get(sec, sec)


def _inject_apple_css() -> None:
    css = """<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=SF+Pro+Display:wght@400;500;600;700&display=swap');

    * { font-family: -apple-system, 'Inter', 'SF Pro Display', 'Helvetica Neue', sans-serif; }

    .stApp {
        background: #f5f5f7;
    }

    /* ---- Sidebar ---- */
    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #d2d2d7;
        min-width: 260px;
    }
    section[data-testid="stSidebar"] > div {
        padding: 1rem 0.8rem;
    }
    section[data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.82rem;
        font-weight: 500;
    }

    .sidebar-section {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: #86868b;
        margin: 0.8rem 0 0.3rem 0;
    }
    .sidebar-section:first-of-type {
        margin-top: 0;
    }

    .stApp .main {
        max-width: 1200px;
        margin: 0 auto;
        padding: 0.5rem;
    }
    .main > div {
        padding: 1.2rem 1.5rem;
        background: transparent;
        border-radius: 0;
        margin: 0;
    }

    .app-title {
        font-size: 2rem;
        font-weight: 800;
        color: #1d1d1f;
        margin: 0;
    }
    .app-subtitle {
        color: #86868b;
        font-size: 0.9rem;
        font-weight: 500;
        margin: 0.2rem 0 0 0;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #d2d2d7;
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 0.82rem;
        font-weight: 600;
        color: #86868b;
        padding: 0.5rem 1rem;
    }
    .stTabs [aria-selected="true"] {
        color: #0071e3 !important;
    }

    div[data-testid="column"] {
        display: flex;
        flex-direction: column;
    }
    div[data-testid="column"] > div {
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    .rec-card {
        flex: 1;
    }

    .rec-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 0.8rem 0.6rem;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.02);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .rec-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.02);
    }
    .rec-card .rc-rank {
        font-size: 0.65rem;
        font-weight: 700;
        color: #86868b;
        letter-spacing: 0.06em;
        margin: 0;
    }
    .rec-card .rc-ticker {
        font-size: 1.5rem;
        font-weight: 800;
        color: #1d1d1f;
        margin: 2px 0 0;
    }
    .rec-card .rc-name {
        font-size: 0.75rem;
        font-weight: 600;
        color: #86868b;
        margin: 1px 0;
        line-height: 1.2;
    }
    .rec-card .rc-sector {
        font-size: 0.65rem;
        color: #a1a1a6;
        margin: 0 0 6px;
    }
    .rec-card .rc-divider {
        border: none;
        height: 1px;
        background: #e8e8ed;
        margin: 6px 10px;
    }
    .rec-card .rc-price {
        font-size: 1.3rem;
        font-weight: 700;
        color: #1d1d1f;
        margin: 0;
        white-space: nowrap;
    }
    .rec-card .rc-score {
        font-size: 0.75rem;
        font-weight: 600;
        color: #86868b;
        margin: 1px 0 0;
    }

    .feature-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 1rem 0.8rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04), 0 0 0 1px rgba(0,0,0,0.02);
        height: 100%;
    }
    .feature-card h3 {
        font-size: 0.95rem;
        font-weight: 700;
        margin: 0 0 0.2rem;
    }
    .feature-card p {
        font-size: 0.78rem;
        font-weight: 500;
        color: #86868b;
        margin: 0;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e8e8ed;
        border-radius: 10px;
        padding: 0.4rem 0.7rem;
    }
    div[data-testid="stMetric"] > div {
        font-size: 0.65rem;
        font-weight: 600;
        color: #86868b;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1rem;
        font-weight: 800;
        color: #1d1d1f;
    }

    .stExpander {
        border: 1px solid #e8e8ed !important;
        border-radius: 12px !important;
        margin-bottom: 0.5rem;
        background: #ffffff;
    }
    .stExpander summary {
        font-weight: 700;
        font-size: 0.85rem;
        padding: 0.6rem 1rem;
    }

    .stButton > button {
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 10px !important;
        padding: 0.3rem 0.8rem;
        border: none;
    }
    .stButton > button[kind="primary"] {
        background: #0071e3;
        color: #ffffff;
    }
    .stButton > button[kind="secondary"] {
        background: #e8e8ed;
        color: #1d1d1f;
    }

    .stDataFrame {
        border: 1px solid #e8e8ed;
        border-radius: 10px;
        overflow-x: auto;
        font-size: 0.8rem;
    }
    .stDataFrame thead tr th {
        font-size: 0.7rem;
        font-weight: 700;
        color: #86868b;
        text-transform: uppercase;
        padding: 0.4rem 0.6rem;
        background: #f5f5f7;
        border-bottom: 1px solid #e8e8ed;
    }
    .stDataFrame tbody td {
        padding: 0.35rem 0.6rem;
        border-bottom: 1px solid #f0f0f2;
    }

    hr {
        border: none;
        height: 1px;
        background: #e8e8ed;
        margin: 1rem 0;
    }

    .stProgress > div > div > div {
        background: #0071e3 !important;
    }

    .stCheckbox label { font-size: 0.78rem; font-weight: 500; }
    .stSlider label { font-size: 0.72rem; font-weight: 600; color: #1d1d1f; }
    .stSlider [data-baseweb="slider"] > div { background: #d2d2d7 !important; height: 4px !important; }
    .stSlider [data-baseweb="slider"] > div > div { background: #1d1d1f !important; height: 4px !important; }
    .stSlider [data-baseweb="slider"] [role="slider"] { background: #1d1d1f !important; border: 2px solid #fff !important; width: 16px !important; height: 16px !important; }
    .stSlider input[type="number"] { background: #f5f5f7 !important; border: 1px solid #d2d2d7 !important; border-radius: 6px !important; color: #1d1d1f !important; font-size: 0.72rem !important; font-weight: 600 !important; padding: 1px 4px !important; width: 44px !important; max-height: 24px !important; text-align: center !important; }

    .stNumberInput label { font-size: 0.72rem; font-weight: 600; color: #1d1d1f; }
    .stNumberInput > div > div { border-radius: 8px !important; border: 1px solid #d2d2d7 !important; }
    .stNumberInput input { background: #f5f5f7 !important; color: #1d1d1f !important; font-size: 0.8rem !important; }

    .stSelectbox label { font-size: 0.78rem; font-weight: 500; }
    .stSelectbox > div > div { border-radius: 10px; border-color: #e8e8ed; }

    .stAlert { border-radius: 10px; background: #f5f5f7; font-size: 0.85rem; padding: 0.6rem 0.8rem; }
    .stContainer { border: 1px solid #e8e8ed !important; border-radius: 10px !important; background: #ffffff; padding: 0.6rem 0.8rem !important; margin-bottom: 0.4rem; }
    .stCaption { font-size: 0.7rem; color: #a1a1a6; }
    .stock-tag { display: inline-flex; align-items: center; gap: 4px; background: #f5f5f7; border: 1px solid #e8e8ed; border-radius: 16px; padding: 2px 10px; font-size: 0.75rem; font-weight: 600; margin: 2px 3px 2px 0; color: #1d1d1f; }

    @media (max-width: 768px) {
        .main > div { padding: 0.8rem; }
        .app-title { font-size: 1.4rem; }
        div[data-testid="column"] { min-width: 100% !important; flex: 0 0 100% !important; }
        .rec-card { padding: 0.6rem 0.4rem; }
        .rec-card .rc-ticker { font-size: 1.2rem; }
        .rec-card .rc-price { font-size: 1.1rem; }
        .stTabs [data-baseweb="tab"] { font-size: 0.7rem; padding: 0.4rem 0.5rem; }
        .stButton > button { min-height: 44px; font-size: 0.85rem; }
        .stCheckbox label { font-size: 0.85rem; }
        section[data-testid="stSidebar"] { min-width: 0; }
        section[data-testid="stSidebar"] > div { padding: 0.8rem 0.6rem; }
    }

    @media (prefers-color-scheme: dark) {
        .stApp { background: #1c1c1e; }
        section[data-testid="stSidebar"] { background: #2c2c2e; border-right-color: #38383a; }
        .app-title { color: #f5f5f7; }
        .rec-card { background: #2c2c2e; box-shadow: 0 1px 4px rgba(0,0,0,0.2), 0 0 0 1px rgba(255,255,255,0.04); }
        .rec-card .rc-ticker { color: #f5f5f7; }
        .rec-card .rc-price { color: #f5f5f7; }
        .rec-card .rc-name { color: #a1a1a6; }
        .rec-card .rc-divider { background: #38383a; }
        .feature-card { background: #2c2c2e; }
        .feature-card p { color: #a1a1a6; }
        div[data-testid="stMetric"] { background: #2c2c2e; border-color: #38383a; }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #f5f5f7; }
        .stExpander { background: #2c2c2e; border-color: #38383a !important; }
        .stDataFrame { border-color: #38383a; }
        .stDataFrame thead tr th { background: #333336; color: #a1a1a6; border-bottom-color: #38383a; }
        .stDataFrame tbody td { border-bottom-color: #333336; }
        .stContainer { background: #2c2c2e; border-color: #38383a !important; }
        .stock-tag { background: #3a3a3c; border-color: #48484a; color: #f5f5f7; }
        .stTabs [data-baseweb="tab-list"] { border-bottom-color: #38383a; }
        .stButton > button[kind="secondary"] { background: #3a3a3c; color: #f5f5f7; }
        .stSlider label { color: #f5f5f7; }
        .stSlider [data-baseweb="slider"] > div { background: #48484a !important; }
        .stSlider [data-baseweb="slider"] > div > div { background: #f5f5f7 !important; }
        .stSlider [data-baseweb="slider"] [role="slider"] { background: #f5f5f7 !important; border-color: #2c2c2e !important; }
        .stSlider input[type="number"] { background: #3a3a3c !important; border-color: #48484a !important; color: #f5f5f7 !important; }
        section[data-testid="stSidebar"] { background: #2c2c2e; }
        .stSelectbox > div > div { border-color: #48484a; }
    }
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def init_state() -> None:
    if "recommendations" not in st.session_state:
        st.session_state.recommendations: List[Dict[str, Any]] = []
        st.session_state.all_rankings: List[Dict[str, Any]] = []
        st.session_state.scored_data: List[Dict[str, Any]] = []
        st.session_state.source_health: Dict[str, Any] = {}
        st.session_state.upgrade_logs: List[Dict[str, Any]] = []
        st.session_state.analysis_running = False
        st.session_state.analysis_done = False
        st.session_state.custom_tickers: List[str] = _load_custom_tickers()
        st.session_state.lang: str = "zh_tw"
        st.session_state.portfolio: Dict[str, Any] = {}


def build_sidebar() -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    lang = st.session_state.get("lang", "zh_tw")
    selected_lang = lang

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.control", lang)}</div>',
        unsafe_allow_html=True)

    lang_opts = {"zh_cn": "简体中文", "zh_tw": "繁體中文", "en": "English"}
    selected_lang = st.sidebar.selectbox(
        "Language", options=list(lang_opts.keys()),
        format_func=lambda k: lang_opts[k],
        index=list(lang_opts.keys()).index(selected_lang),
        key="lang_selector", label_visibility="collapsed",
    )
    if selected_lang != lang:
        st.session_state.lang = selected_lang
        st.rerun()
    params["lang"] = selected_lang

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.sector_set", selected_lang)}</div>',
        unsafe_allow_html=True)
    st.sidebar.caption(t("sidebar.sector_prompt", selected_lang))

    sectors = sorted(set(s["sector"] for s in STOCK_UNIVERSE))
    all_checked = st.sidebar.checkbox(t("sidebar.select_all", selected_lang), value=True, key="select_all")
    selected_sectors: List[str] = []
    for sec in sectors:
        sec_name = _sector_name(sec, selected_lang)
        checked = st.sidebar.checkbox(
            f"{sec_name}",
            value=all_checked,
            key=f"sector_set_{sec}",
        )
        if checked:
            selected_sectors.append(sec)

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.stock_pool", selected_lang)}</div>',
        unsafe_allow_html=True)

    selected_tickers: List[str] = []
    for sec in sectors:
        if sec not in selected_sectors:
            continue
        sec_name = _sector_name(sec, selected_lang)
        stocks_in_sec = [s for s in STOCK_UNIVERSE if s["sector"] == sec]
        with st.sidebar.expander(f"{sec_name} ({len(stocks_in_sec)})", expanded=False):
            sec_all = st.checkbox(
                t("sidebar.select_sector", selected_lang, sector=sec_name),
                value=True, key=f"sec_{sec}",
            )
            for s in stocks_in_sec:
                s_name = _stock_name(s, selected_lang)
                checked = st.checkbox(
                    f"{s['ticker']} — {s_name}",
                    value=sec_all, key=f"stock_{s['ticker']}",
                )
                if checked:
                    selected_tickers.append(s["ticker"])

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.custom_tickers", selected_lang)}</div>',
        unsafe_allow_html=True)

    bulk_tickers = st.sidebar.text_area(
        t("pool.bulk_add", selected_lang),
        placeholder=t("pool.bulk_placeholder", selected_lang),
        label_visibility="collapsed", key="bulk_custom",
        help=t("pool.bulk_placeholder", selected_lang),
    )
    add_col1, add_col2, add_col3 = st.sidebar.columns([2, 1, 1])
    with add_col1:
        st.caption(t("pool.bulk_add", selected_lang))
    with add_col2:
        add_clicked = st.button(t("sidebar.custom_add", selected_lang), use_container_width=True, key="add_custom_btn")
    with add_col3:
        clear_custom = st.button("🗑", use_container_width=True, key="clear_custom_btn")

    if add_clicked and bulk_tickers.strip():
        extra = [t_.strip().upper() for t_ in bulk_tickers.replace("\n", ",").split(",") if t_.strip()]
        changed = False
        for t_ in extra:
            if t_ and t_ not in st.session_state.custom_tickers:
                st.session_state.custom_tickers.append(t_)
                changed = True
        if changed:
            _save_custom_tickers(st.session_state.custom_tickers)
            st.rerun()

    if clear_custom and st.session_state.custom_tickers:
        st.session_state.custom_tickers = []
        _save_custom_tickers([])
        st.rerun()

    if st.session_state.custom_tickers:
        tags_html = "".join(
            f'<span class="stock-tag">{t_}</span>'
            for t_ in st.session_state.custom_tickers
        )
        st.sidebar.markdown(f"<div style='margin:4px 0;'>{tags_html}</div>", unsafe_allow_html=True)
        for t_ in list(st.session_state.custom_tickers):
            col_a, col_b = st.sidebar.columns([5, 1])
            with col_a:
                st.markdown(f"<span style='font-size:0.75rem;'>{t_}</span>", unsafe_allow_html=True)
            with col_b:
                if st.button("✕", key=f"remove_{t_}", help=t("sidebar.custom_remove", selected_lang), use_container_width=True):
                    st.session_state.custom_tickers.remove(t_)
                    _save_custom_tickers(st.session_state.custom_tickers)
                    st.rerun()

    for t_ in st.session_state.custom_tickers:
        if t_ not in selected_tickers:
            selected_tickers.append(t_)

    if not selected_tickers:
        selected_tickers = [s["ticker"] for s in STOCK_UNIVERSE]
    params["selected_tickers"] = selected_tickers

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.weights", selected_lang)}</div>',
        unsafe_allow_html=True)
    weights: Dict[str, float] = {}
    cols = st.sidebar.columns(2)
    for i, (key, label) in enumerate(WEIGHT_LABELS.items()):
        default_pct = int(SCORING_WEIGHTS[key] * 100)
        with cols[i % 2]:
            val = st.slider(label, 0, 100, default_pct, key=f"w_{key}")
            weights[key] = val / 100.0
    total_w = sum(weights.values())
    st.sidebar.caption(t("sidebar.weight_total", selected_lang, w=total_w))
    params["custom_weights"] = {k: v / total_w for k, v in weights.items()} if total_w > 0 else weights

    st.sidebar.markdown(
        f'<div class="sidebar-section">{t("sidebar.filters", selected_lang)}</div>',
        unsafe_allow_html=True)
    filters: Dict[str, Any] = {}
    filters["min_revenue_growth"] = st.sidebar.number_input(t("sidebar.min_revenue", selected_lang), value=0, key="f_rev")
    filters["max_peg"] = st.sidebar.number_input(t("sidebar.max_peg", selected_lang), value=100, key="f_peg")
    filters["min_roe"] = st.sidebar.number_input(t("sidebar.min_roe", selected_lang), value=0, key="f_roe")
    filters["max_debt_equity"] = st.sidebar.number_input(t("sidebar.max_de", selected_lang), value=100, key="f_de")
    params["filters"] = filters

    use_llm = st.session_state.get("use_llm", False)
    if use_llm:
        st.sidebar.markdown(
            f'<div class="sidebar-section">🤖 LLM {t("sidebar.weights", selected_lang)}</div>',
            unsafe_allow_html=True)
        llm_w = st.sidebar.slider(
            t("sidebar.llm_weight", selected_lang, default=20),
            0, 50, int(getattr(st.session_state, "llm_weight", 20) * 100),
            key="llm_weight_slider",
        )
        st.session_state.llm_weight = llm_w / 100.0
        params["llm_weight"] = llm_w / 100.0
        st.sidebar.caption(t("sidebar.llm_hint", selected_lang))

    st.sidebar.markdown(f'<div class="sidebar-section">📁 {t("portfolio.title", selected_lang)}</div>', unsafe_allow_html=True)
    portfolio_capital = st.sidebar.number_input(
        t("portfolio.capital", selected_lang),
        min_value=1000, max_value=10_000_000, value=100_000, step=10_000,
        key="portfolio_capital",
    )
    params["portfolio_capital"] = portfolio_capital

    st.sidebar.markdown("<hr style='margin:1.2rem 0;'>", unsafe_allow_html=True)
    col1, col2, col3 = st.sidebar.columns([1, 1, 1])
    with col1:
        params["run_clicked"] = st.button(t("sidebar.start", selected_lang), type="primary", use_container_width=True)
    with col2:
        params["force_refresh"] = st.checkbox(t("sidebar.refresh", selected_lang), value=True, key="force_refresh_cb")
    with col3:
        if st.button(t("sidebar.clear_cache", selected_lang), type="secondary", use_container_width=True):
            from utils.cache import cache
            cache_dir = os.path.join(os.path.dirname(__file__), "data", "cache")
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
            for key in ["recommendations", "all_rankings", "source_health", "scored_data"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.analysis_done = False
            st.rerun()

    return params


def show_source_health() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    health = st.session_state.source_health or {}
    if health:
        st.sidebar.markdown(
            f'<div class="sidebar-section">{t("sidebar.source_status", lang)}</div>',
            unsafe_allow_html=True)
        for source, info in sorted(health.items()):
            total = info.get("success", 0) + info.get("failure", 0)
            rate = info.get("success", 0) / total * 100 if total > 0 else 0
            icon = "✅" if rate >= 80 else "⚠️" if rate >= 50 else "❌"
            st.sidebar.markdown(
                f"<div style='font-size:0.7rem;margin:1px 0;'>{icon} {source} — {rate:.0f}%</div>",
                unsafe_allow_html=True)
        from agents.data_fetcher import _SEED_DATA
        _seed_count = len(_SEED_DATA)
        _seed_txt = f"🐢 seed={_seed_count}" if _seed_count else "🐢 seed=0 ⚠️"
        st.sidebar.caption(_seed_txt)
        st.sidebar.caption(t("sidebar.last_update", lang, time=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")))
        st.sidebar.caption(t("sidebar.data_from", lang))
        st.sidebar.caption(t("sidebar.version", lang))


def run_analysis(params: Dict[str, Any]) -> None:
    lang = params.get("lang", "zh_tw")
    st.session_state.analysis_running = True
    progress_bar = st.progress(0, text=t("app.init_engine", lang))
    status_text = st.empty()

    def update_progress(completed: int, total: int) -> None:
        pct = completed / total
        progress_bar.progress(pct)
        status_text.markdown(t("app.fetching", lang, c=completed, t=total))

    from agents.recommender import run_full_analysis

    force_refresh = params.get("force_refresh", False)
    if force_refresh:
        from utils.cache import cache
        for tk in params.get("selected_tickers", []):
            cache.delete(tk, "info")

    results = run_full_analysis(
        progress_callback=update_progress,
        selected_tickers=params.get("selected_tickers"),
        custom_weights=params.get("custom_weights"),
        filters=params.get("filters"),
        lang=lang,
        llm_weight=params.get("llm_weight", 0.2),
        force_refresh=force_refresh,
    )

    progress_bar.empty()
    status_text.empty()

    st.session_state.recommendations = results.get("recommendations", [])
    st.session_state.all_rankings = results.get("all_rankings", [])
    st.session_state.scored_data = results.get("scored_data", [])
    st.session_state.source_health = results.get("source_health", {})
    st.session_state.upgrade_logs = results.get("upgrade_logs", [])
    st.session_state.agent_summary = results.get("agent_summary", {})
    st.session_state.use_llm = results.get("use_llm", False)
    st.session_state.analysis_done = True
    st.session_state.analysis_running = False

    from agents.portfolio_manager import build_portfolio
    st.session_state.portfolio = build_portfolio(
        st.session_state.recommendations,
        total_capital=params.get("portfolio_capital", 100000),
    )

    if results.get("error"):
        st.error(t("app.error", lang, msg=results["error"]))
    else:
        st.success(t("app.complete", lang, n=len(st.session_state.all_rankings)))

    debug_all = results.get("_debug_all_data", {})
    with st.expander("🐛 Debug", expanded=False):
        sd = len(st.session_state.scored_data)
        ad = len(debug_all)
        st.write(f"🔄 Pipeline: selected={len(params.get('selected_tickers', []))} → fetched={ad} → scored={sd} → ranked={len(st.session_state.all_rankings)}")
        if debug_all:
            skipped = []
            for k, v in debug_all.items():
                if "error" in v:
                    skipped.append(f"{k}: error={str(v.get('error',''))[:30]}")
                elif v.get("sector") is None:
                    skipped.append(f"{k}: sector=None")
            if skipped:
                st.error(f"Skipped {len(skipped)} stocks:")
                for s in skipped:
                    st.write(f"  - {s}")
        st.write(f"📊 Health keys: {len(results.get('source_health', {}))}")


def _find_local_extrema(series, window: int = 5):
    local_max = (series == series.rolling(window, center=True).max())
    local_min = (series == series.rolling(window, center=True).min())
    # Expose the first/last points
    return local_max, local_min


def _build_tech_chart(ticker: str, interval: str = "1d", lang: str = "zh_tw") -> Any:
    try:
        import yfinance as yf
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        import pandas as pd
        import numpy as np

        stock = yf.Ticker(ticker)

        interval_map = {
            "1m":  ("1m", "5d"),
            "5m":  ("5m", "1mo"),
            "15m": ("15m", "1mo"),
            "30m": ("30m", "1mo"),
            "60m": ("60m", "2mo"),
            "1d":  ("1d", "1y"),
        }
        yf_interval, yf_period = interval_map.get(interval, ("1d", "1y"))
        is_intraday = yf_interval != "1d"

        if is_intraday:
            hist = stock.history(period=yf_period, interval=yf_interval, prepost=True)
        else:
            hist = stock.history(period=yf_period)

        if hist is None or hist.empty or len(hist) < 10:
            return None

        df = hist.copy()
        df.index = pd.to_datetime(df.index)

        stock_info = stock.info
        current_price = stock_info.get("preMarketPrice") or stock_info.get("postMarketPrice") or stock_info.get("currentPrice") or stock_info.get("regularMarketPrice")
        current_price = float(current_price) if current_price else float(df["Close"].iloc[-1])

        if is_intraday:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.04,
                row_heights=[0.7, 0.3],
                subplot_titles=(ticker, "Volume"),
            )
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"], name="Price",
            ), row=1, col=1)
            fig.add_hline(y=current_price, line_dash="dash", line_color="blue",
                          annotation_text=f"Now ${current_price:.2f}", row=1, col=1)

            vol_colors = ["red" if c < o else "green" for o, c in zip(df["Open"], df["Close"])]
            fig.add_trace(go.Bar(
                x=df.index, y=df["Volume"], name="Volume", marker_color=vol_colors, opacity=0.5,
            ), row=2, col=1)

            local_max, local_min = _find_local_extrema(df["Close"], window=7)
            max_pts = df[local_max]
            min_pts = df[local_min]
            fig.add_trace(go.Scatter(
                x=max_pts.index, y=max_pts["High"], mode="markers",
                marker=dict(symbol="triangle-down", size=10, color="red"),
                name="High",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=min_pts.index, y=min_pts["Low"], mode="markers",
                marker=dict(symbol="triangle-up", size=10, color="green"),
                name="Low",
            ), row=1, col=1)

            fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
            fig.update_xaxes(rangeslider_visible=False, row=2, col=1)
        else:
            df["SMA20"] = df["Close"].rolling(20).mean()
            df["SMA50"] = df["Close"].rolling(50).mean()
            df["EMA20"] = df["Close"].ewm(span=20).mean()
            bb_mid = df["Close"].rolling(20).mean()
            bb_std = df["Close"].rolling(20).std()
            df["BB_upper"] = bb_mid + bb_std * 2
            df["BB_lower"] = bb_mid - bb_std * 2
            delta = df["Close"].diff()
            gain = delta.where(delta > 0, 0.0)
            loss = (-delta).where(delta < 0, 0.0)
            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()
            rs = avg_gain / avg_loss.replace(0, float("nan"))
            df["RSI"] = 100 - (100 / (1 + rs))
            ema_fast = df["Close"].ewm(span=12).mean()
            ema_slow = df["Close"].ewm(span=26).mean()
            df["MACD"] = ema_fast - ema_slow
            df["MACD_signal"] = df["MACD"].ewm(span=9).mean()
            df["MACD_hist"] = df["MACD"] - df["MACD_signal"]

            fig = make_subplots(
                rows=4, cols=1, shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.5, 0.15, 0.15, 0.2],
                subplot_titles=(ticker, "Volume", "RSI(14)", "MACD"),
            )
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"], name="Price",
            ), row=1, col=1)
            fig.add_hline(y=current_price, line_dash="dash", line_color="blue",
                          annotation_text=f"Now ${current_price:.2f}", row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["SMA20"], line=dict(color="orange", width=1), name="SMA20",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["SMA50"], line=dict(color="purple", width=1), name="SMA50",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["EMA20"], line=dict(color="blue", width=1, dash="dot"), name="EMA20",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["BB_upper"], line=dict(color="gray", width=1, dash="dash"), name="BB Upper",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["BB_lower"], line=dict(color="gray", width=1, dash="dash"), name="BB Lower",
            ), row=1, col=1)

            local_max, local_min = _find_local_extrema(df["Close"], window=10)
            max_pts = df[local_max]
            min_pts = df[local_min]
            fig.add_trace(go.Scatter(
                x=max_pts.index, y=max_pts["High"], mode="markers",
                marker=dict(symbol="triangle-down", size=8, color="red"),
                name="High",
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=min_pts.index, y=min_pts["Low"], mode="markers",
                marker=dict(symbol="triangle-up", size=8, color="green"),
                name="Low",
            ), row=1, col=1)

            vol_colors = ["red" if c < o else "green" for o, c in zip(df["Open"], df["Close"])]
            fig.add_trace(go.Bar(
                x=df.index, y=df["Volume"], name="Volume", marker_color=vol_colors, opacity=0.5,
            ), row=2, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["RSI"], line=dict(color="purple", width=1), name="RSI",
            ), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
            macd_colors = ["red" if v < 0 else "green" for v in df["MACD_hist"]]
            fig.add_trace(go.Bar(
                x=df.index, y=df["MACD_hist"], name="MACD Hist", marker_color=macd_colors, opacity=0.6,
            ), row=4, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["MACD"], line=dict(color="blue", width=1), name="MACD",
            ), row=4, col=1)
            fig.add_trace(go.Scatter(
                x=df.index, y=df["MACD_signal"], line=dict(color="orange", width=1), name="Signal",
            ), row=4, col=1)

        fig.update_layout(
            height=700 if not is_intraday else 500,
            xaxis_rangeslider_visible=False,
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
            showlegend=True, legend=dict(orientation="h", y=1.1),
            template="plotly_white",
            dragmode="drawline",
            newshape=dict(line_color="cyan", line_width=2),
        )
        fig.update_yaxes(title_text="Price", row=1, col=1)
        if not is_intraday:
            fig.update_yaxes(title_text="Volume", row=2, col=1)
            fig.update_yaxes(title_text="RSI", row=3, col=1)
            fig.update_yaxes(title_text="MACD", row=4, col=1)
        else:
            fig.update_yaxes(title_text="Volume", row=2, col=1)

        return fig
    except Exception as e:
        return None


def _strategy_fail_warning(strategy_id: str, tech_data: Dict[str, Any]) -> str:
    msg = ""
    if strategy_id == "breakout_momentum":
        vol_ratio = tech_data.get("volume_ratio_10_50")
        if vol_ratio and vol_ratio < 1.2:
            msg = "⚠ 突破策略在量能 < 1.2× 均量時有 ~60% 假突破率。確認放量再進。"
    elif strategy_id == "mean_reversion":
        rsi = tech_data.get("rsi_14")
        if rsi and rsi < 20:
            msg = "⚠ V 型反彈中均值回歸策略有 ~40% 鞭打率。等待第二隻腳確認。"
    return msg


def _build_trade_plan_text(data: Dict[str, Any], lang: str) -> str:
    lines = [f"=== Trade Plan ({data.get('id', '')}) ==="]
    ep = data.get("entry_price")
    if ep:
        lines.append(f"Entry: ${ep:.2f}")
    for tgt in data.get("targets", []):
        lines.append(f"Target ${tgt['price']:.2f} ({tgt.get('size_pct', 100)}%)")
    sp = data.get("stop_loss")
    if sp:
        lines.append(f"Stop: ${sp:.2f}")
    rr = data.get("risk_reward")
    if rr:
        lines.append(f"R:R = {rr:.1f}")
    ml = data.get("max_loss_usd")
    if ml:
        lines.append(f"Max Loss: ${ml:.0f}")
    return "\n".join(lines)


def render_recommendations_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    recs = st.session_state.recommendations
    if not recs:
        st.warning(t("recommend.nodata", lang))
        return

    with st.expander(t("risk.title", lang), expanded=False):
        st.caption(t("risk.disclaimer", lang))

    cols = st.columns(len(recs))
    for i, (col, rec) in enumerate(zip(cols, recs)):
        with col:
            score = rec.get("total_score", 0)
            price = rec.get("price")
            price_str = f"${price:.2f}" if price else "$N/A"
            sec_name = _sector_name(rec.get("sector", ""), lang)
            name = _stock_name(rec, lang)
            signal = rec.get("llm_key_signal", "")
            signal_emoji = {"bullish": "🟢", "neutral": "🟡", "bearish": "🔴"}.get(signal, "")
            signal_html = f"""<p style="font-size:0.7rem;margin:2px 0 0;color:#86868b;">
                {t('llm.signal', lang)}: {signal_emoji} {t('llm.signal_' + signal, lang) if signal else ''}
            </p>""" if signal else ""
            st.markdown(
                f"""
                <div class="rec-card">
                    <p class="rc-rank">RANK #{i+1}</p>
                    <p class="rc-ticker">{rec['ticker']}</p>
                    <p class="rc-name">{name}</p>
                    <p class="rc-sector">{sec_name}</p>
                    <div class="rc-divider"></div>
                    <p class="rc-price">{price_str}</p>
                    <p class="rc-score">{t('recommend.score', lang, s=score)}</p>
                    {signal_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<hr style='margin:1.5rem 0;'>", unsafe_allow_html=True)
    for i, rec in enumerate(recs):
        sec = rec.get("sec_insights") or {}
        form_type = sec.get("form_type") or "N/A"
        filing_date = sec.get("filing_date") or "N/A"
        sec_url = sec.get("url")
        insights = sec.get("insights")
        name = _stock_name(rec, lang)
        sec_cn = _sector_name(rec.get("sector", ""), lang)

        with st.expander(
            f"📌 **#{i+1} {rec['ticker']} — {name}**"
            f" ({sec_cn}) | {t('recommend.score', lang, s=rec.get('total_score', 0))}"
        ):
            mcol1, mcol2, mcol3 = st.columns(3)
            with mcol1:
                price_val = rec.get("price")
                price_session = rec.get("price_session", "")
                if price_val:
                    session_badge = ""
                    if price_session == "Pre-Market Trading":
                        session_badge = "🟢"
                    elif price_session == "After-Hours Trading":
                        session_badge = "🟣"
                    elif price_session == "Overnight Trading":
                        session_badge = "🔵"
                    elif price_session == "Regular Trading Hours":
                        session_badge = "🟢"
                    price_label = f"${price_val:.2f}"
                    st.metric(t("metric.price", lang), price_label)
                    badge = ""
                    if price_session and price_session != "Regular Trading Hours":
                        badge = f"<span style='font-size:0.7rem;color:#86868b;'>({price_session})</span>"
                    fetched = rec.get("data_quality", {}).get("fetched_at") or rec.get("fetched_at")
                    if fetched:
                        from datetime import datetime as _dt
                        try:
                            ft = _dt.strptime(fetched[:19], "%Y-%m-%d %H:%M:%S")
                            mins_ago = (_dt.now() - ft).total_seconds() / 60
                            if mins_ago < 5:
                                dot = "🟢"
                            elif mins_ago < 30:
                                dot = "🟡"
                            else:
                                dot = "🔴"
                            badge += f" <span style='font-size:0.7rem;color:#86868b;'>{dot} {fetched[:16]}</span>"
                        except ValueError:
                            pass
                    if badge:
                        st.markdown(badge, unsafe_allow_html=True)
                else:
                    st.metric(t("metric.price", lang), "N/A")
                st.metric(t("metric.revenue", lang), f"{rec.get('revenue_growth', 0):.1f}%" if rec.get("revenue_growth") is not None else "N/A")
                st.metric(t("metric.profit_margin", lang), f"{rec.get('profit_margin', 0):.1f}%" if rec.get("profit_margin") is not None else "N/A")
            with mcol2:
                st.metric(t("metric.eps", lang), f"{rec.get('eps_growth', 0):.1f}%" if rec.get("eps_growth") is not None else "N/A")
                st.metric(t("metric.roe", lang), f"{rec.get('roe', 0):.1f}%" if rec.get("roe") is not None else "N/A")
                st.metric(t("metric.peg", lang), f"{rec.get('peg', 0):.2f}" if rec.get("peg") is not None else "N/A")
            with mcol3:
                st.metric(t("metric.pe", lang), f"{rec.get('pe_ratio', 0):.2f}" if rec.get("pe_ratio") is not None else "N/A")
                st.metric(t("metric.de", lang), f"{rec.get('debt_equity', 0):.2f}" if rec.get("debt_equity") is not None else "N/A")
                market_cap = rec.get("market_cap")
                cap_str = f"${market_cap/1e9:.2f}B" if market_cap and market_cap >= 1e9 else f"${market_cap/1e6:.2f}M" if market_cap else "N/A"
                st.metric(t("metric.mcap", lang), cap_str)

            # Relative strength
            try:
                from agents.trading_strategies import _get_relative_strength as _rel_str
                _rs_data = _rel_str(rec["ticker"], rec.get("sector"))
                if _rs_data.get("vs_spy_pct") is not None:
                    _v = _rs_data["vs_spy_pct"]
                    _c = "color:#22c55e" if _v > 0 else "color:#ef4444"
                    st.markdown(
                        f"<span style='font-size:0.7rem;{_c};'>📊 vs SPY: {'+' if _v > 0 else ''}{_v:.1f}%"
                        + (f" | vs 板塊: {'+' if _rs_data.get('vs_sector_pct', 0) > 0 else ''}{_rs_data.get('vs_sector_pct', 0):.1f}%"
                           if _rs_data.get("vs_sector_pct") is not None else "")
                        + "</span>",
                        unsafe_allow_html=True,
                    )
            except Exception:
                pass

            dq = rec.get("data_quality", {})
            fetched = dq.get("fetched_at", rec.get("fetched_at"))
            if fetched:
                st.caption(t("recommend.fetched_at", lang, time=fetched))
            avail = dq.get("metrics_available", 0)
            total_m = dq.get("metrics_total", 6)
            ratio = avail / total_m if total_m > 0 else 0
            if ratio >= 0.8:
                conf = t("conf.high", lang)
            elif ratio >= 0.5:
                conf = t("conf.medium", lang)
            else:
                conf = t("conf.low", lang)
            st.caption(t("recommend.confidence", lang, level=conf))

            extra_cols = st.columns(4)
            items = [
                (t("metric.beta", lang), f"{rec.get('beta', 0):.2f}" if rec.get("beta") else "N/A"),
                (t("metric.div_yield", lang), f"{rec.get('dividend_yield', 0)*100:.2f}%" if rec.get("dividend_yield") else "N/A"),
                (t("metric.rating", lang), rec.get("rating_label") or "N/A"),
                (t("metric.inst_own", lang), f"{rec.get('held_percent_institutions', 0)*100:.1f}%" if rec.get("held_percent_institutions") else "N/A"),
            ]
            for extra_col, (lbl, val) in zip(extra_cols, items):
                extra_col.metric(lbl, val)

            use_llm = st.session_state.get("use_llm", False)
            if use_llm and rec.get("llm_reasoning"):
                llm_score = rec.get("llm_score")
                fund_score = rec.get("growth_score")
                key_signal = rec.get("llm_key_signal", "neutral")
                sig_emoji = {"bullish": "🟢", "neutral": "🟡", "bearish": "🔴"}.get(key_signal, "")
                sig_label = t(f"llm.signal_{key_signal}", lang)
                st.subheader(t("llm.analysis", lang))

                score_col1, score_col2, score_col3 = st.columns(3)
                with score_col1:
                    st.metric(t("recommend.score", lang), f"{rec.get('total_score', 0):.0f}")
                with score_col2:
                    if fund_score is not None:
                        st.metric(t("llm.fundamental_score", lang), f"{fund_score:.0f}")
                with score_col3:
                    if llm_score is not None:
                        st.metric(t("llm.score", lang), f"{llm_score:.0f}/100")

                if fund_score is not None and llm_score is not None:
                    divergence = abs(fund_score - llm_score)
                    if divergence > 25:
                        st.warning(t("llm.divergence", lang, d=divergence))

                st.markdown(f"{sig_emoji} **{t('llm.signal', lang)}**: {sig_label}")
                tech_summary = rec.get("llm_technical_summary", "")
                if tech_summary:
                    st.markdown(f"**{t('llm.technical_summary', lang)}**: {tech_summary}")

            ticker = rec["ticker"]
            price = rec.get("price")
            pcol1, pcol2 = st.columns(2)
            with pcol1:
                if st.button(t("price_suggest.btn", lang), key=f"price_btn_{ticker}", use_container_width=True):
                    with st.spinner(t("price_suggest.loading", lang)):
                        from agents.technical_analyzer import compute_technical_indicators
                        tech_data = compute_technical_indicators(ticker)
                        news_data = rec.get("news", [])
                        try:
                            from agents.llm_agent import suggest_price_targets
                            result = suggest_price_targets(ticker, tech_data, news_data, price or 0, lang)
                            if "error" in result:
                                from agents.data_fetcher import suggest_price_fallback
                                result = suggest_price_fallback(ticker, tech_data, price or 0)
                        except Exception:
                            from agents.data_fetcher import suggest_price_fallback
                            result = suggest_price_fallback(ticker, tech_data, price or 0)
                        st.session_state[f"price_result_{ticker}"] = result
            with pcol2:
                if st.button(t("options.btn", lang), key=f"opt_btn_{ticker}", use_container_width=True):
                    with st.spinner(t("options.loading", lang)):
                        from agents.technical_analyzer import compute_technical_indicators
                        tech_data = compute_technical_indicators(ticker)
                        news_data = rec.get("news", [])
                        try:
                            from agents.llm_agent import suggest_options_strategy
                            result = suggest_options_strategy(ticker, tech_data, price or 0, news_data, lang)
                            if "error" in result:
                                from agents.data_fetcher import suggest_options_fallback
                                result = suggest_options_fallback(ticker, tech_data, price or 0)
                        except Exception:
                            from agents.data_fetcher import suggest_options_fallback
                            result = suggest_options_fallback(ticker, tech_data, price or 0)
                        st.session_state[f"opt_result_{ticker}"] = result

            price_result = st.session_state.get(f"price_result_{ticker}")
            if price_result:
                if "error" in price_result:
                    st.error(f"⚠️ {price_result['error']}")
                else:
                    st.markdown(f"**{t('price_suggest.btn', lang)}**")
                    pc1, pc2, pc3, pc4 = st.columns(4)
                    buy = price_result.get("buy_price")
                    sell = price_result.get("sell_price")
                    stop = price_result.get("stop_loss")
                    conf = price_result.get("confidence")
                    with pc1:
                        st.metric(t("price_suggest.buy", lang), f"${buy:.2f}" if buy else t("price_suggest.na", lang))
                    with pc2:
                        st.metric(t("price_suggest.sell", lang), f"${sell:.2f}" if sell else "—")
                    with pc3:
                        st.metric(t("price_suggest.stop", lang), f"${stop:.2f}" if stop else "—")
                    with pc4:
                        st.metric(t("price_suggest.confidence", lang), f"{conf:.0f}%" if conf else "—")
                    reason = price_result.get("reasoning", "")
                    if reason:
                        st.markdown(reason)
                    st.markdown("<hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)

            opt_result = st.session_state.get(f"opt_result_{ticker}")
            if opt_result:
                if "error" in opt_result:
                    st.error(f"⚠️ {opt_result['error']}")
                else:
                    st.markdown(f"**{t('options.btn', lang)}**")
                    ot = opt_result.get("option_type", "none")
                    if ot == "call":
                        ot_label = t("options.call", lang)
                    elif ot == "put":
                        ot_label = t("options.put", lang)
                    else:
                        ot_label = t("options.none", lang)
                    oc1, oc2, oc3, oc4 = st.columns(4)
                    with oc1:
                        st.metric(t("options.type", lang), ot_label)
                    with oc2:
                        strike = opt_result.get("strike_price")
                        st.metric(t("options.strike", lang), f"${strike:.2f}" if strike else "—")
                    with oc3:
                        expiry = opt_result.get("expiration")
                        st.metric(t("options.expiry", lang), expiry or "—")
                    with oc4:
                        sup = opt_result.get("key_support")
                        res = opt_result.get("key_resistance")
                        st.metric(t("options.support", lang), f"${sup:.2f}" if sup else "—")
                    oreason = opt_result.get("reasoning", "")
                    if oreason:
                        st.markdown(oreason)
                    st.markdown("<hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)

            # --- Trading Strategy ---
            strategy_key = f"strat_result_{ticker}"
            if st.button(t("strategy.btn", lang), key=f"strat_btn_{ticker}", use_container_width=True):
                with st.spinner(t("strategy.loading", lang)):
                    from agents.trading_strategies import recommend_strategies
                    from agents.technical_analyzer import compute_technical_indicators
                    tech_data = compute_technical_indicators(ticker)
                    result = recommend_strategies(ticker, rec, tech_data)
                    try:
                        from agents.llm_agent import check_llm_health, suggest_trading_strategy
                        if check_llm_health():
                            opts = result.get("options_data", {})
                            news_data = rec.get("news", [])
                            llm_r = suggest_trading_strategy(
                                ticker, rec, tech_data, price or 0, opts, news_data, lang
                            )
                            if "error" not in llm_r:
                                result["llm"] = llm_r
                    except Exception:
                        pass
                    st.session_state[strategy_key] = {**result, "_tech_data": tech_data}

            strat_result = st.session_state.get(strategy_key)
            if strat_result:
                if "error" in strat_result:
                    st.error(f"⚠️ {strat_result['error']}")
                else:
                    cal = strat_result.get("calendar", {})
                    if cal.get("has_conflict"):
                        st.warning(cal["warning"])
                    regime = strat_result.get("regime", {})
                    regime_str = f"📊 市況: {regime.get('trend', '?')} / {regime.get('volatility', '?')}波動"
                    rs = strat_result.get("relative_strength", {})
                    if rs.get("vs_spy_pct") is not None:
                        sp = rs["vs_spy_pct"]
                        regime_str += f" | vs SPY: {'+' if sp > 0 else ''}{sp:.1f}%"
                    if rs.get("vs_sector_pct") is not None:
                        sp2 = rs["vs_sector_pct"]
                        regime_str += f" | vs 板塊: {'+' if sp2 > 0 else ''}{sp2:.1f}%"
                    st.caption(regime_str)

                    llm_data = strat_result.get("llm")
                    top = strat_result.get("top", {})
                    rankings = strat_result.get("rankings", [])

                    if llm_data and llm_data.get("top_strategy"):
                        st.markdown(f"**🤖 {t('strategy.llm_title', lang)}**")
                        llm_sid = llm_data.get("top_strategy", "")
                        llm_name = t(f"strategy.{llm_sid}", lang) if llm_sid else ""
                        st.info(f"**{llm_name}** — {llm_data.get('reasoning', '')}")
                        conf = llm_data.get("confidence", {})
                        if conf:
                            cc1, cc2, cc3 = st.columns(3)
                            cc1.metric("技術信心", f"{conf.get('technical', 0)}%")
                            cc2.metric("基本面信心", f"{conf.get('fundamental', 0)}%")
                            cc3.metric("型態品質", f"{conf.get('setup_quality', 0)}%")
                        entry = llm_data.get("entry", {})
                        stop = llm_data.get("stop_loss", {})
                        targets = llm_data.get("targets", [])
                        rr = llm_data.get("risk_reward")
                        if entry.get("price"):
                            st.markdown(f"**{t('strategy.entry', lang)}**: ${entry['price']:.2f} ({entry.get('type', 'limit')})")
                        if targets:
                            tgt_str = " → ".join([f"${t['price']:.2f} ({t.get('size_pct', 100)}%)" for t in targets])
                            st.markdown(f"**{t('strategy.target', lang)}**: {tgt_str}")
                        if stop.get("price"):
                            st.markdown(f"**{t('strategy.stop', lang)}**: ${stop['price']:.2f} ({stop.get('type', 'fixed')})")
                        if rr:
                            st.markdown(f"**R:R** = {rr:.1f}")
                        sc = llm_data.get("scenario", {})
                        if sc:
                            with st.expander(t("strategy.scenario", lang)):
                                for label_key in ["best", "base", "worst"]:
                                    v = sc.get(label_key)
                                    if v:
                                        st.markdown(f"**{t(f'strategy.{label_key}', lang)}**: {v}")
                        st.markdown("<hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)

                    if rankings:
                        st.markdown(f"**📋 {t('strategy.title', lang)}**")
                        for rank_entry in rankings:
                            sid = rank_entry.get("id", "")
                            sname = t(rank_entry.get("name_key", ""), lang)
                            sscore = rank_entry.get("score", 0)
                            sd = t(rank_entry.get("difficulty_key", ""), lang)
                            sh = rank_entry.get("time_horizon", "")

                            risk_map = {"trend_following": "strategy.risk_low", "mean_reversion": "strategy.risk_mid",
                                        "breakout_momentum": "strategy.risk_mid", "value_entry": "strategy.risk_low",
                                        "income_defensive": "strategy.risk_low"}
                            risk_label = t(risk_map.get(sid, "strategy.risk_mid"), lang) if sid else ""

                            bar_color = "#22c55e" if sscore >= 70 else "#eab308" if sscore >= 40 else "#ef4444"
                            st.markdown(
                                f"<div style='display:flex;justify-content:space-between;"
                                f"align-items:center;padding:2px 0;'>"
                                f"<span><b>{sname}</b> | {sh} | {sd} | {risk_label}</span>"
                                f"<span style='font-weight:bold;color:{bar_color};'>{sscore}%</span>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )
                            if sscore > 0 and rank_entry.get("reasoning"):
                                st.caption(rank_entry["reasoning"])

                        st.markdown("<hr style='margin:0.5rem 0;'>", unsafe_allow_html=True)
                        st.markdown(f"**🏆 {t('strategy.top_title', lang)}**")

                        if top:
                            if top.get("entry_price"):
                                stop_p = top.get("stop_loss")
                                st.info(
                                    f"**{t('strategy.entry', lang)}**: ${top['entry_price']:.2f}"
                                    + (f" → **{t('strategy.target', lang)}**: ${top['targets'][0]['price']:.2f}" if top.get('targets') else "")
                                    + (f" | **{t('strategy.stop', lang)}**: ${stop_p:.2f}" if stop_p else "")
                                    + (f" | **R:R** = {top.get('risk_reward', '?')}" if top.get('risk_reward') else "")
                                )
                            if top.get("targets"):
                                tgt_line = "  |  ".join([f"🎯 ${t['price']:.2f} (出 {t['size_pct']}%)" for t in top["targets"]])
                                st.markdown(tgt_line)
                            pos_size = top.get("max_loss_usd", 0)
                            shares = top.get("shares", 0)
                            if pos_size or shares:
                                st.caption(f"💵 {t('strategy.max_loss', lang)}: ${pos_size:.0f} ({t('strategy.shares', lang)} {shares})")
                            conf_t = top.get("technical_confidence")
                            conf_f = top.get("fundamental_confidence")
                            conf_s = top.get("setup_quality")
                            if any([conf_t, conf_f, conf_s]):
                                r1, r2, r3 = st.columns(3)
                                r1.metric("📊 技術信心", f"{conf_t}%" if conf_t else "—")
                                r2.metric("📈 基本面信心", f"{conf_f}%" if conf_f else "—")
                                r3.metric("⚙ 型態品質", f"{conf_s}%" if conf_s else "—")
                            sc = top.get("scenario", {})
                            if sc:
                                with st.expander(t("strategy.scenario", lang)):
                                    for label_key in ["best", "base", "worst"]:
                                        v = sc.get(label_key)
                                        if v:
                                            st.markdown(f"**{t(f'strategy.{label_key}', lang)}**: {v}")
                            reason = top.get("reasoning", "")
                            if reason:
                                st.caption(reason)
                            fail_warning = _strategy_fail_warning(top.get("id", ""), strat_result.get("_tech_data", {}))
                            if fail_warning:
                                st.caption(fail_warning)
                            if st.button(t("strategy.copy", lang), key=f"copy_strat_{ticker}"):
                                plan = _build_trade_plan_text(top, lang)
                                st.code(plan, language="text")

            reasoning = rec.get("reasoning", "")
            if reasoning:
                st.subheader(t("recommend.reasoning", lang))
                st.markdown(reasoning)

            score_details = rec.get("score_details", {})
            if score_details:
                st.subheader(t("recommend.details", lang))
                sd_list = [
                    {t("recommend.metric", lang): k, t("recommend.value", lang): v.get("value", ""),
                     t("recommend.score_label", lang): v.get("score", "")}
                    for k, v in score_details.items()
                ]
                st.dataframe(pd.DataFrame(sd_list), hide_index=True, use_container_width=True)

            news = rec.get("news", [])
            if news:
                st.subheader(t("recommend.news", lang))
                for n in news:
                    emoji = "✅" if n.get("sentiment") == "positive" else "❌" if n.get("sentiment") == "negative" else "➖"
                    st.markdown(f"{emoji} **{n.get('title', '')}**")
                    if n.get("summary"):
                        st.markdown(n["summary"])
                    st.caption(f"{n.get('publisher', '')} | [{t('news.view', lang)}]({n.get('link', '')})")

            st.subheader(t("recommend.sec", lang))
            if sec_url:
                st.markdown(t("recommend.sec_file", lang, form=form_type, date=filing_date))
                st.markdown(f"[{t('recommend.sec_view', lang)}]({sec_url})")
            else:
                st.markdown(f"*{t('recommend.sec_fail', lang)}*")

            if insights:
                llm_summary = insights.get("llm_summary")
                if llm_summary and llm_summary.get("summary") and llm_summary["summary"] != "N/A":
                    st.markdown(f"**📝 {_sector_name(rec.get('sector', ''), lang)} 摘要**")
                    st.info(llm_summary["summary"])
                    if llm_summary.get("key_positives"):
                        for kp in llm_summary["key_positives"]:
                            st.markdown(f"✅ {kp}")
                    if llm_summary.get("key_risks"):
                        for kr in llm_summary["key_risks"]:
                            st.markdown(f"⚠️ {kr}")
                else:
                    sections = insights.get("sections") or {}
                    if sections:
                        for section_title, content in sections.items():
                            if section_title != "ticker":
                                with st.container():
                                    st.markdown(f"**{section_title}**")
                                    st.text(content[:800])
                                    st.caption(t("recommend.truncated", lang))
                    else:
                        st.markdown(f"*{t('recommend.sec_na', lang)}*")
            else:
                st.markdown(f"*{t('recommend.sec_na', lang)}*")

            chart_visible_key = f"chart_visible_{ticker}"
            if st.button(t("chart.show", lang), key=f"chart_btn_{ticker}", use_container_width=True):
                st.session_state[chart_visible_key] = not st.session_state.get(chart_visible_key, False)

            if st.session_state.get(chart_visible_key, False):
                chart_interval_key = f"chart_interval_{ticker}"
                intervals = ["1m", "5m", "15m", "30m", "60m", "1d"]
                interval_labels = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "60m": "1hr", "1d": "Daily"}
                default_idx = intervals.index("1d") if "1d" in intervals else 0
                selected_interval = st.selectbox(
                    t("chart.interval", lang), intervals,
                    format_func=lambda x: interval_labels.get(x, x),
                    key=chart_interval_key,
                    index=intervals.index(st.session_state.get(f"chart_interval_last_{ticker}", "1d")),
                )
                st.session_state[f"chart_interval_last_{ticker}"] = selected_interval
                with st.spinner(t("chart.loading", lang)):
                    fig = _build_tech_chart(ticker, interval=selected_interval, lang=lang)
                    if fig:
                        st.plotly_chart(
                            fig, use_container_width=True,
                            config={
                                "modeBarButtonsToAdd": [
                                    "drawline", "drawopenpath", "drawcircle",
                                    "drawrect", "eraseshape",
                                ],
                                "modeBarButtonsToRemove": ["sendDataToCloud"],
                                "displayModeBar": True,
                                "displaylogo": False,
                            },
                        )
                    else:
                        st.caption("No chart data available")


def render_rankings_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    rankings = st.session_state.all_rankings
    if not rankings:
        st.warning(t("ranking.nodata", lang))
        return
    df = pd.DataFrame(rankings).dropna(axis=1, how="all")
    use_llm = st.session_state.get("use_llm", False)
    if use_llm and "LLM评分" in df.columns:
        df = df.sort_values("LLM评分", ascending=False)
        df["排名"] = range(1, len(df) + 1)
    highlight = st.checkbox(t("ranking.highlight", lang), value=True)

    def color_top_rows(row: pd.Series) -> List[str]:
        if highlight and row.get(t("ranking.rank", lang)) is not None and row[t("ranking.rank", lang)] <= 5:
            return ["background-color: #e8f5e9"] * len(row)
        return [""] * len(row)

    styled = df.style.apply(color_top_rows, axis=1)
    st.dataframe(styled, hide_index=True, use_container_width=True, height=600)


def render_compare_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    scored = st.session_state.scored_data
    if not scored:
        st.warning(t("compare.prompt", lang))
        return

    options = {}
    for s in scored:
        label = f"{s['ticker']} ({(s.get('longName') or '')[:20]})"
        options[s["ticker"]] = label

    selected = st.multiselect(
        t("compare.select", lang), options=sorted(options.keys()),
        format_func=lambda t_: options[t_],
        max_selections=4,
        default=[s["ticker"] for s in scored[:2]] if len(scored) >= 2 else None,
    )

    if len(selected) < 2:
        st.info(t("compare.min_select", lang))
        return

    compare_data = {s["ticker"]: s for s in scored if s["ticker"] in selected}
    metrics = [
        ("total_score", t("compare.indicator", lang), "{:.1f}"),
        ("price", t("metric.price", lang), "${:.2f}"),
        ("market_cap", t("metric.mcap", lang), lambda v: f"${v/1e9:.2f}B" if v and v >= 1e9 else f"${v/1e6:.2f}M" if v else "N/A"),
        ("revenue_growth", t("metric.revenue", lang), "{:.1f}%"),
        ("eps_growth", t("metric.eps", lang), "{:.1f}%"),
        ("profit_margin", t("metric.profit_margin", lang), "{:.1f}%"),
        ("roe", t("metric.roe", lang), "{:.1f}%"),
        ("peg", t("metric.peg", lang), "{:.2f}"),
        ("pe_ratio", t("metric.pe", lang), "{:.2f}"),
        ("debt_equity", t("metric.de", lang), "{:.2f}"),
        ("beta", t("metric.beta", lang), "{:.2f}"),
    ]

    rows: List[Dict[str, Any]] = []
    for key, label, fmt in metrics:
        row: Dict[str, Any] = {t("compare.indicator", lang): label}
        for ticker in selected:
            data = compare_data.get(ticker, {})
            val = data.get(key)
            if val is None:
                row[ticker] = "N/A"
            elif callable(fmt):
                row[ticker] = fmt(val)
            else:
                row[ticker] = fmt.format(val)
        rows.append(row)

    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    chart_metrics = [
        ("total_score", "Score"), ("revenue_growth", "Rev%"), ("eps_growth", "EPS%"),
        ("profit_margin", "Margin%"), ("roe", "ROE%"),
    ]
    chart_data: Dict[str, List[float]] = {t("compare.indicator", lang): [m[1] for m in chart_metrics]}
    for ticker in selected:
        chart_data[ticker] = []
    for key, _ in chart_metrics:
        for ticker in selected:
            data = compare_data.get(ticker, {})
            val = data.get(key)
            chart_data[ticker].append(val if val is not None else 0)

    dfc = pd.DataFrame(chart_data)
    dfm = dfc.melt(id_vars=[t("compare.indicator", lang)], var_name=t("compare.stock", lang), value_name="Value")
    chart = alt.Chart(dfm).mark_bar(opacity=0.85).encode(
        x=alt.X(f"{t('compare.indicator', lang)}:N", title=None),
        y=alt.Y("Value:Q", title=None),
        color=alt.Color(f"{t('compare.stock', lang)}:N", legend=alt.Legend(orient="top")),
        column=alt.Column(f"{t('compare.stock', lang)}:N", title=None),
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)


def _valuation_label(value: Optional[float], ranges: List[float], lang: str) -> str:
    if value is None:
        return "N/A"
    if value <= ranges[1]:
        return t("valuation.undervalued", lang)
    elif value <= ranges[2]:
        return t("valuation.fair", lang)
    return t("valuation.overvalued", lang)


def render_valuation_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    scored = st.session_state.scored_data
    if not scored:
        st.warning(t("valuation.prompt", lang))
        return

    rows: List[Dict[str, Any]] = []
    for s in scored:
        row: Dict[str, Any] = {t("valuation.ticker", lang): s["ticker"],
                                t("valuation.name", lang): (s.get("longName") or "")[:20]}
        for key, label in VALUATION_LABELS.items():
            val = s.get(key)
            row[label] = f"{val:.2f}" if val is not None else "N/A"
        row[t("valuation.growth", lang)] = f"{s.get('total_score', 0):.1f}"
        rows.append(row)

    df = pd.DataFrame(rows)

    cols = st.columns(2)
    metrics_to_judge = [
        ("pe_ratio", t("metric.pe", lang), t("valuation.pe_note", lang)),
        ("peg", t("metric.peg", lang), t("valuation.peg_note", lang)),
        ("ps_ratio", t("metric.ps", lang), t("valuation.ps_note", lang)),
        ("pb_ratio", t("metric.pb", lang), t("valuation.pb_note", lang)),
        ("ev_ebitda", "EV/EBITDA", t("valuation.ev_note", lang)),
    ]
    for col, (key, label, note) in zip(cols * 3, metrics_to_judge):
        with col:
            st.markdown(f"**{label}**")
            st.caption(note)
            tickers = [s["ticker"] for s in scored]
            vals = [s.get(key) for s in scored]
            jdg = [_valuation_label(v, VALUATION_RANGES[key], lang) for v in vals]
            jdg_df = pd.DataFrame({
                t("valuation.ticker", lang): tickers,
                "Value": [f"{v:.2f}" if v else "N/A" for v in vals],
                t("valuation.judgment", lang): jdg,
            })
            st.dataframe(jdg_df, hide_index=True, use_container_width=True, height=200)

    st.subheader(t("valuation.full_table", lang))
    display_cols = [t("valuation.ticker", lang), t("valuation.name", lang)] + list(VALUATION_LABELS.values()) + [t("valuation.growth", lang)]
    st.dataframe(df[display_cols], hide_index=True, use_container_width=True, height=600)


def render_charts_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    recs = st.session_state.recommendations
    if not recs:
        st.warning(t("charts.nodata", lang))
        return

    ticker_options = {r["ticker"]: f"{r['ticker']} — {_stock_name(r, lang)}" for r in recs}
    selected = st.selectbox(t("charts.select", lang), options=list(ticker_options.keys()), format_func=lambda t_: ticker_options[t_])

    from agents.data_fetcher import fetch_financials_history
    data = fetch_financials_history(selected)
    if not data:
        st.warning(t("charts.no_history", lang))
        return

    years = list(range(2026 - len(next(iter(data.values()))), 2026))

    for key, label, color in [
        ("revenue", t("charts.revenue", lang), "#0071e3"),
        ("net_income", t("charts.net_income", lang), "#34c759"),
        ("eps", t("charts.eps", lang), "#ff3b30"),
    ]:
        vals = data.get(key)
        if not vals:
            continue
        df = pd.DataFrame({"Year": years[-len(vals):], label: vals})
        chart = alt.Chart(df).mark_bar(color=color, opacity=0.85).encode(
            x=alt.X("Year:N", title=None),
            y=alt.Y(f"{label}:Q", title=None),
        ).properties(height=250)
        st.subheader(label)
        st.altair_chart(chart, use_container_width=True)

    if "revenue" in data and "net_income" in data:
        rev = data["revenue"]
        ni = data["net_income"]
        margin = [(ni[i] / rev[i] * 100) if rev[i] else 0 for i in range(min(len(ni), len(rev)))]
        dfm = pd.DataFrame({"Year": years[-len(margin):], t("charts.margin", lang): margin})
        cm = alt.Chart(dfm).mark_line(point=True, color="#af52de").encode(
            x=alt.X("Year:N", title=None),
            y=alt.Y(f"{t('charts.margin', lang)}:Q", title=None),
        ).properties(height=250)
        st.subheader(t("charts.margin", lang))
        st.altair_chart(cm, use_container_width=True)


def render_news_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    recs = st.session_state.recommendations
    if not recs:
        st.warning(t("news.nodata", lang))
        return

    all_news: List[Dict[str, Any]] = []
    for rec in recs:
        for n in rec.get("news", []):
            all_news.append(n)

    if not all_news:
        st.info(t("news.nodata", lang))
        return

    sentiment_order = {"positive": 0, "neutral": 1, "negative": 2}
    all_news.sort(key=lambda n: sentiment_order.get(n.get("sentiment", "neutral"), 1))

    for n in all_news:
        emoji = "✅" if n.get("sentiment") == "positive" else "❌" if n.get("sentiment") == "negative" else "➖"
        label = t("news.positive", lang) if n.get("sentiment") == "positive" else t("news.negative", lang) if n.get("sentiment") == "negative" else t("news.neutral", lang)
        with st.container(border=True):
            cols = st.columns([1, 6, 1])
            with cols[0]:
                st.markdown(f"**{n.get('ticker', '')}**")
            with cols[1]:
                st.markdown(f"{emoji} **{n.get('title', '')}**")
                if n.get("summary"):
                    st.caption(n["summary"][:200])
            with cols[2]:
                st.markdown(f"`{label}`")
                if n.get("link"):
                    st.markdown(f"[{t('news.view', lang)}]({n['link']})")


def render_ai_status_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(t("ai.source_health", lang))
        health = st.session_state.source_health or {}
        if health:
            health_rows = []
            for source, info in sorted(health.items()):
                total = info.get("success", 0) + info.get("failure", 0)
                rate = info.get("success", 0) / total * 100 if total > 0 else 0
                health_rows.append({
                    t("ai.source", lang): source,
                    t("ai.success", lang): info.get("success", 0),
                    t("ai.failure", lang): info.get("failure", 0),
                    t("ai.rate", lang): f"{rate:.0f}%",
                    t("ai.status", lang): info.get("last_status", t("ai.unknown", lang)),
                })
            st.dataframe(pd.DataFrame(health_rows), hide_index=True, use_container_width=True)
        else:
            st.info(t("ai.no_source", lang))

    with col2:
        st.subheader(t("ai.logs", lang))
        logs = st.session_state.upgrade_logs or []
        if logs:
            for log_entry in logs[-10:]:
                msg = log_entry.get("message", "")
                st.markdown(f"- {msg}")
        else:
            st.info(t("ai.no_logs", lang))

    st.subheader(t("ai.cache", lang))
    from utils.cache import cache
    st.json(cache.get_cache_status() or {})
    summary = st.session_state.get("agent_summary", {})
    if summary:
        st.subheader(t("ai.summary", lang))
        st.json(summary)


def render_stock_pool_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    st.subheader(t("tab.pool", lang))

    search = st.text_input("🔍", placeholder="Search ticker or name...", label_visibility="collapsed", key="pool_search")

    all_stocks = list(STOCK_UNIVERSE)
    custom = st.session_state.get("custom_tickers", [])
    for t_ in custom:
        if t_ not in {s["ticker"] for s in all_stocks}:
            all_stocks.append({"ticker": t_, "name_cn": t_, "name_en": t_, "name_tw": t_, "sector": "Custom"})

    if search:
        s = search.upper()
        all_stocks = [s_ for s_ in all_stocks if s in s_["ticker"].upper() or s in s_["name_cn"].upper()]

    rows = []
    for s in all_stocks:
        is_custom = s["ticker"] in custom
        sec = s.get("sector", "")
        rows.append({
            "Ticker": s["ticker"],
            "Name": _stock_name(s, lang),
            "Sector": _sector_name(sec, lang),
            "Custom": "⭐" if is_custom else "",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True, height=500)

    st.subheader("📊 " + t("sidebar.stock_pool", lang))
    sec_counts = df.groupby("Sector").size().reset_index(name="Count")
    st.dataframe(sec_counts, hide_index=True, use_container_width=True)


def export_csv() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    if not st.session_state.all_rankings:
        return
    df = pd.DataFrame(st.session_state.all_rankings)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    st.sidebar.download_button(
        t("sidebar.export", lang),
        data=buf.getvalue(),
        file_name=f"stock_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_industry_news_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    st.subheader(t("industry_news.title", lang))
    st.caption(t("recommend.desc", lang) + " | " + t("industry_news.source", lang, source="Yahoo Finance"))
    try:
        news_data = fetch_industry_news()
    except Exception as e:
        st.warning(t("industry_news.no_data", lang) + ": " + str(e))
        return
    if not news_data or not news_data.get("all_headlines"):
        st.warning(t("industry_news.no_data", lang))
        return
    climate_items = news_data.get("climate_items", [])
    by_sector = news_data.get("by_sector", {})
    all_headlines = news_data.get("all_headlines", [])
    if climate_items:
        c_label = t("industry_news.warming", lang) + " (" + str(len(climate_items)) + ")"
        with st.expander(c_label, expanded=True):
            for item in climate_items:
                sec_cn = _sector_name(item.get("sector", ""), lang)
                st.markdown("**" + item.get("title", "") + "**")
                if item.get("summary"):
                    st.markdown(item["summary"][:200])
                pub = item.get("publisher", "")
                link = item.get("link", "")
                st.caption(pub + " | " + sec_cn + " | [" + t("news.view", lang) + "](" + link + ")")
                st.markdown("---")
    sector_names = sorted(by_sector.keys())
    tab_labels = [_sector_name(s, lang) for s in sector_names]
    tab_labels.append(t("news.title", lang) + " (" + str(len(all_headlines)) + ")")
    sector_tabs = st.tabs(tab_labels)
    for i, sec_en in enumerate(sector_names):
        with sector_tabs[i]:
            for item in by_sector[sec_en]:
                st.markdown("**" + item.get("title", "") + "**")
                if item.get("summary"):
                    st.markdown(item["summary"][:200])
                pub = item.get("publisher", "")
                link = item.get("link", "")
                st.caption(pub + " | [" + t("news.view", lang) + "](" + link + ")")
                st.markdown("---")
    with sector_tabs[-1]:
        for item in all_headlines:
            sec_cn = _sector_name(item.get("sector", ""), lang)
            st.markdown("**" + item.get("title", "") + "**")
            if item.get("summary"):
                st.markdown(item["summary"][:200])
            pub = item.get("publisher", "")
            link = item.get("link", "")
            st.caption(pub + " | " + sec_cn + " | [" + t("news.view", lang) + "](" + link + ")")
            st.markdown("---")


def render_backtest_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    st.subheader(t("backtest.title", lang))
    st.caption(t("backtest.desc", lang))

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        use_fund = st.checkbox("Use fundamentals (slower, more accurate)", value=True)
    with col2:
        years = st.selectbox("Backtest years", [3, 5], index=1)
    with col3:
        run = st.button(t("backtest.run", lang), type="primary", use_container_width=True)

    if run:
        import datetime as dt
        end_str = dt.datetime.now().strftime("%Y-%m-%d")
        start_str = str(dt.datetime.now().year - years) + "-01-01"
        status = st.status(t("backtest.running", lang), expanded=True)

        def progress(i: int, n: int, msg: str = ""):
            if n > 0:
                status.progress(i / n, text=f"{msg} ({i}/{n})")
            else:
                status.text(msg)

        from backtesting.engine import run_backtest, format_backtest_summary

        result = run_backtest(start=start_str, end=end_str, use_fundamentals=use_fund, progress_callback=progress)
        summary = format_backtest_summary(result)

        st.session_state.backtest_summary = summary
        status.update(label="✅ Backtest complete!", state="complete", expanded=False)

    summary = st.session_state.get("backtest_summary")
    if not summary:
        st.info(t("backtest.no_data", lang))
        return

    st.markdown("---")
    cols = st.columns(4)
    with cols[0]:
        st.metric(t("backtest.total_return", lang), f"{summary['total_return']:+.1f}%",
                  delta=f"{summary['avg_alpha']:+.1f}% vs SPY" if summary.get('avg_alpha') else None,
                  delta_color="normal")
    with cols[1]:
        st.metric(t("backtest.spy_return", lang), f"{summary['spy_return']:+.1f}%")
    with cols[2]:
        st.metric(t("backtest.win_rate", lang), f"{summary['win_rate']:.1f}%",
                  delta=f"{summary['wins']}W / {summary['losses']}L")
    with cols[3]:
        st.metric(t("backtest.sharpe", lang), f"{summary['sharpe']:.2f}")

    cols2 = st.columns(4)
    with cols2[0]:
        st.metric(t("backtest.max_dd", lang), f"{summary['max_drawdown']:.1f}%")
    with cols2[1]:
        st.metric(t("backtest.volatility", lang), f"{summary['volatility']:.1f}%")
    with cols2[2]:
        st.metric(t("backtest.best_month", lang), f"{summary['best_month']:+.1f}%")
    with cols2[3]:
        st.metric(t("backtest.worst_month", lang), f"{summary['worst_month']:+.1f}%")

    st.markdown("---")
    import plotly.graph_objects as go
    import pandas as pd
    import numpy as np

    periods = summary.get("periods", [])

    tab1, tab2, tab3, tab4 = st.tabs([
        t("backtest.equity_curve", lang),
        t("backtest.monthly_returns", lang),
        t("backtest.top_picks", lang),
        t("backtest.period_detail", lang),
    ])

    with tab1:
        dates = [p["date"] for p in periods]
        strategy_vals = []
        spy_vals = []
        val = 10000
        spy_val = 10000
        strategy_vals.append(val)
        spy_vals.append(spy_val)
        label_dates = [dates[0] - pd.DateOffset(months=1)] if dates else []
        for p in periods:
            if p.get("avg_return") is not None:
                val *= (1 + p["avg_return"] / 100)
            if p.get("spy_return") is not None:
                spy_val *= (1 + p["spy_return"] / 100)
            strategy_vals.append(val)
            spy_vals.append(spy_val)
            label_dates.append(p["date"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=label_dates, y=strategy_vals, mode="lines",
                                 name="Strategy", line=dict(color="#00d4aa", width=2)))
        fig.add_trace(go.Scatter(x=label_dates, y=spy_vals, mode="lines",
                                 name="SPY", line=dict(color="#888", width=2, dash="dash")))
        fig.update_layout(
            height=400, margin=dict(l=40, r=20, t=20, b=40),
            yaxis_title="Portfolio Value ($)",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        monthly = []
        for p in periods:
            if p.get("avg_return") is not None:
                monthly.append({
                    "date": str(p["date"].date()),
                    "strategy_return": p["avg_return"],
                    "spy_return": p.get("spy_return"),
                    "alpha": p.get("alpha"),
                    "beat_spy": p.get("beat_spy", False),
                })
        if monthly:
            df_m = pd.DataFrame(monthly)
            fig2 = go.Figure()
            colors = ["#00d4aa" if r else "#ff4b4b" for r in df_m["beat_spy"]]
            fig2.add_trace(go.Bar(
                x=df_m["date"], y=df_m["strategy_return"],
                marker_color=colors,
                name="Strategy",
            ))
            fig2.add_trace(go.Scatter(
                x=df_m["date"], y=df_m["spy_return"],
                mode="lines+markers",
                name="SPY", line=dict(color="#888", width=1.5, dash="dash"),
            ))
            fig2.update_layout(
                height=400, margin=dict(l=40, r=20, t=20, b=40),
                yaxis_title="Return (%)",
                hovermode="x unified",
                showlegend=True,
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        top_picks = summary.get("tickers_picked", {})
        sector_counts = summary.get("sector_counts", {})

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader(t("backtest.top_picks", lang))
            if top_picks:
                df_picks = pd.DataFrame({
                    "Ticker": list(top_picks.keys()),
                    "Picks": list(top_picks.values()),
                }).sort_values("Picks", ascending=True)
                fig3 = go.Figure(go.Bar(
                    x=df_picks["Picks"], y=df_picks["Ticker"],
                    orientation="h",
                    marker_color="#00d4aa",
                ))
                fig3.update_layout(height=400, margin=dict(l=20, r=20, t=10, b=20), xaxis_title="Times Picked")
                st.plotly_chart(fig3, use_container_width=True)

        with col_b:
            st.subheader(t("backtest.sector_breakdown", lang))
            if sector_counts:
                df_sec = pd.DataFrame({
                    "Sector": list(sector_counts.keys()),
                    "Picks": list(sector_counts.values()),
                })
                fig4 = go.Figure(go.Pie(
                    labels=df_sec["Sector"], values=df_sec["Picks"],
                    hole=0.4,
                ))
                fig4.update_layout(height=400, margin=dict(l=20, r=20, t=10, b=20))
                st.plotly_chart(fig4, use_container_width=True)

    with tab4:
        if periods:
            rows = []
            has_fund = any(p.get("avg_fund_score") is not None for p in periods)
            for p in periods:
                row = {
                    "Date": str(p["date"].date()),
                    "Picks": ", ".join(p.get("picks", [])),
                    "Tech Score": p.get("avg_tech_score", ""),
                    "Fund Score": f"{p.get('avg_fund_score', ''):.1f}" if p.get("avg_fund_score") is not None else "",
                    "Total Score": p.get("avg_score", ""),
                    "Return %": f"{p.get('avg_return', ''):+.1f}" if p.get("avg_return") is not None else "",
                    "SPY %": f"{p.get('spy_return', ''):+.1f}" if p.get("spy_return") is not None else "",
                    "Alpha %": f"{p.get('alpha', ''):+.1f}" if p.get("alpha") is not None else "",
                    "Beat": "✅" if p.get("beat_spy") else "❌",
                }
                if not has_fund:
                    del row["Fund Score"]
                rows.append(row)
            df_detail = pd.DataFrame(rows)
            st.dataframe(df_detail, hide_index=True, use_container_width=True, height=500)


def render_portfolio_tab() -> None:
    lang = st.session_state.get("lang", "zh_tw")
    portfolio = st.session_state.get("portfolio", {})
    if not portfolio or not portfolio.get("positions"):
        st.info(t("portfolio.no_data", lang))
        return

    positions = portfolio["positions"]
    st.subheader(t("portfolio.title", lang))
    st.caption(t("portfolio.desc", lang))

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric(t("portfolio.capital", lang), f"${portfolio['total_capital']:,.0f}")
    with col2:
        st.metric(t("portfolio.invested", lang), f"${portfolio['total_invested']:,.0f}")
    with col3:
        st.metric(t("portfolio.cash", lang), f"${portfolio['cash']:,.0f}")
    with col4:
        pnl = portfolio["total_pnl"]
        st.metric(t("portfolio.pnl", lang), f"${pnl:+,.0f}", delta_color="normal" if pnl >= 0 else "inverse")
    with col5:
        pnl_pct = portfolio["total_pnl_pct"]
        st.metric(t("portfolio.pnl_pct", lang), f"{pnl_pct:+.2f}%",
                  delta=f"{pnl_pct:+.2f}%", delta_color="normal" if pnl_pct >= 0 else "inverse")

    st.markdown(
        f'<p style="color:#86868b;font-size:0.8rem;">{t("portfolio.alloc_hint", lang)}</p>',
        unsafe_allow_html=True,
    )

    high_corr = portfolio.get("high_corr_pairs", [])
    if high_corr:
        with st.expander(t("portfolio.high_corr", lang), expanded=True):
            st.caption(t("portfolio.high_corr_desc", lang))
            for t1, t2, val in high_corr:
                st.warning(f"**{t1}** ↔ **{t2}**: ρ = {val:.3f}")

    stop_hit = [p for p in positions if p.get("stop_hit")]
    if stop_hit:
        for p in stop_hit:
            st.error(f"{t('portfolio.stop_hit', lang)} — **{p['ticker']}** @ ${p['current_price']:.2f} (SL: ${p['stop_loss']:.2f})")

    st.subheader(t("portfolio.positions", lang))
    pos_rows = []
    for p in positions:
        pos_rows.append({
            "Ticker": p["ticker"],
            t("portfolio.score", lang): p["total_score"],
            t("portfolio.weight", lang): f"{p['weight']*100:.1f}%",
            t("portfolio.shares", lang): p["shares"],
            t("portfolio.entry_price", lang): f"${p['entry_price']:.2f}",
            t("portfolio.current_price", lang): f"${p['current_price']:.2f}",
            t("portfolio.pnl", lang): f"${p['pnl']:+,.0f}",
            t("portfolio.pnl_pct", lang): f"{p['pnl_pct']:+.1f}%",
            t("portfolio.stop_loss", lang): f"${p['stop_loss']:.2f}",
            t("portfolio.target", lang): f"${p['target_price']:.2f}" if p.get("target_price") else "N/A",
        })
    import pandas as pd
    st.dataframe(pd.DataFrame(pos_rows), hide_index=True, use_container_width=True, height=400)

    with st.expander(t("portfolio.journal", lang)):
        from agents.portfolio_manager import get_journal
        journal = get_journal()
        if journal:
            import pandas as _pd
            st.dataframe(_pd.DataFrame(journal), hide_index=True, use_container_width=True, height=300)
        else:
            st.caption(t("portfolio.journal_empty", lang))

    if st.button(t("portfolio.reset", lang), type="secondary"):
        from agents.portfolio_manager import reset_portfolio
        reset_portfolio(capital=st.session_state.get("portfolio_capital", 100000))
        st.session_state.portfolio = {}
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Stock Analyzer", page_icon="📈", layout="wide")
    init_state()
    _inject_apple_css()

    st.markdown("""<script>
try {
  const l=document.createElement('link'); l.rel='manifest'; l.href='/manifest.json';
  document.head.appendChild(l);
  const m=document.createElement('meta'); m.name='apple-mobile-web-app-capable'; m.content='yes';
  document.head.appendChild(m);
  if('serviceWorker'in navigator) navigator.serviceWorker.register('/sw.js',{scope:'/'});
} catch(e){}
</script>""", unsafe_allow_html=True)

    lang = st.session_state.get("lang", "zh_tw")

    st.markdown(f'<p class="app-title">📈 {t("app.title", lang)}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="app-subtitle">{t("app.subtitle", lang)}</p>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    params = build_sidebar()

    show_source_health()
    st.sidebar.markdown("<hr style='margin:1.2rem 0;'>", unsafe_allow_html=True)
    export_csv()

    if params.get("run_clicked"):
        if not params.get("selected_tickers"):
            st.error(t("sidebar.select_stock", lang))
        else:
            run_analysis(params)

    show_tabs = st.session_state.analysis_done and st.session_state.recommendations
    tab_labels = [t("tab.pool", lang), t("tab.backtest", lang)]
    if show_tabs:
        tab_labels += [
            t("tab.portfolio", lang), t("tab.recommend", lang), t("tab.ranking", lang),
            t("tab.compare", lang), t("tab.valuation", lang), t("tab.charts", lang),
            t("tab.news", lang), t("industry_news.title", lang), t("tab.ai", lang),
        ]
    else:
        tab_labels.append("🏠 " + t("app.title", lang))

    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_stock_pool_tab()
    with tabs[1]:
        render_backtest_tab()

    if show_tabs:
        with tabs[2]:
            render_portfolio_tab()
        with tabs[3]:
            render_recommendations_tab()
        with tabs[4]:
            render_rankings_tab()
        with tabs[5]:
            render_compare_tab()
        with tabs[6]:
            render_valuation_tab()
        with tabs[7]:
            render_charts_tab()
        with tabs[8]:
            render_news_tab()
        with tabs[9]:
            render_industry_news_tab()
        with tabs[10]:
            render_ai_status_tab()
    elif not st.session_state.analysis_done:
        st.markdown(f"<p style='color:#86868b;'>{t('app.start_hint', lang)}</p>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<div class='feature-card'><h3>📊 {t('app.feature1', lang)}</h3><p>{t('app.feature1.desc', lang)}</p></div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<div class='feature-card'><h3>📈 {t('app.feature2', lang)}</h3><p>{t('app.feature2.desc', lang)}</p></div>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<div class='feature-card'><h3>🔄 {t('app.feature3', lang)}</h3><p>{t('app.feature3.desc', lang)}</p></div>", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<div class='feature-card'><h3>💎 {t('app.feature4', lang)}</h3><p>{t('app.feature4.desc', lang)}</p></div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
