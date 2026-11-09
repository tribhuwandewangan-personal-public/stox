"""
One-off helper: log in to Zerodha Kite Connect and find out whether YOUR plan returns market quotes.

    set KITE_API_KEY=...        (PowerShell: $env:KITE_API_KEY="...")
    set KITE_API_SECRET=...
    python tools/kite_probe.py

What it does
  1. Prints the Kite login URL. You log in yourself in the browser (this tool never automates your password/TOTP).
  2. You paste the `request_token` (or the whole redirected URL) back here.
  3. It exchanges it for an access token, saves it to storage/kite_token.json, and tries a quote call.
  4. It prints "Zerodha quotes: AVAILABLE" or "NOT AVAILABLE (reason)". If not available, nothing is lost:
     the dashboard keeps using Yahoo.

SECURITY: a Kite access token can place orders on your account, not just read prices. It is stored only in the
gitignored storage/kite_token.json and Zerodha expires it daily. The API secret is read from the environment and
is never written to disk. Do not share or commit the token file. Requires `pip install kiteconnect`.
"""

import json
import os
import sys
from datetime import datetime
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.quote_tools import KITE_TOKEN_PATH   # noqa: E402

PROBE_SYMBOLS = ["NSE:RELIANCE", "NSE:TCS"]


def extract_request_token(text: str) -> str:
    """Accepts the bare token or the full redirect URL containing ?request_token=..."""
    text = (text or "").strip()
    if "request_token=" in text:
        qs = parse_qs(urlparse(text).query)
        return (qs.get("request_token") or [""])[0]
    return text


def main() -> int:
    api_key = os.getenv("KITE_API_KEY", "").strip()
    api_secret = os.getenv("KITE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        print("Set KITE_API_KEY and KITE_API_SECRET in the environment first.")
        return 2
    try:
        from kiteconnect import KiteConnect
    except ImportError:
        print("kiteconnect is not installed. Run: pip install kiteconnect")
        return 2

    kite = KiteConnect(api_key=api_key)
    print("\n1) Open this URL, log in to Zerodha, and approve:\n\n   " + kite.login_url() + "\n")
    token = extract_request_token(input("2) Paste the request_token (or the full redirected URL): "))
    if not token:
        print("No request_token given.")
        return 2

    try:
        session = kite.generate_session(token, api_secret=api_secret)
    except Exception as e:
        print(f"Login failed ({type(e).__name__}): {e}")
        return 1
    access_token = session["access_token"]
    kite.set_access_token(access_token)

    os.makedirs(os.path.dirname(KITE_TOKEN_PATH), exist_ok=True)
    with open(KITE_TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"access_token": access_token, "api_key": api_key, "created": datetime.now().isoformat()}, f)
    print(f"Saved access token to {KITE_TOKEN_PATH} (expires daily; keep this file private).")

    try:
        data = kite.quote(PROBE_SYMBOLS)
    except Exception as e:
        print(f"\nZerodha quotes: NOT AVAILABLE -> {type(e).__name__}: {e}")
        print("The dashboard will keep using Yahoo. (Quotes/streaming are part of the paid Connect plan.)")
        return 1

    print("\nZerodha quotes: AVAILABLE")
    for key, q in data.items():
        print(f"  {key}: last_price={q.get('last_price')} volume={q.get('volume')} time={q.get('last_trade_time')}")
    print("\nSet QUOTE_SOURCES=kite,yahoo (the default) and restart the dashboard. Re-run this tool daily.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
