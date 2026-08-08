from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx

from runcrew.domain.activity import ActivityDetail
from runcrew.providers.coros.provider import CorosActivityProvider
from runcrew.providers.fit import FitFileStore


class FitFallbackMcpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def initialize(self):
        return {"result": {"protocolVersion": "2025-06-18"}}

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        if name == "querySportRecords":
            payload = {
                "records": [
                    {
                        "labelId": "fit-fallback-label",
                        "sportType": 100,
                        "startTimestamp": 1785544800,
                        "workoutTime": 1400,
                        "distance": "4.00 km",
                        "avgHr": 140,
                    }
                ]
            }
        elif name in {"getActivityDetail", "queryActivityLapData"}:
            payload = "COROS service temporarily unavailable"
        else:
            assert name == "queryActivityFitFileDownloadUrls"
            assert arguments == {
                "labelId": "fit-fallback-label",
                "sportType": 100,
            }
            payload = {
                "downloadUrl": "https://download.example.test/activity.fit"
            }
        return {
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(payload)}
                ]
            }
        }

    async def aclose(self):
        return None


def test_coros_detail_falls_back_to_fit_then_private_cache(
    tmp_path: Path,
    synthetic_fit_bytes: bytes,
) -> None:
    downloads = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal downloads
        downloads += 1
        return httpx.Response(200, content=synthetic_fit_bytes)

    async def scenario() -> tuple[ActivityDetail, ActivityDetail, list[str]]:
        mcp = FitFallbackMcpClient()
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            provider = CorosActivityProvider(
                mcp_client=mcp,
                fit_file_store=FitFileStore(tmp_path, http_client=client),
            )
            await provider.connect()
            activities = await provider.list_activities(
                date(2026, 8, 1), date(2026, 8, 8)
            )
            external_id = activities[0].activity.source_ref.external_id
            first = await provider.get_activity(external_id)
            second = await provider.get_activity(external_id)
        return first.activity, second.activity, mcp.calls

    first, second, calls = asyncio.run(scenario())

    assert isinstance(first, ActivityDetail)
    assert first.provider_metadata["detail_source"] == "fit"
    assert len(first.laps) == 4
    assert second.source_ref.raw_payload_hash == first.source_ref.raw_payload_hash
    assert downloads == 1
    assert calls == [
        "querySportRecords",
        "getActivityDetail",
        "queryActivityLapData",
        "queryActivityFitFileDownloadUrls",
        "getActivityDetail",
        "queryActivityLapData",
    ]
