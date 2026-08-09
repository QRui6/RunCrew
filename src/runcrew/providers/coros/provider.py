from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from runcrew.domain.activity import ActivitySummary, SourceProvider
from runcrew.providers.base import ProviderActivity
from runcrew.providers.coros.mcp import CorosMcpClient
from runcrew.providers.coros.oauth import CorosOAuthClient
from runcrew.providers.coros.parser import (
    CorosPayloadError,
    extract_detail_object,
    extract_fit_download_url,
    extract_records,
    parse_activity_detail,
    parse_activity_summary,
    unwrap_tool_result,
)
from runcrew.providers.fit import FitFileStore, parse_fit_activity


class CorosActivityProvider:
    def __init__(
        self,
        *,
        callback_port: int = 8765,
        open_browser: bool = True,
        authorization_url_handler: Callable[[str], None] | None = None,
        oauth_client: CorosOAuthClient | None = None,
        mcp_client: CorosMcpClient | None = None,
        debug_payload_path: Path | None = None,
        fit_file_store: FitFileStore | None = None,
    ) -> None:
        self.oauth_client = oauth_client or CorosOAuthClient(
            callback_port=callback_port,
            open_browser=open_browser,
            authorization_url_handler=authorization_url_handler,
        )
        self.mcp_client = mcp_client
        self.debug_payload_path = debug_payload_path
        self.fit_file_store = fit_file_store or FitFileStore()
        self._summaries: dict[str, ActivitySummary] = {}
        self._sport_codes: dict[str, int] = {}

    @property
    def name(self) -> str:
        return SourceProvider.COROS.value

    async def connect(self) -> None:
        if self.mcp_client is None:
            token = await self.oauth_client.authorize()
            self.mcp_client = CorosMcpClient(token.access_token)
        await self.mcp_client.initialize()

    async def list_activities(
        self, start_date: date, end_date: date
    ) -> list[ProviderActivity]:
        client = self._require_client()
        response = await client.call_tool(
            "querySportRecords",
            {
                "startDate": start_date.strftime("%Y%m%d"),
                "endDate": end_date.strftime("%Y%m%d"),
                "sportTypeCodes": [100, 101, 102, 103],
                "minDistanceKm": None,
                "maxDistanceKm": None,
                "minDurationMinutes": None,
                "maxDurationMinutes": None,
                "maxAveragePace": None,
                "locationKeyword": None,
                "limit": 100,
            },
        )
        payload = unwrap_tool_result(response)
        try:
            records = extract_records(payload)
        except Exception:
            self._capture_debug_payload("querySportRecords", payload)
            raise
        envelopes = []
        for record in records:
            summary = parse_activity_summary(record)
            external_id = summary.source_ref.external_id
            self._summaries[external_id] = summary
            sport_code = _sport_code(record)
            if sport_code is not None:
                self._sport_codes[external_id] = sport_code
            envelopes.append(ProviderActivity(activity=summary, raw_payload=record))
        envelopes.sort(key=lambda item: item.activity.started_at, reverse=True)
        return envelopes

    async def get_activity(self, external_id: str) -> ProviderActivity:
        client = self._require_client()
        fallback = self._summaries.get(external_id)
        sport_code = self._sport_codes.get(external_id)
        if fallback is None or sport_code is None:
            raise LookupError(
                "Call list_activities before get_activity so COROS sportType is available"
            )
        tool_arguments = {"labelId": external_id, "sportType": sport_code}
        try:
            response = await client.call_tool("getActivityDetail", tool_arguments)
            payload = unwrap_tool_result(response)
            if isinstance(payload, str):
                raise CorosPayloadError("COROS detail tool returned unstructured text")
            raw = extract_detail_object(payload)
            detail = parse_activity_detail(raw, fallback_summary=fallback)
            return ProviderActivity(activity=detail, raw_payload=raw)
        except Exception:
            if "payload" in locals():
                self._capture_debug_payload("getActivityDetail", payload)
        try:
            lap_response = await client.call_tool(
                "queryActivityLapData", tool_arguments
            )
            lap_payload = unwrap_tool_result(lap_response)
            if isinstance(lap_payload, str):
                raise CorosPayloadError("COROS lap tool returned unstructured text")
            raw = extract_detail_object(lap_payload)
            detail = parse_activity_detail(raw, fallback_summary=fallback)
            return ProviderActivity(activity=detail, raw_payload=raw)
        except Exception:
            if "lap_payload" in locals():
                self._capture_debug_payload("queryActivityLapData", lap_payload)

        artifact = self.fit_file_store.load_cached(external_id)
        if artifact is None:
            fit_response = await client.call_tool(
                "queryActivityFitFileDownloadUrls", tool_arguments
            )
            fit_payload = unwrap_tool_result(fit_response)
            fit_url = extract_fit_download_url(fit_payload)
            artifact = await self.fit_file_store.download(fit_url, external_id)
        try:
            parsed = parse_fit_activity(
                artifact.content,
                fallback_summary=fallback,
            )
        except Exception:
            self.fit_file_store.discard(external_id)
            raise
        return ProviderActivity(
            activity=parsed.activity,
            raw_payload={
                "detail_source": "fit",
                "fit_sha256": parsed.sha256,
                "fit_size_bytes": len(artifact.content),
                "fit_message_counts": parsed.message_counts,
                "from_private_cache": artifact.from_cache,
            },
        )

    async def aclose(self) -> None:
        if self.mcp_client is not None:
            await self.mcp_client.aclose()

    def _require_client(self) -> CorosMcpClient:
        if self.mcp_client is None:
            raise RuntimeError("Call connect() before using COROS provider")
        return self.mcp_client

    def _capture_debug_payload(self, operation: str, payload: Any) -> None:
        if self.debug_payload_path is None:
            return
        self.debug_payload_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_payload_path.write_text(
            json.dumps(
                {"operation": operation, "payload": payload},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )


def _sport_code(record: Mapping[str, Any]) -> int | None:
    for key in ("sportType", "sport_type", "sportTypeCode"):
        value = record.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None
