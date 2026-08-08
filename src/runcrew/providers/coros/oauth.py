from __future__ import annotations

import asyncio
import base64
import hashlib
import http.server
import queue
import secrets
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx


COROS_AUTHORITY = "https://mcpcn.coros.com"
COROS_RESOURCE = f"{COROS_AUTHORITY}/mcp"
COROS_SCOPE = "openid mcp.tools offline_access"


class CorosOAuthError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CorosToken:
    access_token: str
    token_type: str
    expires_in: int | None


def _base64_url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class CorosOAuthClient:
    def __init__(
        self,
        *,
        callback_port: int = 8765,
        timeout_seconds: int = 600,
        open_browser: bool = True,
        authorization_url_handler: Callable[[str], None] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.callback_port = callback_port
        self.timeout_seconds = timeout_seconds
        self.open_browser = open_browser
        self.authorization_url_handler = authorization_url_handler
        self._provided_http_client = http_client

    async def authorize(self) -> CorosToken:
        redirect_uri = f"http://127.0.0.1:{self.callback_port}/callback"
        owns_client = self._provided_http_client is None
        client = self._provided_http_client or httpx.AsyncClient(timeout=30)
        try:
            registration_response = await client.post(
                f"{COROS_AUTHORITY}/connect/register",
                json={
                    "client_name": "RunCrew Local Client",
                    "redirect_uris": [redirect_uri],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "none",
                    "scope": COROS_SCOPE,
                },
            )
            registration_response.raise_for_status()
            client_id = registration_response.json()["client_id"]

            state = _base64_url(secrets.token_bytes(24))
            verifier = _base64_url(secrets.token_bytes(48))
            challenge = _base64_url(hashlib.sha256(verifier.encode()).digest())

            callback_queue: queue.Queue[str | Exception] = queue.Queue(maxsize=1)
            server = self._build_callback_server(
                state=state,
                callback_queue=callback_queue,
            )
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()

            authorization_url = f"{COROS_AUTHORITY}/oauth2/authorize?{urlencode({
                'response_type': 'code',
                'client_id': client_id,
                'redirect_uri': redirect_uri,
                'scope': COROS_SCOPE,
                'state': state,
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
                'resource': COROS_RESOURCE,
            })}"
            if self.authorization_url_handler:
                self.authorization_url_handler(authorization_url)
            if self.open_browser and not webbrowser.open(authorization_url):
                raise CorosOAuthError(
                    "Could not open a browser. Open the printed COROS authorization URL manually."
                )

            try:
                callback_result = await asyncio.to_thread(
                    callback_queue.get,
                    True,
                    self.timeout_seconds,
                )
            except queue.Empty as error:
                raise CorosOAuthError("Timed out waiting for COROS authorization") from error
            finally:
                server.shutdown()
                server.server_close()

            if isinstance(callback_result, Exception):
                raise CorosOAuthError(str(callback_result))

            token_response = await client.post(
                f"{COROS_AUTHORITY}/oauth2/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "code": callback_result,
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier,
                    "resource": COROS_RESOURCE,
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            return CorosToken(
                access_token=token_payload["access_token"],
                token_type=token_payload.get("token_type", "Bearer"),
                expires_in=token_payload.get("expires_in"),
            )
        except (httpx.HTTPError, KeyError) as error:
            raise CorosOAuthError(f"COROS OAuth failed: {error}") from error
        finally:
            if owns_client:
                await client.aclose()

    def _build_callback_server(
        self,
        *,
        state: str,
        callback_queue: queue.Queue[str | Exception],
    ) -> http.server.ThreadingHTTPServer:
        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler_self) -> None:  # noqa: N802
                parsed = urlparse(handler_self.path)
                query = parse_qs(parsed.query)
                try:
                    if parsed.path != "/callback":
                        raise CorosOAuthError("Unexpected OAuth callback path")
                    if query.get("state", [None])[0] != state:
                        raise CorosOAuthError("OAuth state mismatch")
                    if "error" in query:
                        raise CorosOAuthError(
                            f"COROS authorization denied: {query['error'][0]}"
                        )
                    code = query.get("code", [None])[0]
                    if not code:
                        raise CorosOAuthError("OAuth callback did not contain a code")
                    callback_queue.put_nowait(code)
                    handler_self._respond(
                        200,
                        "<h2>COROS 授权成功</h2><p>可以关闭此页面，RunCrew 正在同步数据。</p>",
                    )
                except Exception as error:  # callback must always return a response
                    if callback_queue.empty():
                        callback_queue.put_nowait(error)
                    handler_self._respond(400, "COROS 授权回调失败，可以关闭此页面。")

            def _respond(handler_self, status: int, body: str) -> None:
                encoded = body.encode("utf-8")
                handler_self.send_response(status)
                handler_self.send_header("Content-Type", "text/html; charset=utf-8")
                handler_self.send_header("Content-Length", str(len(encoded)))
                handler_self.end_headers()
                handler_self.wfile.write(encoded)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        try:
            return http.server.ThreadingHTTPServer(
                ("127.0.0.1", self.callback_port), CallbackHandler
            )
        except OSError as error:
            raise CorosOAuthError(
                f"Cannot listen on 127.0.0.1:{self.callback_port}: {error}"
            ) from error

