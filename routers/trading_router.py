"""
Trading Router
Handles:
  - AngelOne live holdings
  - Favourite stocks (per user, stored in DB)
  - Market data: quotes, candles, technicals
  - Trading agent summary for a symbol
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
import yfinance as yf
import pandas as pd
# import pandas_ta as ta

from database import get_db
from core.auth import get_current_user
from models.users import User
from models.trading import FavouriteStock
# from services.cache_service import get_cached, set_cached
from config import settings

router = APIRouter()

# ══════════════════════════════════════════════════════════
# ── AngelOne Holdings ─────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.get("/holdings")
async def get_holdings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns live holdings from AngelOne + user's favourite flags.
    Falls back gracefully if AngelOne is not configured.
    """
    # Fetch favourites for this user
    result = await db.execute(
        select(FavouriteStock).where(FavouriteStock.user_id == current_user.id)
    )
    fav_symbols = {r.symbol for r in result.scalars().all()}

    # Try AngelOne if configured
    if settings.angelone_api_key and settings.angelone_client_id:
        try:
            from services.angel_one_service import get_live_holdings, get_portfolio_summary
            holdings = await get_live_holdings()
            # Inject favourite flag
            for h in holdings:
                h["is_favourite"] = h["symbol"] in fav_symbols
            summary = await get_portfolio_summary(holdings)
            return {"source": "angelone", "holdings": holdings, "summary": summary}
        except Exception as e:
            # AngelOne failed — fall through to yfinance fallback
            pass

    # ── yfinance fallback (demo mode / no AngelOne) ────────
    return {
        "source": "demo",
        "message": "AngelOne not configured. Showing demo holdings.",
        "holdings": _demo_holdings(fav_symbols),
        "summary": {
            "total_invested": 443420,
            "current_value": 482340,
            "total_pnl": 38920,
            "total_pnl_pct": 8.78,
            "holdings_count": 5,
        },
    }


def _demo_holdings(fav_symbols: set) -> list[dict]:
    demo = [
        {"symbol": "RELIANCE",  "name": "Reliance Industries", "exchange": "NSE", "quantity": 50,  "buy_price": 2640.0, "current_price": 2847.6, "value": 142380, "invested": 132000, "pnl": 10380, "pnl_pct": 7.86, "product_type": "CNC"},
        {"symbol": "HDFCBANK",  "name": "HDFC Bank",           "exchange": "NSE", "quantity": 50,  "buy_price": 1580.0, "current_price": 1623.4, "value": 81170,  "invested": 79000,  "pnl": 2170,  "pnl_pct": 2.75, "product_type": "CNC"},
        {"symbol": "TCS",       "name": "Tata Consultancy",    "exchange": "NSE", "quantity": 50,  "buy_price": 3650.0, "current_price": 3912.8, "value": 195640, "invested": 182500, "pnl": 13140, "pnl_pct": 7.20, "product_type": "CNC"},
        {"symbol": "INFY",      "name": "Infosys",             "exchange": "NSE", "quantity": 100, "buy_price": 1420.0, "current_price": 1487.5, "value": 148750, "invested": 142000, "pnl": 6750,  "pnl_pct": 4.75, "product_type": "CNC"},
        {"symbol": "WIPRO",     "name": "Wipro",               "exchange": "NSE", "quantity": 200, "buy_price": 430.0,  "current_price": 447.6,  "value": 89520,  "invested": 86000,  "pnl": 3520,  "pnl_pct": 4.09, "product_type": "CNC"},
    ]
    for h in demo:
        h["is_favourite"] = h["symbol"] in fav_symbols
        h["isin"] = ""
        h["token"] = ""
    return demo


# ══════════════════════════════════════════════════════════
# ── Favourites ────────────────────────────────────────────
# ══════════════════════════════════════════════════════════

class FavouriteRequest(BaseModel):
    symbol: str

@router.post("/favourites")
async def add_favourite(
    req: FavouriteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(FavouriteStock).where(
            FavouriteStock.user_id == current_user.id,
            FavouriteStock.symbol == req.symbol.upper()
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_exists"}

    fav = FavouriteStock(user_id=current_user.id, symbol=req.symbol.upper())
    db.add(fav)
    await db.commit()
    return {"status": "added", "symbol": req.symbol.upper()}


@router.delete("/favourites/{symbol}")
async def remove_favourite(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(FavouriteStock).where(
            FavouriteStock.user_id == current_user.id,
            FavouriteStock.symbol == symbol.upper()
        )
    )
    await db.commit()
    return {"status": "removed", "symbol": symbol.upper()}


@router.get("/favourites")
async def get_favourites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FavouriteStock).where(FavouriteStock.user_id == current_user.id)
    )
    return {"symbols": [r.symbol for r in result.scalars().all()]}


# ══════════════════════════════════════════════════════════
# ── Market Data ───────────────────────────────────────────
# ══════════════════════════════════════════════════════════

def _ns(symbol: str) -> str:
    """Ensure NSE suffix for yfinance."""
    s = symbol.upper().strip()
    if "." not in s:
        return s + ".NS"
    return s


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """Live quote for a symbol."""
    ns_sym = _ns(symbol)
    cache_key = f"quote:{ns_sym}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    try:
        ticker = yf.Ticker(ns_sym)
        info = ticker.info
        price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev  = info.get("previousClose", price)
        change = price - prev
        change_pct = (change / prev * 100) if prev else 0

        result = {
            "symbol":      ns_sym,
            "name":        info.get("longName", symbol),
            "current_price": round(float(price), 2),
            "prev_close":    round(float(prev), 2),
            "change":        round(float(change), 2),
            "change_pct":    round(float(change_pct), 2),
            "volume":        info.get("regularMarketVolume", 0),
            "market_cap":    info.get("marketCap"),
            "pe_ratio":      info.get("trailingPE"),
            "week_52_high":  info.get("fiftyTwoWeekHigh"),
            "week_52_low":   info.get("fiftyTwoWeekLow"),
            "sector":        info.get("sector"),
        }
        # set_cached(cache_key, result, ttl=60)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Quote fetch failed: {str(e)}")


@router.get("/candles/{symbol}")
async def get_candles(symbol: str, period: str = "3mo", interval: str = "1d"):
    """OHLCV candlestick data."""
    ns_sym = _ns(symbol)
    cache_key = f"candles:{ns_sym}:{period}:{interval}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    try:
        ticker = yf.Ticker(ns_sym)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        candles = [
            {
                "time":   str(idx.date()),
                "open":   round(float(row["Open"]), 2),
                "high":   round(float(row["High"]), 2),
                "low":    round(float(row["Low"]), 2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            }
            for idx, row in df.iterrows()
        ]
        result = {"symbol": ns_sym, "period": period, "interval": interval, "candles": candles}
        # set_cached(cache_key, result, ttl=300)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/technical/{symbol}")
async def get_technical(symbol: str):
    """Full technical analysis: RSI, MACD, EMA, Bollinger, signal."""
    ns_sym = _ns(symbol)
    cache_key = f"technical:{ns_sym}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    try:
        ticker = yf.Ticker(ns_sym)
        df = ticker.history(period="6mo")
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")

        df = _add_indicators(df)


        latest = df.iloc[-1]
        rsi    = float(latest.get("RSI_14", 50))
        macd   = float(latest.get("MACD_12_26_9", 0))
        macd_s = float(latest.get("MACDs_12_26_9", 0))
        close  = float(latest["Close"])

        # Signal logic
        if rsi < 30 and macd > macd_s:
            signal = "STRONG BUY"
        elif rsi < 45 and macd > macd_s:
            signal = "BUY"
        elif rsi > 70 and macd < macd_s:
            signal = "STRONG SELL"
        elif rsi > 55 and macd < macd_s:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        result = {
            "symbol":      ns_sym,
            "last_close":  round(close, 2),
            "rsi_14":      round(rsi, 2),
            "macd":        round(macd, 4),
            "macd_signal": round(macd_s, 4),
            "bb_upper":    round(float(latest.get("BBU_20_2.0", 0)), 2),
            "bb_lower":    round(float(latest.get("BBL_20_2.0", 0)), 2),
            "ema_20":      round(float(latest.get("EMA_20", 0)), 2),
            "ema_50":      round(float(latest.get("EMA_50", 0)), 2),
            "volume":      int(latest["Volume"]),
            "signal":      signal,
        }
        # set_cached(cache_key, result, ttl=300)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

#  calculation logic for technical indicators can be moved to a separate function for clarity and reuse
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


@router.get("/summary/{symbol}")
async def get_ai_summary(symbol: str):
    """
    Quick AI summary for a stock using the trading agent tools
    without a full chat session. Returns a static LLM analysis string.
    """
    ns_sym = _ns(symbol)
    cache_key = f"summary:{ns_sym}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    try:
        # Fetch technical data first
        tech_data = await get_technical(symbol)

        # Build summary from technicals (no LLM call for speed)
        sig = tech_data["signal"]
        rsi = tech_data["rsi_14"]
        macd = tech_data["macd"]
        close = tech_data["last_close"]
        ema20 = tech_data["ema_20"]
        ema50 = tech_data["ema_50"]

        trend = "above" if close > ema20 else "below"
        macro = "uptrend" if ema20 > ema50 else "downtrend"
        rsi_note = "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"
        macd_note = "bullish crossover" if macd > tech_data["macd_signal"] else "bearish crossover"

        summary = (
            f"{ns_sym} is trading at ₹{close:,.2f}. "
            f"Signal: {sig}. "
            f"RSI at {rsi:.1f} ({rsi_note}). "
            f"MACD shows {macd_note}. "
            f"Price is {trend} EMA 20 (₹{ema20:,.0f}), "
            f"indicating a {macro}. "
            f"EMA 50 at ₹{ema50:,.0f}. "
            f"Bollinger: ₹{tech_data['bb_lower']:,.0f} – ₹{tech_data['bb_upper']:,.0f}."
        )

        result = {"symbol": ns_sym, "signal": sig, "summary": summary, "technicals": tech_data}
        # set_cached(cache_key, result, ttl=300)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))



@router.get("/forex")
async def get_forex(from_currency: str = "USD", to_currency: str = "INR"):
    """Live forex rate."""
    symbol = f"{from_currency}{to_currency}=X"
    cache_key = f"forex:{symbol}"
    # cached = get_cached(cache_key)
    # if cached:
    #     return cached

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period="5d")
        result = {
            "pair":       f"{from_currency}/{to_currency}",
            "rate":       round(float(info.get("regularMarketPrice", 0)), 4),
            "change_pct": round(float(info.get("regularMarketChangePercent", 0)), 4),
            "week_high":  round(float(hist["High"].max()), 4) if not hist.empty else 0,
            "week_low":   round(float(hist["Low"].min()),  4) if not hist.empty else 0,
        }
        # set_cached(cache_key, result, ttl=300)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))