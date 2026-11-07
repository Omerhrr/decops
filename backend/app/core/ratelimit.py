"""Small in-process sliding-window rate limiter for abuse-prone endpoints.

Keyed by client IP (uvicorn --proxy-headers resolves the real address behind
Caddy/Render). State lives in memory: correct for the supported single-worker
deployment; use an edge limiter (Cloudflare/Caddy plugin) for multi-instance.
"""

import json
import time
from collections import defaultdict, deque

# (method, path) -> (max requests, window seconds)
RULES: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/api/v1/auth/login"): (15, 60),
    ("POST", "/api/v1/auth/forgot-password"): (5, 900),
    ("POST", "/api/v1/auth/reset-password"): (10, 900),
    ("POST", "/api/v1/auth/change-password"): (10, 900),
    ("POST", "/api/v1/auth/mfa/disable"): (10, 900),
    ("POST", "/api/v1/auth/mfa/enable"): (10, 900),
}


class RateLimitMiddleware:
    def __init__(self, app, *, enabled: bool = True) -> None:  # noqa: ANN001
        self.app = app
        self.enabled = enabled
        self.hits: dict[tuple[str, str, str], deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if not self.enabled or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rule = RULES.get((scope["method"], scope["path"]))
        if rule is None:
            await self.app(scope, receive, send)
            return
        limit, window = rule
        ip = (scope.get("client") or ("unknown", 0))[0]
        key = (ip, scope["method"], scope["path"])
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window - (now - q[0])))
            body = json.dumps({"error": {"code": "rate_limited",
                                         "message": "Too many attempts. Please wait and try again."}}).encode()
            await send({"type": "http.response.start", "status": 429, "headers": [
                (b"content-type", b"application/json"), (b"retry-after", str(retry).encode()),
                (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store"),
            ]})
            await send({"type": "http.response.body", "body": body})
            return
        q.append(now)
        if now - self._last_sweep > 300:  # drop idle keys
            self._last_sweep = now
            for k in [k for k, v in self.hits.items() if not v or now - v[-1] > 900]:
                self.hits.pop(k, None)
        await self.app(scope, receive, send)
