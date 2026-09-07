from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import random
import time
from typing import Any, Callable, Mapping

import httpx


_REDACT_KEYS = {"api_key", "apikey", "key", "token", "access_token", "authorization"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_mapping(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key.lower() in _REDACT_KEYS or "token" in key.lower() or "secret" in key.lower():
            out[key] = "***REDACTED***"
        else:
            out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 4
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 8.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)

    def delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_cap_seconds)
            except ValueError:
                pass
        raw = min(self.backoff_base_seconds * (2 ** max(0, attempt - 1)), self.backoff_cap_seconds)
        return raw * (0.85 + random.random() * 0.30)


@dataclass(frozen=True, slots=True)
class RequestLogEntry:
    request_id: str
    source: str
    method: str
    endpoint: str
    params: dict[str, Any]
    status_code: int
    attempt: int
    elapsed_seconds: float
    retrieved_at_utc: str
    response_sha256: str
    cache_hit: bool = False
    rate_limit: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HTTPRequestError(RuntimeError):
    pass


class DiskResponseCache:
    """Small opt-in HTTP response cache for reproducible development runs.

    It stores response bodies keyed by method + URL + non-secret parameters. It is disabled
    unless explicitly passed to RetryingClient, so users control local persistence.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(method: str, url: str, params: Mapping[str, Any] | None) -> str:
        safe = _redact_mapping(params)
        payload = json.dumps([method.upper(), url, sorted(safe.items())], ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, method: str, url: str, params: Mapping[str, Any] | None) -> bytes | None:
        path = self.directory / f"{self.key(method, url, params)}.gz"
        if not path.exists():
            return None
        return gzip.decompress(path.read_bytes())

    def put(self, method: str, url: str, params: Mapping[str, Any] | None, content: bytes) -> None:
        path = self.directory / f"{self.key(method, url, params)}.gz"
        path.write_bytes(gzip.compress(content))


class RawAuditStore:
    """Optional response-body archive. Each body is content-addressed by SHA-256.

    Secrets are never written into the metadata sidecar. The archive is intentionally opt-in
    because upstream licences/terms and local privacy policies may affect what users may retain.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, *, source: str, content: bytes, content_type: str | None, metadata: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(content).hexdigest()
        body_path = self.directory / f"{digest}.gz"
        meta_path = self.directory / f"{digest}.json"
        if not body_path.exists():
            body_path.write_bytes(gzip.compress(content))
        if not meta_path.exists():
            safe_meta = dict(metadata)
            safe_meta["source"] = source
            safe_meta["sha256"] = digest
            safe_meta["content_type"] = content_type
            meta_path.write_text(json.dumps(safe_meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return digest


class RetryingClient:
    """Thin auditable HTTP client with exponential backoff and optional caching/auditing."""

    def __init__(
        self,
        *,
        source: str,
        client: httpx.Client | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout: float = 30.0,
        cache: DiskResponseCache | None = None,
        audit_store: RawAuditStore | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.source = source
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self.retry_policy = retry_policy or RetryPolicy()
        self.cache = cache
        self.audit_store = audit_store
        self.sleeper = sleeper
        self.logs: list[RequestLogEntry] = []

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "RetryingClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _rate_headers(response: httpx.Response) -> dict[str, str]:
        wanted = {
            "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
            "x-ratelimit-credits-used", "retry-after", "x-api-pool",
            "x-rec-amtperyear-remaining", "x-rec-amtpermonth-remaining",
            "x-req-reqpersec-remaining", "x-req-reqperday-remaining",
        }
        return {k: v for k, v in response.headers.items() if k.lower() in wanted}

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cacheable: bool = False,
    ) -> httpx.Response:
        safe_params = _redact_mapping(params)
        cached = self.cache.get("GET", url, params) if (cacheable and self.cache) else None
        if cached is not None:
            request = httpx.Request("GET", url, params=params, headers=headers)
            response = httpx.Response(200, content=cached, request=request, headers={"X-MetaEvidence-Cache": "HIT"})
            digest = hashlib.sha256(cached).hexdigest()
            self.logs.append(RequestLogEntry(
                request_id=digest[:16], source=self.source, method="GET", endpoint=url,
                params=safe_params, status_code=200, attempt=0, elapsed_seconds=0.0,
                retrieved_at_utc=_utcnow(), response_sha256=digest, cache_hit=True,
            ))
            return response

        last_exc: Exception | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            started = time.perf_counter()
            try:
                response = self.client.get(url, params=params, headers=headers)
                elapsed = time.perf_counter() - started
                content = response.content
                digest = hashlib.sha256(content).hexdigest()
                entry = RequestLogEntry(
                    request_id=digest[:16], source=self.source, method="GET", endpoint=url,
                    params=safe_params, status_code=response.status_code, attempt=attempt,
                    elapsed_seconds=round(elapsed, 6), retrieved_at_utc=_utcnow(),
                    response_sha256=digest, cache_hit=False, rate_limit=self._rate_headers(response) or None,
                )
                self.logs.append(entry)

                if response.status_code in self.retry_policy.retry_statuses and attempt < self.retry_policy.max_attempts:
                    self.sleeper(self.retry_policy.delay(attempt, response.headers.get("Retry-After")))
                    continue
                response.raise_for_status()

                if cacheable and self.cache:
                    self.cache.put("GET", url, params, content)
                if self.audit_store:
                    self.audit_store.write(
                        source=self.source,
                        content=content,
                        content_type=response.headers.get("Content-Type"),
                        metadata={"endpoint": url, "params": safe_params, "retrieved_at_utc": entry.retrieved_at_utc},
                    )
                return response
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                if attempt < self.retry_policy.max_attempts:
                    self.sleeper(self.retry_policy.delay(attempt))
                    continue
                break
        raise HTTPRequestError(f"{self.source} request failed after {self.retry_policy.max_attempts} attempts: {last_exc}") from last_exc
    def post(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        """POST with the same retry/audit semantics as :meth:`get`.

        POST responses are intentionally not placed in the simple disk cache because the
        cache key currently models query parameters only. The JSON body is recorded only in
        redacted form in the request log/audit metadata.
        """
        safe_params = _redact_mapping(params)
        safe_body = _redact_mapping(json_body)
        log_params: dict[str, Any] = dict(safe_params)
        if safe_body:
            log_params["__json__"] = safe_body

        last_exc: Exception | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            started = time.perf_counter()
            try:
                response = self.client.post(url, params=params, headers=headers, json=json_body)
                elapsed = time.perf_counter() - started
                content = response.content
                digest = hashlib.sha256(content).hexdigest()
                entry = RequestLogEntry(
                    request_id=digest[:16], source=self.source, method="POST", endpoint=url,
                    params=log_params, status_code=response.status_code, attempt=attempt,
                    elapsed_seconds=round(elapsed, 6), retrieved_at_utc=_utcnow(),
                    response_sha256=digest, cache_hit=False, rate_limit=self._rate_headers(response) or None,
                )
                self.logs.append(entry)

                if response.status_code in self.retry_policy.retry_statuses and attempt < self.retry_policy.max_attempts:
                    self.sleeper(self.retry_policy.delay(attempt, response.headers.get("Retry-After")))
                    continue
                response.raise_for_status()

                if self.audit_store:
                    self.audit_store.write(
                        source=self.source,
                        content=content,
                        content_type=response.headers.get("Content-Type"),
                        metadata={
                            "endpoint": url,
                            "params": safe_params,
                            "json": safe_body,
                            "retrieved_at_utc": entry.retrieved_at_utc,
                        },
                    )
                return response
            except (httpx.HTTPError, OSError) as exc:
                last_exc = exc
                if attempt < self.retry_policy.max_attempts:
                    self.sleeper(self.retry_policy.delay(attempt))
                    continue
                break
        raise HTTPRequestError(f"{self.source} request failed after {self.retry_policy.max_attempts} attempts: {last_exc}") from last_exc

