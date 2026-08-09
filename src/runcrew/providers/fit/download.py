from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx


class FitDownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FitFileArtifact:
    content: bytes
    sha256: str
    private_path: Path
    from_cache: bool


class FitFileStore:
    def __init__(
        self,
        private_dir: Path = Path("data/private/fit"),
        *,
        max_bytes: int = 50 * 1024 * 1024,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.private_dir = private_dir
        self.max_bytes = max_bytes
        self._provided_http_client = http_client

    def path_for(self, external_id: str) -> Path:
        safe_id = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:24]
        return self.private_dir / f"{safe_id}.fit"

    def load_cached(self, external_id: str) -> FitFileArtifact | None:
        path = self.path_for(external_id)
        if not path.is_file():
            return None
        content = path.read_bytes()
        self._validate_size(content)
        return FitFileArtifact(
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            private_path=path,
            from_cache=True,
        )

    def discard(self, external_id: str) -> None:
        """Remove an unusable private cache entry without exposing its identifier."""
        self.path_for(external_id).unlink(missing_ok=True)

    async def download(self, url: str, external_id: str) -> FitFileArtifact:
        cached = self.load_cached(external_id)
        if cached is not None:
            return cached

        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise FitDownloadError("FIT download URL must use HTTPS")

        owns_client = self._provided_http_client is None
        client = self._provided_http_client or httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
        )
        try:
            async with client.stream("GET", url) as response:
                if response.status_code in {401, 403, 404, 410}:
                    raise FitDownloadError(
                        "FIT download URL is expired or unavailable"
                    )
                if response.status_code >= 400:
                    raise FitDownloadError(
                        f"FIT download failed with HTTP {response.status_code}"
                    )
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError as error:
                        raise FitDownloadError(
                            "FIT download returned an invalid content length"
                        ) from error
                    if declared_size > self.max_bytes:
                        raise FitDownloadError(
                            "FIT file exceeds configured size limit"
                        )
                chunks: list[bytes] = []
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > self.max_bytes:
                        raise FitDownloadError("FIT file exceeds configured size limit")
                    chunks.append(chunk)
        except httpx.HTTPError as error:
            raise FitDownloadError(
                f"FIT download transport error: {type(error).__name__}"
            ) from error
        finally:
            if owns_client:
                await client.aclose()

        content = b"".join(chunks)
        self._validate_size(content)
        path = self.path_for(external_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(".fit.part")
        temporary_path.write_bytes(content)
        temporary_path.replace(path)
        return FitFileArtifact(
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            private_path=path,
            from_cache=False,
        )

    def _validate_size(self, content: bytes) -> None:
        if not content:
            raise FitDownloadError("FIT file is empty")
        if len(content) > self.max_bytes:
            raise FitDownloadError("FIT file exceeds configured size limit")
