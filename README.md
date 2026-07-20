# 📈 AI Stock Analyzer / AI 智能選股分析師

[![Streamlit App](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://stock-analyzergit-ijue4vuwb7kuvizn62fema.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **AI-powered US stock screener** — fundamental scoring, portfolio management, backtesting, and LLM-assisted analysis.  
> **AI 驅動的美股篩選器** — 基本面評分、投資組合管理、回測驗證、LLM 輔助分析。

---

## 🌟 Features / 功能特色

### 📊 Fundamental Scoring / 基本面評分

| Metric / 指標 | Weight / 權重 |
|--------------|-------------|
| Revenue Growth / 營收增長 | 25% |
| EPS Growth / 每股盈餘增長 | 20% |
| Profit Margin / 淨利潤率 | 10% |
| PEG Ratio / PEG 比率 | 15% |
| ROE / 股東權益報酬率 | 10% |
| Debt-to-Equity / 負債權益比 | 5% |

### 🤖 LLM-Assisted Analysis / LLM 輔助分析

- Quant (80%) + LLM sentiment (20%) blended scoring
- 量化評分 80% + LLM 情緒評分 20% 混合加權
- Adjustable LLM influence via sidebar slider
- 可透過側邊欄滑桿調整 LLM 影響權重

### 📋 Portfolio Management / 投資組合管理

- Kelly Criterion position sizing (max 25% per position, 90% total)
- 凱利公式倉位管理（單一部位上限 25%，總倉位上限 90%）
- Trade journal with automated buy logging
- 交易日記自動記錄買入
- P&L tracking per position + portfolio level
- 個股與組合層級損益追蹤
- Correlation check (flags pairs with ρ ≥ 0.80)
- 相關性檢查（標記 ρ ≥ 0.80 的配對）
- Stop-loss management (beta-based, default 10%)
- 止損管理（基於 Beta，預設 10%）

### 📈 Backtesting / 回測驗證

- Walk-forward validation across 5 years
- 5 年滾動驗證
- Monthly rebalancing simulation vs SPY benchmark
- 每月再平衡模擬，對比 SPY 基準

### 💹 Technical Analysis / 技術分析

- RSI, MACD, Bollinger Bands, SMA crossover signals
- RSI、MACD、布林通道、SMA 交叉訊號
- Used as tiebreaker for top candidates (top 15 by score)
- 作為頂尖候選股（前 15 名）的輔助判斷

### 🔍 Risk Metrics / 風險指標

- VaR 95%, Sharpe/Sortino Ratio, Max Drawdown, Beta, Volatility
- VaR 95%、夏普/索提諾比率、最大回撤、Beta、波動率

### 🌐 Multi-Language UI / 多語言介面

- English / 简体中文 / 繁體中文
- Sector names, risk labels, and analysis reports all localized
- 行業名稱、風險標籤、分析報告皆已本地化

### 🗞️ News Sentiment / 新聞情緒分析

- Real-time news fetching via Sina Finance (fallback: Yahoo Finance)
- 通過新浪財經即時獲取新聞（備援：Yahoo Finance）
- Keyword-based sentiment classification
- 基於關鍵字的情緒分類

---

## 🏗 Architecture / 系統架構

```
├── backend/
│   ├── app.py                      # Streamlit Web UI
│   ├── run_agent.py                # CLI mode / 命令列模式
│   ├── i18n.py                     # Multi-language (en/zh_cn/zh_tw)
│   │
│   ├── agents/
│   │   ├── data_fetcher.py         # Data fetching (yfinance → Sina/EM → seed fallback)
│   │   ├── china_data_fetcher.py   # Chinese data sources (新浪 + 東方財富)
│   │   ├── seed_data.py            # Offline seed data for 44 US stocks
│   │   ├── fundamental_analyzer.py # Core scoring engine / 核心評分引擎
│   │   ├── recommender.py          # Analysis orchestrator / 分析編排
│   │   ├── sec_analyzer.py         # SEC EDGAR 10-K/10-Q analysis
│   │   ├── technical_analyzer.py   # RSI, MACD, BB, SMA
│   │   ├── portfolio_manager.py    # Kelly sizing, P&L tracking
│   │   ├── llm_agent.py            # OpenAI/LLM integration
│   │   ├── auto_upgrader.py        # Self-diagnosis & upgrade logging
│   │   └── trading_strategies.py   # Strategy backtesting engine
│   │
│   ├── backtesting/
│   │   └── engine.py               # Walk-forward backtesting
│   │
│   ├── utils/
│   │   ├── constants.py            # Config (stock pool, weights)
│   │   ├── cache.py                # Memory + disk cache
│   │   └── price_utils.py          # Price helpers
│   │
│   └── data/                       # Cached data, trade journal, portfolio state
│
├── requirements.txt
└── runtime.txt                     # Python 3.12 for Streamlit Cloud
```

---

## 🚀 Quick Start / 快速開始

```bash
# Clone / 克隆
git clone https://github.com/cgabrielck/stock-analyzer.git
cd stock-analyzer

# Install / 安裝依賴
pip install -r requirements.txt

# Launch Web UI / 啟動網頁介面
streamlit run backend/app.py

# Or CLI mode / 或命令列模式
python backend/run_agent.py
```

### Environment Variables / 環境變數 (optional)

```env
OPENAI_API_KEY=sk-...   # Enables LLM analysis / 啟用 LLM 分析
```

---

## 🔌 Data Sources / 數據來源

The system uses a **fallback chain** to ensure data availability everywhere:

```
yfinance (local) → Sina Finance + East Money (cloud) → Seed Data (offline)
```

| Source / 來源 | Purpose / 用途 | Cloud / 雲端 |
|-------------|--------------|------------|
| **Yahoo Finance** (yfinance) | Real-time price, financials, options, ESG | ❌ Blocked |
| **Sina Finance / 新浪財經** | Real-time quote, PE, market cap (HTTP API) | ✅ Works |
| **East Money / 東方財富** (AKShare) | Revenue, EPS, ROE, debt/equity financials | ✅ Works |
| **Seed Data / 種子數據** | Offline fallback for all 44 stocks | ✅ Always |

44 US stocks across 10 sectors: Semiconductors, Technology, Healthcare, Financial, Consumer, Industrials, Energy, Space, Memory & Storage, Defense & Aerospace.

---

## ☁️ Deploy to Streamlit Cloud / 部署到 Streamlit Cloud

1. Push to GitHub
2. Connect repo at [share.streamlit.io](https://share.streamlit.io)
3. Set main file: `backend/app.py`
4. Add `OPENAI_API_KEY` in Secrets if desired

The app auto-deploys on every push to `main`.

---

## 📸 Screenshots / 介面截圖

| Tab / 分頁 | Description / 說明 |
|-----------|------------------|
| 📋 **Stock Pool** | Browse 44 stocks by sector |
| 📊 **Backtest** | 5-year walk-forward validation vs SPY |
| 💼 **Portfolio** | Kelly-sized positions, P&L, trade journal |
| 🏆 **Recommend** | Top 5 picks with detailed reasoning |
| 📊 **Rankings** | Full 44-stock ranking table |
| 🔍 **Compare** | Side-by-side stock comparison |
| 📐 **Valuation** | P/E, P/S, P/B, EV/EBITDA charts |
| 📈 **Charts** | Price history with technical overlays |
| 📰 **News** | Per-stock news with sentiment |
| 🏭 **Industry News** | Sector-level news aggregation |
| 🤖 **AI** | Agent logs, cache status, LLM settings |

---

## 🧪 Tech Stack / 技術棧

- **Python** 3.12+ (3.14 locally, 3.12 on cloud via `runtime.txt`)
- **Streamlit** — Web UI framework
- **yfinance** / **AKShare** — Market data
- **Pandas**, **NumPy** — Data processing
- **Plotly**, **Altair** — Charts & visualization
- **OpenAI API** — LLM analysis (optional)
- **BeautifulSoup4**, **Requests** — Web scraping

---

## ⚠️ Disclaimer / 免責聲明

**English:** This tool is for **educational and research purposes only**. It does not constitute financial advice. Past performance does not guarantee future results. Always do your own research before investing.

**繁體中文：** 本工具僅供 **教育與研究用途**，不構成任何投資建議。過往表現不代表未來成果。投資有風險，入市前請自行研究評估。

---

## 📄 License / 授權

MIT License — see [LICENSE](LICENSE) file.
