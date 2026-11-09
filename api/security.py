"""
Security middleware and guards for the Starlette app.

Reuses protections from the legacy http.server handler:
  - loopback-only binding (prevents off-network access)
  - Host header validation (DNS-rebinding defense)
  - POST guard (CSRF, content-type, custom header)
  - WebSocket Origin check (CSWSH defense)
  - Symbol and path validation
"""

import os
import sys
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from typing import Callable, Awaitable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import DASHBOARD_HOST
from tools.web_security import LOOPBACK_NAMES, host_header_ok, post_guard_error

ENFORCE_HOST_CHECK = DASHBOARD_HOST in LOOPBACK_NAMES  # blocks DNS-rebinding when bound to loopback only


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Apply Host header check and POST guard to all HTTP requests.
    Reuses the same security logic as the legacy handler.
    """

    async def dispatch(
        self, request, call_next: Callable[[any], Awaitable[Response]]
    ) -> Response:
        # Host header check
        host = request.headers.get("host", "")
        if not host_header_ok(host, ENFORCE_HOST_CHECK):
            return JSONResponse({"error": "Forbidden host"}, status_code=403)

        # POST guard (CSRF tokens, content-type, etc.)
        if request.method == "POST":
            guard_error = post_guard_error(request.headers)
            if guard_error:
                status_code, message = guard_error
                return JSONResponse({"error": message}, status_code=status_code)

        response = await call_next(request)
        return response


class WebSocketSecurityMiddleware:
    """
    Wraps ASGI app to validate WebSocket connection security:
      - Host header check
      - Origin header check (blocks cross-site WebSocket hijacking)
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            headers = dict(scope.get("headers", []))

            # Host check
            host = headers.get(b"host", b"").decode("utf-8", errors="ignore")
            if host and not host_header_ok(host, ENFORCE_HOST_CHECK):
                await send({
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Forbidden host",
                })
                return

            # Origin check (same-origin only, blocks CSWSH)
            origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")
            if origin and host:
                # origin is "scheme://host", we need just "host" from it
                try:
                    origin_host = origin.split("://")[1] if "://" in origin else origin
                    if origin_host != host:
                        await send({
                            "type": "websocket.close",
                            "code": 1008,
                            "reason": "Cross-origin",
                        })
                        return
                except Exception:
                    pass

        await self.app(scope, receive, send)
