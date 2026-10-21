"""Read-only HTTP JSON collector. No auth or write methods are implemented."""
import json
from urllib.request import Request, urlopen


def get_json(url: str, timeout: float = 12.0):
    if not url.startswith("https://"):
        raise ValueError("TLS required")
    req = Request(url, headers={"User-Agent": "prediction-arb-research/0.1 (read-only)", "Accept": "application/json"}, method="GET")
    with urlopen(req, timeout=timeout) as response:
        payload = response.read(10_000_001)
        if len(payload) > 10_000_000:
            raise ValueError("Response exceeds 10 MB cap")
        return json.loads(payload)
