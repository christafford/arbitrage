"""Kalshi public REST read-only capture. Market discovery only, NOT live matched books."""
from urllib.parse import urlencode
from .provider import get_json

BASE = "https://external-api.kalshi.com/trade-api/v2"

def get_markets(limit: int = 20):
    if not (1 <= limit <= 100):
        raise ValueError("limit must be 1..100")
    url = BASE + "/markets?" + urlencode({"status": "open", "limit": limit})
    data = get_json(url)
    if not isinstance(data, dict) or not isinstance(data.get("markets"), list):
        raise ValueError("Unexpected Kalshi markets response schema")
    return url, data

def get_orderbook(ticker: str):
    from urllib.parse import quote
    if not ticker or "/" in ticker or "?" in ticker:
        raise ValueError("invalid ticker")
    url = BASE + "/markets/" + quote(ticker, safe="") + "/orderbook"
    data = get_json(url)
    if not isinstance(data, dict) or not ("orderbook_fp" in data or "orderbook" in data):
        raise ValueError("Unexpected Kalshi orderbook schema")
    return url, data
