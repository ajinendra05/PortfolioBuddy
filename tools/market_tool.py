import yfinance as yf
import pandas as pd
# import pandas_ta as ta
from langchain_core.tools import tool
# from backend.services.cache_service import get_cached, set_cached

@tool
def get_stock_info(symbol: str) -> dict:
    """
    Fetch fundamental data for a stock symbol.
    Use NSE suffix for Indian stocks: RELIANCE.NS, HDFCBANK.NS, TCS.NS
    """
    cache_key = f"stock_info:{symbol}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    ticker = yf.Ticker(symbol)
    info = ticker.info

    result = {
        "symbol": symbol,
        "name": info.get("longName", symbol),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "pb_ratio": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "description": info.get("longBusinessSummary", "")[:500],
    }

    # set_cached(cache_key, result, ttl=900)  # cache 15 min
    return result

# functions to compute technical indicators 

def _calculate_rsi(df: pd.DataFrame, period: int = 14):
    close = df["Close"]

    delta = close.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss

    df["RSI_14"] = 100 - (100 / (1 + rs))

    return df


def _calculate_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    close = df["Close"]

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()

    df["MACD_12_26_9"] = macd
    df["MACDs_12_26_9"] = macd_signal
    df["MACDh_12_26_9"] = macd - macd_signal

    return df


def _calculate_bollinger_bands(
    df: pd.DataFrame,
    length: int = 20,
    std_dev: float = 2.0,
):
    close = df["Close"]

    sma = close.rolling(length).mean()
    std = close.rolling(length).std()

    df["BBM_20_2.0"] = sma
    df["BBU_20_2.0"] = sma + (std * std_dev)
    df["BBL_20_2.0"] = sma - (std * std_dev)

    return df


def _calculate_ema(df: pd.DataFrame, length: int):
    df[f"EMA_{length}"] = (
        df["Close"]
        .ewm(span=length, adjust=False)
        .mean()
    )

    return df


def _add_indicators(df: pd.DataFrame):
    """
    Replaces pandas-ta calculations.
    """

    df = _calculate_rsi(df, 14)

    df = _calculate_macd(
        df,
        fast=12,
        slow=26,
        signal=9,
    )

    df = _calculate_bollinger_bands(
        df,
        length=20,
        std_dev=2.0,
    )

    df = _calculate_ema(df, 20)
    df = _calculate_ema(df, 50)

    return df



@tool
def get_technical_analysis(symbol: str, period: str = "3mo") -> dict:
    """
    Compute technical indicators: RSI, MACD, Bollinger Bands, EMA.
    period options: 1mo, 3mo, 6mo, 1y
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)

    if df.empty:
        return {"error": f"No data found for {symbol}"}

    # Calculate indicators using pandas-ta
    # df.ta.rsi(length=14, append=True)
    # df.ta.macd(fast=12, slow=26, signal=9, append=True)
    # df.ta.bbands(length=20, append=True)
    # df.ta.ema(length=20, append=True)
    # df.ta.ema(length=50, append=True)

    df = _add_indicators(df)
    latest = df.iloc[-1]

    return {
        "symbol": symbol,
        "last_close": round(float(latest["Close"]), 2),
        "rsi_14": round(float(latest.get("RSI_14", 0)), 2),
        "macd": round(float(latest.get("MACD_12_26_9", 0)), 4),
        "macd_signal": round(float(latest.get("MACDs_12_26_9", 0)), 4),
        "bb_upper": round(float(latest.get("BBU_20_2.0", 0)), 2),
        "bb_lower": round(float(latest.get("BBL_20_2.0", 0)), 2),
        "ema_20": round(float(latest.get("EMA_20", 0)), 2),
        "ema_50": round(float(latest.get("EMA_50", 0)), 2),
        "volume": int(latest["Volume"]),
        "signal": _derive_signal(latest),
    }


def _derive_signal(row) -> str:
    """Simple rule-based signal from indicators"""
    rsi = float(row.get("RSI_14", 50))
    macd = float(row.get("MACD_12_26_9", 0))
    macd_signal = float(row.get("MACDs_12_26_9", 0))

    if rsi < 30 and macd > macd_signal:
        return "STRONG BUY"
    elif rsi < 45 and macd > macd_signal:
        return "BUY"
    elif rsi > 70 and macd < macd_signal:
        return "STRONG SELL"
    elif rsi > 55 and macd < macd_signal:
        return "SELL"
    else:
        return "NEUTRAL"


@tool
def get_candlestick_data(symbol: str, period: str = "3mo", interval: str = "1d") -> dict:
    """
    Fetch OHLCV candlestick data for charting.
    interval options: 1d, 1wk, 1mo
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        return {"error": f"No data for {symbol}"}

    candles = []
    for date, row in df.iterrows():
        candles.append({
            "time": date.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })

    return {"symbol": symbol, "interval": interval, "candles": candles}


@tool
def get_forex_rate(from_currency: str, to_currency: str) -> dict:
    """
    Get live exchange rate between two currencies.
    Example: from_currency='USD', to_currency='INR'
    """
    symbol = f"{from_currency}{to_currency}=X"
    cache_key = f"forex:{symbol}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    ticker = yf.Ticker(symbol)
    info = ticker.info
    history = ticker.history(period="5d")

    result = {
        "pair": f"{from_currency}/{to_currency}",
        "rate": round(float(info.get("regularMarketPrice", 0)), 4),
        "change_pct": round(float(info.get("regularMarketChangePercent", 0)), 4),
        "week_high": round(float(history["High"].max()), 4) if not history.empty else None,
        "week_low": round(float(history["Low"].min()), 4) if not history.empty else None,
    }

    # set_cached(cache_key, result, ttl=300)  # 5-min cache for forex
    return result