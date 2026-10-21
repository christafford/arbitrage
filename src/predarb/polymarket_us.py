"""US-only raw collector; does NOT reference polymarket.com international CLOB/Gamma."""
import os
from urllib.parse import quote
from .provider import get_json

# Verify production data hostname against https://docs.polymarket.us/ before running.
DEFAULT_BASE = "https://api.polymarket.us"

def base_url():
    base = os.environ.get("POLYMARKET_US_DATA_BASE", DEFAULT_BASE).rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("Polymarket US API base must use HTTPS")
    return base

def get_reference_data():
    url = base_url() + "/v1/refdata/instruments"
    return url, get_json(url)

def get_book(symbol: str):
    if not symbol or "/" in symbol or "?" in symbol:
        raise ValueError("invalid symbol")
    url = base_url() + "/v1/orderbook/" + quote(symbol, safe="")
    return url, get_json(url)
