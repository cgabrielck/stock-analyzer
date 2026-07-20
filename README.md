# 📈 AI 智能选股分析师

基于基本面分析的美股成长股推荐系统，覆盖 30 只美国各行业龙头股票。

## 功能

- **基本面评分** — 基于营收增长、EPS 增长、利润率、PEG、ROE、负债权益比的加权评分
- **行业分散推荐** — 从各行业中精选评分最高的股票，确保投资组合多元化
- **SEC 财报分析** — 自动获取并分析 SEC EDGAR 10-K/10-Q 官方文件
- **AI 自动升级** — 持续追踪数据源健康度，自动检测问题和推荐优化

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 界面
streamlit run backend/app.py

# 或使用 CLI 版本
python backend/run_agent.py
```

## 项目结构

```
stock-analyzer/
├── backend/
│   ├── app.py                 # Streamlit Web UI
│   ├── run_agent.py           # CLI 版本
│   ├── agents/
│   │   ├── data_fetcher.py    # 数据获取 (yfinance + fallback)
│   │   ├── fundamental_analyzer.py  # 基本面评分引擎
│   │   ├── sec_analyzer.py    # SEC EDGAR 财报分析
│   │   ├── recommender.py     # 分析编排 & 推荐生成
│   │   └── auto_upgrader.py   # AI 自动升级系统
│   └── utils/
│       ├── constants.py       # 配置 (股票池、评分权重)
│       └── cache.py           # 内存 + 文件两级缓存
├── requirements.txt
└── .gitignore
```

## 数据来源

- [Yahoo Finance](https://finance.yahoo.com/) — 实时股价与财务报表数据
- [SEC EDGAR](https://www.sec.gov/edgar/) — 官方 10-K/10-Q 申报文件

## 免责声明

本分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。
