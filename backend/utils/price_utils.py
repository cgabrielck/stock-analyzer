from typing import Any, Optional, Tuple

import yfinance as yf


def get_latest_price(stock: yf.Ticker, fallback_close: Optional[float] = None) -> Tuple[Optional[float], str]:
    price = fallback_close
    session = "Regular Trading Hours"

    try:
        info = stock.info
        pre = info.get("preMarketPrice")
        post = info.get("postMarketPrice")
        regular = info.get("currentPrice") or info.get("regularMarketPrice")

        if pre is not None:
            price = pre
            session = "Pre-Market Trading"
        elif post is not None:
            price = post
            session = "After-Hours Trading"
        elif regular is not None:
            price = regular
            session = "Regular Trading Hours"
        else:
            hist = stock.history(period="2d", prepost=True)
            if hist is not None and not hist.empty:
                price = float(hist["Close"].iloc[-1])
                hour = hist.index[-1].hour
                if hour < 4:
                    session = "Overnight Trading"
                elif hour < 9:
                    session = "Pre-Market Trading"
                elif hour < 16:
                    session = "Regular Trading Hours"
                else:
                    session = "After-Hours Trading"
    except Exception:
        pass

    return price, session
