"""Response headers and request-body limits for the whole API.

The frontend loads page images through fetch and blob URLs, so nothing here
restricts script loading - that is the frontend's own CSP job. These headers
stop the API from being a hosting surface: no sniffing, no framing, no referrer
leaks, and no browser-only features reachable from a response.
"""

from starlette.datastructures import Headers, MutableHeaders

from app.core.config import settings

HSTS = "max-age=31536000; includeSubDomains"

# Every JSON/form endpoint deals in small fields; a bigger body is an attack.
MAX_BODY_BYTES = 1_000_000

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


class SecurityMiddleware:
    """Adds the response headers and refuses oversized request bodies.

    PDF uploads stream as multipart/form-data and enforce settings.max_upload_mb
    in the upload route, so those requests are passed through unread.
    """

    def __init__(self, app, max_body_bytes: int = MAX_BODY_BYTES,
                 drain_limit_bytes: int = 32_000_000):
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.drain_limit_bytes = drain_limit_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if settings.hsts_enabled:
                    headers.setdefault("Strict-Transport-Security", HSTS)
            await send(message)

        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "")
        declared = headers.get("content-length")

        if content_type.startswith("multipart/form-data"):
            await self.app(scope, receive, send_with_headers)
            return
        too_big = bool(declared and declared.isdigit() and int(declared) > self.max_body_bytes)
        if not declared and not too_big and scope["method"] in {"GET", "HEAD", "DELETE"}:
            await self.app(scope, receive, send_with_headers)
            return

        body = bytearray()
        while not too_big:
            message = await receive()
            if message["type"] == "http.disconnect":
                await self.app(scope, receive, send_with_headers)
                return
            body += message.get("body", b"")
            if len(body) > self.max_body_bytes:
                too_big = True
            elif not message.get("more_body", False):
                await self._serve(scope, bytes(body), receive, send_with_headers)
                return

        # Read the rest before answering. Replying first makes the server close
        # mid-upload, and the client loses the 413 under a connection reset.
        await self._drain(receive)
        await self._reject(send_with_headers)

    async def _serve(self, scope, body, receive, send):
        replayed = False

        async def replay_receive():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _drain(self, receive) -> None:
        """Discard the tail of a rejected upload without holding it in memory."""
        drained = 0
        while drained < self.drain_limit_bytes:
            message = await receive()
            if message["type"] != "http.request":
                return
            drained += len(message.get("body", b""))
            if not message.get("more_body", False):
                return

    @staticmethod
    async def _reject(send) -> None:
        payload = b'{"detail":"Request body too large"}'
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": payload})
