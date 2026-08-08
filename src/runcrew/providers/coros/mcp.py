from __future__ import annotations

import json
from typing import Any

import httpx

from runcrew.providers.coros.oauth import COROS_RESOURCE


class McpProtocolError(RuntimeError):
    pass


class CorosMcpClient:
    def __init__(
        self,
        access_token: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.access_token = access_token
        self._provided_http_client = http_client
        self._client = http_client or httpx.AsyncClient(timeout=60)
        self._session_id: str | None = None
        self._next_id = 1
        self._initialized = False

    async def initialize(self) -> dict[str, Any]:
        response = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "runcrew", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})
        self._initialized = True
        return response

    async def list_tools(self) -> list[dict[str, Any]]:
        self._require_initialized()
        response = await self._request("tools/list", {})
        return response.get("result", {}).get("tools", [])

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        self._require_initialized()
        return await self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

    async def aclose(self) -> None:
        if self._provided_http_client is None:
            await self._client.aclose()

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise McpProtocolError("MCP client has not been initialized")

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        response = await self._post(payload)
        if response is None:
            raise McpProtocolError(f"MCP method {method} returned an empty response")
        if "error" in response:
            error = response["error"]
            raise McpProtocolError(
                f"MCP {method} failed: {error.get('code')} {error.get('message')}"
            )
        return response

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params})

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self._session_id:
            headers["MCP-Session-Id"] = self._session_id
        response = await self._client.post(COROS_RESOURCE, headers=headers, json=payload)
        if response.status_code >= 400:
            raise McpProtocolError(
                f"MCP HTTP {response.status_code}: {response.text[:300]}"
            )
        self._session_id = response.headers.get("MCP-Session-Id") or self._session_id
        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            events = []
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data = line.removeprefix("data:").strip()
                    if data:
                        events.append(json.loads(data))
            return events[-1] if events else None
        return response.json()

