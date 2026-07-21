import os
from typing import Any, Dict, List, Optional

DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

CIK_MAP_URL: str = "https://www.sec.gov/files/company_tickers.json"

SECTOR_EN_MAP: Dict[str, str] = {
    "Semiconductors": "Semiconductors",
    "Technology": "Technology",
    "Healthcare": "Healthcare",
    "Financial": "Financial",
    "Consumer": "Consumer",
    "Industrials": "Industrials",
    "Energy": "Energy",
    "Space": "Space",
    "Memory & Storage": "Memory & Storage",
    "Defense & Aerospace": "Defense & Aerospace",
    "Consumer Staples": "Consumer Staples",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Communication Services": "Communication Services",
    "Other": "Other",
}

SECTOR_CN_MAP: Dict[str, str] = {
    "Semiconductors": "半导体",
    "Technology": "科技软件",
    "Healthcare": "医疗保健",
    "Financial": "金融服务",
    "Consumer": "消费零售",
    "Industrials": "工业",
    "Energy": "能源",
    "Space": "太空",
    "Memory & Storage": "内存存储",
    "Defense & Aerospace": "国防航天",
    "Consumer Staples": "必需消费",
    "Utilities": "公用事业",
    "Real Estate": "房地产",
    "Communication Services": "通信服务",
    "Other": "其他",
}

SECTOR_TW_MAP: Dict[str, str] = {
    "Semiconductors": "半導體",
    "Technology": "科技軟體",
    "Healthcare": "醫療保健",
    "Financial": "金融服務",
    "Consumer": "消費零售",
    "Industrials": "工業",
    "Energy": "能源",
    "Space": "太空",
    "Memory & Storage": "記憶體存儲",
    "Defense & Aerospace": "國防航太",
    "Consumer Staples": "必需消費",
    "Utilities": "公用事業",
    "Real Estate": "房地產",
    "Communication Services": "通訊服務",
    "Other": "其他",
}

STOCK_UNIVERSE: List[Dict[str, str]] = [
    {"ticker": "NVDA", "name_cn": "英伟达", "name_tw": "輝達", "name_en": "NVIDIA", "sector": "Semiconductors", "universe_tier": "core"},
    {"ticker": "AMD", "name_cn": "超微半导体", "name_tw": "超微半導體", "name_en": "AMD", "sector": "Semiconductors"},
    {"ticker": "AVGO", "name_cn": "博通", "name_tw": "博通", "name_en": "Broadcom", "sector": "Semiconductors"},
    {"ticker": "MU", "name_cn": "美光科技", "name_tw": "美光科技", "name_en": "Micron Technology", "sector": "Semiconductors"},
    {"ticker": "INTC", "name_cn": "英特尔", "name_tw": "英特爾", "name_en": "Intel", "sector": "Semiconductors"},
    {"ticker": "QCOM", "name_cn": "高通", "name_tw": "高通", "name_en": "Qualcomm", "sector": "Semiconductors"},
    {"ticker": "TXN", "name_cn": "德州仪器", "name_tw": "德州儀器", "name_en": "Texas Instruments", "sector": "Semiconductors"},
    {"ticker": "AAPL", "name_cn": "苹果", "name_tw": "蘋果", "name_en": "Apple", "sector": "Technology"},
    {"ticker": "MSFT", "name_cn": "微软", "name_tw": "微軟", "name_en": "Microsoft", "sector": "Technology"},
    {"ticker": "META", "name_cn": "Meta", "name_tw": "Meta", "name_en": "Meta", "sector": "Communication Services"},
    {"ticker": "GOOGL", "name_cn": "谷歌", "name_tw": "谷歌", "name_en": "Google", "sector": "Communication Services"},
    {"ticker": "NOW", "name_cn": "ServiceNow", "name_tw": "ServiceNow", "name_en": "ServiceNow", "sector": "Technology"},
    {"ticker": "CRM", "name_cn": "赛富时", "name_tw": "賽富時", "name_en": "Salesforce", "sector": "Technology"},
    {"ticker": "NFLX", "name_cn": "奈飞", "name_tw": "網飛", "name_en": "Netflix", "sector": "Communication Services"},
    {"ticker": "LLY", "name_cn": "礼来", "name_tw": "禮來", "name_en": "Eli Lilly", "sector": "Healthcare"},
    {"ticker": "UNH", "name_cn": "联合健康", "name_tw": "聯合健康", "name_en": "UnitedHealth", "sector": "Healthcare"},
    {"ticker": "ISRG", "name_cn": "直觉外科", "name_tw": "直覺外科", "name_en": "Intuitive Surgical", "sector": "Healthcare"},
    {"ticker": "VRTX", "name_cn": "福泰制药", "name_tw": "福泰製藥", "name_en": "Vertex Pharmaceuticals", "sector": "Healthcare"},
    {"ticker": "AMGN", "name_cn": "安进", "name_tw": "安進", "name_en": "Amgen", "sector": "Healthcare"},
    {"ticker": "GILD", "name_cn": "吉利德科学", "name_tw": "吉列德科學", "name_en": "Gilead Sciences", "sector": "Healthcare"},
    {"ticker": "V", "name_cn": "Visa", "name_tw": "Visa", "name_en": "Visa", "sector": "Financial"},
    {"ticker": "MA", "name_cn": "万事达", "name_tw": "萬事達", "name_en": "Mastercard", "sector": "Financial"},
    {"ticker": "JPM", "name_cn": "摩根大通", "name_tw": "摩根大通", "name_en": "JPMorgan Chase", "sector": "Financial"},
    {"ticker": "AMZN", "name_cn": "亚马逊", "name_tw": "亞馬遜", "name_en": "Amazon", "sector": "Consumer"},
    {"ticker": "TSLA", "name_cn": "特斯拉", "name_tw": "特斯拉", "name_en": "Tesla", "sector": "Consumer"},
    {"ticker": "HD", "name_cn": "家得宝", "name_tw": "家得寶", "name_en": "Home Depot", "sector": "Consumer"},
    {"ticker": "NKE", "name_cn": "耐克", "name_tw": "耐吉", "name_en": "Nike", "sector": "Consumer"},
    {"ticker": "SBUX", "name_cn": "星巴克", "name_tw": "星巴克", "name_en": "Starbucks", "sector": "Consumer"},
    {"ticker": "COST", "name_cn": "好市多", "name_tw": "好市多", "name_en": "Costco", "sector": "Consumer"},
    {"ticker": "WMT", "name_cn": "沃尔玛", "name_tw": "沃爾瑪", "name_en": "Walmart", "sector": "Consumer"},
    {"ticker": "RIVN", "name_cn": "Rivian", "name_tw": "Rivian", "name_en": "Rivian Automotive", "sector": "Consumer"},
    {"ticker": "LI", "name_cn": "理想汽车", "name_tw": "理想汽車", "name_en": "Li Auto", "sector": "Consumer"},
    {"ticker": "CAT", "name_cn": "卡特彼勒", "name_tw": "卡特彼勒", "name_en": "Caterpillar", "sector": "Industrials"},
    {"ticker": "HON", "name_cn": "霍尼韦尔", "name_tw": "霍尼韋爾", "name_en": "Honeywell", "sector": "Industrials"},
    {"ticker": "GE", "name_cn": "通用电气", "name_tw": "通用電氣", "name_en": "General Electric", "sector": "Industrials"},
    {"ticker": "XOM", "name_cn": "埃克森美孚", "name_tw": "埃克森美孚", "name_en": "ExxonMobil", "sector": "Energy"},
    {"ticker": "COP", "name_cn": "康菲石油", "name_tw": "康菲石油", "name_en": "ConocoPhillips", "sector": "Energy"},
    {"ticker": "RKLB", "name_cn": "火箭实验室", "name_tw": "火箭實驗室", "name_en": "Rocket Lab USA", "sector": "Space"},
    {"ticker": "ASTS", "name_cn": "AST SpaceMobile", "name_tw": "AST SpaceMobile", "name_en": "AST SpaceMobile", "sector": "Space"},
    {"ticker": "LUNR", "name_cn": "Intuitive Machines", "name_tw": "Intuitive Machines", "name_en": "Intuitive Machines", "sector": "Space"},
    {"ticker": "WDC", "name_cn": "西部数据", "name_tw": "西部數據", "name_en": "Western Digital", "sector": "Memory & Storage"},
    {"ticker": "STX", "name_cn": "希捷科技", "name_tw": "希捷科技", "name_en": "Seagate Technology", "sector": "Memory & Storage"},
    {"ticker": "RTX", "name_cn": "雷神技术", "name_tw": "雷神技術", "name_en": "RTX Corporation", "sector": "Defense & Aerospace"},
    {"ticker": "LMT", "name_cn": "洛克希德·马丁", "name_tw": "洛克希德·馬丁", "name_en": "Lockheed Martin", "sector": "Defense & Aerospace"},
    {"ticker": "TSM", "name_cn": "台积电", "name_tw": "台積電", "name_en": "Taiwan Semiconductor", "sector": "Semiconductors"},
    {"ticker": "ASML", "name_cn": "阿斯麦", "name_tw": "艾司摩爾", "name_en": "ASML", "sector": "Semiconductors"},
    {"ticker": "AMAT", "name_cn": "应用材料", "name_tw": "應用材料", "name_en": "Applied Materials", "sector": "Semiconductors"},
    {"ticker": "LRCX", "name_cn": "泛林集团", "name_tw": "科林研發", "name_en": "Lam Research", "sector": "Semiconductors"},
    {"ticker": "ORCL", "name_cn": "甲骨文", "name_tw": "甲骨文", "name_en": "Oracle", "sector": "Technology"},
    {"ticker": "ADBE", "name_cn": "奥多比", "name_tw": "Adobe", "name_en": "Adobe", "sector": "Technology"},
    {"ticker": "ACN", "name_cn": "埃森哲", "name_tw": "埃森哲", "name_en": "Accenture", "sector": "Technology"},
    {"ticker": "CSCO", "name_cn": "思科", "name_tw": "思科", "name_en": "Cisco", "sector": "Technology"},
    {"ticker": "JNJ", "name_cn": "强生", "name_tw": "嬌生", "name_en": "Johnson & Johnson", "sector": "Healthcare"},
    {"ticker": "MRK", "name_cn": "默沙东", "name_tw": "默沙東", "name_en": "Merck", "sector": "Healthcare"},
    {"ticker": "ABBV", "name_cn": "艾伯维", "name_tw": "艾伯維", "name_en": "AbbVie", "sector": "Healthcare"},
    {"ticker": "TMO", "name_cn": "赛默飞世尔", "name_tw": "賽默飛世爾", "name_en": "Thermo Fisher", "sector": "Healthcare"},
    {"ticker": "BAC", "name_cn": "美国银行", "name_tw": "美國銀行", "name_en": "Bank of America", "sector": "Financial"},
    {"ticker": "GS", "name_cn": "高盛", "name_tw": "高盛", "name_en": "Goldman Sachs", "sector": "Financial"},
    {"ticker": "MS", "name_cn": "摩根士丹利", "name_tw": "摩根士丹利", "name_en": "Morgan Stanley", "sector": "Financial"},
    {"ticker": "BRK-B", "name_cn": "伯克希尔", "name_tw": "波克夏", "name_en": "Berkshire Hathaway", "sector": "Financial"},
    {"ticker": "CVX", "name_cn": "雪佛龙", "name_tw": "雪佛龍", "name_en": "Chevron", "sector": "Energy"},
    {"ticker": "SLB", "name_cn": "斯伦贝谢", "name_tw": "斯倫貝謝", "name_en": "SLB", "sector": "Energy"},
    {"ticker": "DE", "name_cn": "迪尔", "name_tw": "迪爾", "name_en": "Deere", "sector": "Industrials"},
    {"ticker": "UNP", "name_cn": "联合太平洋", "name_tw": "聯合太平洋", "name_en": "Union Pacific", "sector": "Industrials"},
    {"ticker": "UPS", "name_cn": "联合包裹", "name_tw": "優比速", "name_en": "UPS", "sector": "Industrials"},
    {"ticker": "PG", "name_cn": "宝洁", "name_tw": "寶僑", "name_en": "Procter & Gamble", "sector": "Consumer Staples"},
    {"ticker": "KO", "name_cn": "可口可乐", "name_tw": "可口可樂", "name_en": "Coca-Cola", "sector": "Consumer Staples"},
    {"ticker": "PEP", "name_cn": "百事", "name_tw": "百事", "name_en": "PepsiCo", "sector": "Consumer Staples"},
    {"ticker": "CL", "name_cn": "高露洁", "name_tw": "高露潔", "name_en": "Colgate-Palmolive", "sector": "Consumer Staples"},
    {"ticker": "NEE", "name_cn": "新纪元能源", "name_tw": "新紀元能源", "name_en": "NextEra Energy", "sector": "Utilities"},
    {"ticker": "DUK", "name_cn": "杜克能源", "name_tw": "杜克能源", "name_en": "Duke Energy", "sector": "Utilities"},
    {"ticker": "SO", "name_cn": "南方电力", "name_tw": "南方電力", "name_en": "Southern Company", "sector": "Utilities"},
    {"ticker": "PLD", "name_cn": "安博", "name_tw": "普洛斯", "name_en": "Prologis", "sector": "Real Estate"},
    {"ticker": "AMT", "name_cn": "美国电塔", "name_tw": "美國電塔", "name_en": "American Tower", "sector": "Real Estate"},
]

SATELLITE_TICKERS = {"RIVN", "LI", "RKLB", "ASTS", "LUNR"}
for _stock in STOCK_UNIVERSE:
    _stock["universe_tier"] = "satellite" if _stock["ticker"] in SATELLITE_TICKERS else "core"

SCORING_WEIGHTS: Dict[str, float] = {
    "revenue_growth": 0.25,
    "eps_growth": 0.20,
    "profit_margin": 0.10,
    "peg_ratio": 0.15,
    "roe": 0.10,
    "debt_equity": 0.05,
}

CACHE_TTL: Dict[str, int] = {
    "price": 300,
    "info": 300,
    "financials": 86400,
    "sec_filings": 86400,
    "cik_map": 86400,
}

SEC_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/html, application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

VALUATION_LABELS: Dict[str, str] = {
    "pe_ratio": "市盈率 (P/E)",
    "peg": "PEG 比率",
    "ps_ratio": "市销率 (P/S)",
    "pb_ratio": "市净率 (P/B)",
    "ev_ebitda": "EV/EBITDA",
}

VALUATION_RANGES: Dict[str, List[float]] = {
    "pe_ratio": [0, 15, 25],
    "peg": [0, 1, 2],
    "ps_ratio": [0, 2, 5],
    "pb_ratio": [0, 1, 3],
    "ev_ebitda": [0, 10, 15],
}
