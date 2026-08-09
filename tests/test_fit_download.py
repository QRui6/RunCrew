from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from runcrew.providers.fit import FitDownloadError, FitFileStore


def test_fit_download_is_cached_by_external_id(
    tmp_path: Path,
    synthetic_fit_bytes: bytes,
) -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url == "https://example.test/activity.fit"
        return httpx.Response(200, content=synthetic_fit_bytes)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            store = FitFileStore(tmp_path, http_client=client)
            first = await store.download(
                "https://example.test/activity.fit", "private-label-id"
            )
            second = await store.download(
                "https://expired.example.test/old.fit", "private-label-id"
            )

        assert first.from_cache is False
        assert second.from_cache is True
        assert first.sha256 == second.sha256
        assert first.private_path.name != "private-label-id.fit"
        assert second.content == synthetic_fit_bytes

    asyncio.run(scenario())
    assert requests == 1


def test_fit_download_rejects_insecure_url(tmp_path: Path) -> None:
    store = FitFileStore(tmp_path)
    with pytest.raises(FitDownloadError, match="HTTPS"):
        asyncio.run(store.download("http://example.test/file.fit", "id"))


def test_fit_download_rejects_oversized_content(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"12345")

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            store = FitFileStore(tmp_path, max_bytes=4, http_client=client)
            with pytest.raises(FitDownloadError, match="size limit"):
                await store.download("https://example.test/file.fit", "id")

    asyncio.run(scenario())


def test_fit_download_identifies_expired_url(tmp_path: Path) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(410)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            store = FitFileStore(tmp_path, http_client=client)
            with pytest.raises(FitDownloadError, match="expired or unavailable"):
                await store.download("https://example.test/expired.fit", "id")

    asyncio.run(scenario())


def test_fit_download_redacts_transport_timeout_details(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("signed URL must not leak", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            store = FitFileStore(tmp_path, http_client=client)
            with pytest.raises(FitDownloadError) as captured:
                await store.download(
                    "https://example.test/private.fit?token=secret", "id"
                )
        assert "ReadTimeout" in str(captured.value)
        assert "token=secret" not in str(captured.value)

    asyncio.run(scenario())
