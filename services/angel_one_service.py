"""
AngelOne SmartAPI Integration Service
Handles authentication, live holdings, quotes, and order data.

Docs: https://smartapi.angelbroking.com/
SDK:  pip install smartapi-python pyotp
"""

import pyotp
import asyncio
from typing import Optional
from functools import lru_cache
from datetime import datetime, timezone

from SmartApi import SmartConnect
from config import settings
from services.cache_service import get_cached, set_cached


# ── AngelOne session (singleton per process) ─────────────────────────────────
_session: Optional[SmartConnect] = None
_session_token: Optional[str] = None


def _get_totp() -> str:
    """Generate TOTP from AngelOne TOTP secret."""
    return pyotp.TOTP(settings.angelone_totp_secret).now()


def get_angel_client() -> SmartConnect:
    """
    Returns authenticated SmartConnect instance.
    Re-authenticates if session is expired.
    """
    global _session, _session_token

    if _session and _session_token:
        return _session

    obj = SmartConnect(api_key=settings.angelone_api_key)
    data = obj.generateSession(
        clientCode=settings.angelone_client_id,
        password=settings.angelone_mpin,
        totp=_get_totp(),
    )

    if data.get("status") is False:
        raise RuntimeError(f"AngelOne auth failed: {data.get('message')}")

    _session_token = data["data"]["jwtToken"]
    _session = obj
    return _session


def reset_session():
    """Force re-authentication on next call."""
    global _session, _session_token
    _session = None
    _session_token = None


# ── Holdings ──────────────────────────────────────────────────────────────────
async def get_live_holdings() -> list[dict]:
    """
    Fetch all holdings from AngelOne demat account.
    Returns list of holdings with live LTP, P&L.
    Cached for 60 seconds to avoid hammering API.
    """
    cache_key = "angelone:holdings"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = get_angel_client()
        resp = client.holding()

        if resp.get("status") is False:
            raise RuntimeError(resp.get("message", "Holdings fetch failed"))

        raw_holdings = resp.get("data", [])
        holdings = []

        for h in raw_holdings:
            qty = int(h.get("quantity", 0))
            avg_price = float(h.get("averageprice", 0))
            ltp = float(h.get("ltp", 0))
            pnl = (ltp - avg_price) * qty
            pnl_pct = ((ltp - avg_price) / avg_price * 100) if avg_price > 0 else 0

            holdings.append({
                "symbol":        h.get("tradingsymbol", ""),
                "isin":          h.get("isin", ""),
                "exchange":      h.get("exchange", "NSE"),
                "quantity":      qty,
                "buy_price":     round(avg_price, 2),
                "current_price": round(ltp, 2),
                "value":         round(ltp * qty, 2),
                "invested":      round(avg_price * qty, 2),
                "pnl":           round(pnl, 2),
                "pnl_pct":       round(pnl_pct, 2),
                "name":          h.get("symbolname", h.get("tradingsymbol", "")),
                "product_type":  h.get("product", "CNC"),
                "is_favourite":  False,   # enriched from user DB separately
                # AngelOne-specific
                "angelone_symbol": h.get("tradingsymbol", ""),
                "token":           h.get("symboltoken", ""),
            })

        set_cached(cache_key, holdings, ttl=60)
        return holdings

    except Exception as e:
        reset_session()
        raise RuntimeError(f"AngelOne holdings error: {str(e)}")


# ── Portfolio Summary ─────────────────────────────────────────────────────────
async def get_portfolio_summary(holdings: list[dict]) -> dict:
    """Compute aggregate portfolio metrics from holdings list."""
    total_invested = sum(h["invested"] for h in holdings)
    current_value  = sum(h["value"]    for h in holdings)
    total_pnl      = current_value - total_invested
    total_pnl_pct  = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    return {
        "total_invested": round(total_invested, 2),
        "current_value":  round(current_value, 2),
        "total_pnl":      round(total_pnl, 2),
        "total_pnl_pct":  round(total_pnl_pct, 2),
        "holdings_count": len(holdings),
    }


# ── Live Quote (AngelOne LTP) ─────────────────────────────────────────────────
async def get_live_quote(symbol_token: str, exchange: str = "NSE") -> dict:
    """
    Fetch live LTP for a single token from AngelOne.
    symbol_token: the 'token' field from holdings (e.g. '3045' for SBIN)
    """
    cache_key = f"angelone:ltp:{exchange}:{symbol_token}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = get_angel_client()
        resp = client.ltpData(exchange, symbol_token, symbol_token)
        ltp = resp.get("data", {}).get("ltp", 0)
        result = {"ltp": float(ltp), "token": symbol_token, "exchange": exchange}
        set_cached(cache_key, result, ttl=15)  # 15s for live prices
        return result
    except Exception as e:
        reset_session()
        raise RuntimeError(f"AngelOne LTP error: {str(e)}")


# ── Positions (intraday) ──────────────────────────────────────────────────────
async def get_positions() -> list[dict]:
    """Fetch today's open intraday positions."""
    cache_key = "angelone:positions"
    cached = get_cached(cache_key)
    if cached:
        return cached

    try:
        client = get_angel_client()
        resp = client.position()
        positions = resp.get("data", []) or []
        result = []
        for p in positions:
            qty = int(p.get("netqty", 0))
            if qty == 0:
                continue
            result.append({
                "symbol":    p.get("tradingsymbol", ""),
                "exchange":  p.get("exchange", "NSE"),
                "quantity":  qty,
                "buy_price": float(p.get("avgnetprice", 0)),
                "ltp":       float(p.get("ltp", 0)),
                "pnl":       float(p.get("unrealised", 0)),
                "product":   p.get("producttype", "MIS"),
            })
        set_cached(cache_key, result, ttl=30)
        return result
    except Exception as e:
        reset_session()
        raise RuntimeError(f"AngelOne positions error: {str(e)}")