import math
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import yfinance as yf
from agents import function_tool
from statusTools import mark_getting_stock_price, clear_tool_status


def _is_num(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _round_price(x: float) -> float:
    """Round low-priced tickers more precisely, others to 2 decimals."""
    if x is None:
        return None
    return round(x, 4) if abs(x) < 1 else round(x, 2)


@function_tool
def get_stock_price(ticker: str) -> dict | None:
    """
    Fetch the freshest available price and daily change for a ticker using yfinance.

    Args:
        ticker (str): e.g., "AAPL", "MSFT".

    Returns:
        dict | None: {
            "price": float,
            "change": float,
            "change_percent": float,
            "prev_close": float | None,
            "currency": str | None,
            "source": str,
            "timestamp_utc": str
        }
    """
    mark_getting_stock_price()
    try:
        t = yf.Ticker(ticker)
        now = time.time()
        price = None
        source = None
        currency = None
        prev_close = None

        fi = getattr(t, "fast_info", None)
        if fi:
            currency = getattr(fi, "currency", None)

            # previous close
            pc = getattr(fi, "previous_close", None)
            if _is_num(pc):
                prev_close = float(pc)

            # prefer extended session prices when present
            for val, src in ((getattr(fi, "post_market_price", None), "fast_info_post"),
                             (getattr(fi, "pre_market_price", None), "fast_info_pre"),
                             (getattr(fi, "last_price", None), "fast_info")):
                if _is_num(val):
                    price = float(val)
                    source = src
                    break

        # ---------- 2) Intraday 1-minute bar fallback ----------
        if price is None:
            try:
                hist_1m = t.history(period="1d", interval="1m", prepost=True)
                if not hist_1m.empty:
                    last_close = float(hist_1m["Close"].iloc[-1])
                    last_ts = hist_1m.index[-1].to_pydatetime().timestamp()
                    # treat the 1m bar as fresh if within ~3 minutes
                    if _is_num(last_close) and (now - last_ts) <= 180:
                        price = last_close
                        source = "intraday_1m"
                        now = last_ts
            except Exception:
                pass

        # ---------- 3) Regular last close fallback ----------
        if price is None:
            hist_1d = t.history(period="1d")
            if not hist_1d.empty:
                price = float(hist_1d["Close"].iloc[-1])
                source = "prev_close"

        # Ensure we have previous close (for change calc)
        if prev_close is None:
            try:
                hist_2d = t.history(period="2d")
                if not hist_2d.empty and len(hist_2d) >= 2:
                    prev_close = float(hist_2d["Close"].iloc[-2])
            except Exception:
                pass

        if not _is_num(price):
            return None

        # Calculate changes if we have prev_close
        if _is_num(prev_close) and prev_close:
            change = price - prev_close
            change_pct = (change / prev_close) * 100
        else:
            change = None
            change_pct = None

        return {
            "price": _round_price(price),
            "change": _round_price(change) if change is not None else None,
            "change_percent": round(change_pct, 4) if change_pct is not None else None,
            "prev_close": _round_price(prev_close) if prev_close is not None else None,
            "currency": currency,
            "source": source or "unknown",
            "timestamp_utc": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
        }

    except Exception:
        return None
    finally:
        clear_tool_status()
