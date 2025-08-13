import yfinance as yf
from agents import function_tool
from statusTools import mark_getting_stock_price, clear_tool_status

@function_tool
def get_stock_price(ticker: str) -> dict:
    """
    Fetch the latest stock price and daily change for the given ticker symbol.

    Args:
        ticker (str): Stock ticker symbol (e.g., 'AAPL', 'MSFT').

    Returns:
        dict: {
            "price": float,
            "change": float,          # absolute change from previous close
            "change_percent": float   # percentage change from previous close
        } or None if not available.
    """
    mark_getting_stock_price()
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period="2d")  # Need 2 days for previous close
        if len(data) >= 2:
            prev_close = data['Close'].iloc[-2]
            price = data['Close'].iloc[-1]
            change = price - prev_close
            change_percent = (change / prev_close) * 100 if prev_close else None
            return {
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2) if change_percent is not None else None
            }
        else:
            print(f"No sufficient data found for ticker: {ticker}")
            return None
    except Exception as e:
        print(f"Error fetching stock price for {ticker}: {e}")
        return None
    finally:
        clear_tool_status()
