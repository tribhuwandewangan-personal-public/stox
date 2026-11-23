"""
Small, dependency-free request-security helpers for the local dashboard (kept separate so they can be unit-tested
without starting the server).
"""

import os
import re
import urllib.parse
from typing import Optional, Tuple

SYMBOL_RE = re.compile(r"[A-Z0-9&-]{1,20}")   # used with fullmatch: "$" would also accept a trailing newline
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def valid_symbol(sym) -> bool:
    """NSE-style symbol: 1-20 chars of A-Z, 0-9, '&' or '-'. Rejects anything that could break out of HTML/JS/paths."""
    return isinstance(sym, str) and SYMBOL_RE.fullmatch(sym) is not None


def host_header_ok(host_header, enforce: bool = True) -> bool:
    """Accept only localhost-style Host headers (defeats DNS-rebinding against a loopback-bound server)."""
    if not enforce:
        return True
    try:
        hostname = urllib.parse.urlsplit("//" + (host_header or "")).hostname
    except ValueError:
        return False
    return hostname in LOOPBACK_NAMES


def post_guard_error(headers) -> Optional[Tuple[int, str]]:
    """
    Cross-site request forgery guard for state-changing endpoints. A web page the user happens to visit can send
    a 'simple' POST to localhost, but it cannot set a JSON content type or a custom header without a CORS
    preflight (which this server never approves). Returns (status, message) or None when the request is allowed.
    """
    ctype = (headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        return 415, "Content-Type must be application/json"
    if headers.get("X-Stox-Request") != "1":
        return 403, "Missing X-Stox-Request header"
    origin = headers.get("Origin")
    if origin:
        origin_split = urllib.parse.urlsplit(origin)
        host_raw = (headers.get("Host") or "").lower()
        host_split = urllib.parse.urlsplit("//" + host_raw)
        same_netloc = origin_split.netloc.lower() == host_raw
        local_dev_proxy = (
            (origin_split.hostname or "").lower() in LOOPBACK_NAMES
            and (host_split.hostname or "").lower() in LOOPBACK_NAMES
            and origin_split.port in (4200, 8765, 8766, 8767)
        )
        if not (same_netloc or local_dev_proxy):
            return 403, "Cross-origin request blocked"
    return None


def resolve_within(base_dir: str, rel_path: str) -> Optional[str]:
    """Real path of rel_path under base_dir if it is an existing file strictly inside it; else None."""
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, rel_path.lstrip("/\\")))
    try:
        common = os.path.commonpath([base, target])
    except ValueError:                       # different drives
        return None
    if os.path.normcase(common) != os.path.normcase(base):
        return None
    return target if os.path.isfile(target) else None
