from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
from typing import Callable

import httpx

_DEFAULT_CACHE_FILENAME = "query-ids-cache.json"
_DEFAULT_TTL_MS = 24 * 60 * 60 * 1000

_DISCOVERY_PAGES = [
    "https://x.com/?lang=en",
    "https://x.com/explore",
    "https://x.com/notifications",
    "https://x.com/settings/profile",
]

_BUNDLE_URL_REGEX = re.compile(r"https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/[A-Za-z0-9.-]+\.js")
_QUERY_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")

_OPERATION_PATTERNS = [
    {
        "regex": re.compile(
            r"e\.exports=\{queryId\s*:\s*[\"']([^\"']+)[\"']\s*,\s*operationName\s*:\s*[\"']([^\"']+)[\"']",
            re.DOTALL,
        ),
        "operation_group": 2,
        "query_id_group": 1,
    },
    {
        "regex": re.compile(
            r"e\.exports=\{operationName\s*:\s*[\"']([^\"']+)[\"']\s*,\s*queryId\s*:\s*[\"']([^\"']+)[\"']",
            re.DOTALL,
        ),
        "operation_group": 1,
        "query_id_group": 2,
    },
    {
        "regex": re.compile(
            r"operationName\s*[:=]\s*[\"']([^\"']+)[\"'](.{0,4000}?)queryId\s*[:=]\s*[\"']([^\"']+)[\"']",
            re.DOTALL,
        ),
        "operation_group": 1,
        "query_id_group": 3,
    },
    {
        "regex": re.compile(
            r"queryId\s*[:=]\s*[\"']([^\"']+)[\"'](.{0,4000}?)operationName\s*[:=]\s*[\"']([^\"']+)[\"']",
            re.DOTALL,
        ),
        "operation_group": 3,
        "query_id_group": 1,
    },
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass(frozen=True)
class RuntimeQueryIdSnapshot:
    fetchedAt: str
    ttlMs: int
    ids: dict[str, str]
    discovery: dict[str, list[str]]


@dataclass(frozen=True)
class RuntimeQueryIdSnapshotInfo:
    snapshot: RuntimeQueryIdSnapshot
    cachePath: str
    ageMs: float
    isFresh: bool


@dataclass
class RuntimeQueryIdsOptions:
    cachePath: str | None = None
    ttlMs: int | None = None
    fetchImpl: Callable[[str], str] | None = None


class RuntimeQueryIdStore:
    def __init__(self, cache_path: Path, ttl_ms: int, fetch_impl: Callable[[str], str]):
        self.cache_path = cache_path
        self.ttl_ms = ttl_ms
        self._fetch_impl = fetch_impl
        self._memory_snapshot: RuntimeQueryIdSnapshot | None = None
        self._load_once: RuntimeQueryIdSnapshot | None = None
        self._refresh_in_flight = False

    def _load_snapshot(self) -> RuntimeQueryIdSnapshot | None:
        if self._memory_snapshot is not None:
            return self._memory_snapshot
        if self._load_once is not None:
            return self._load_once
        self._load_once = _read_snapshot_from_disk(self.cache_path)
        self._memory_snapshot = self._load_once
        return self._load_once

    def get_snapshot_info(self) -> RuntimeQueryIdSnapshotInfo | None:
        snapshot = self._load_snapshot()
        if not snapshot:
            return None
        fetched_at_ms = _parse_iso_timestamp(snapshot.fetchedAt) or int(time.time() * 1000)
        age_ms = max(0, int(time.time() * 1000) - fetched_at_ms)
        effective_ttl = snapshot.ttlMs if snapshot.ttlMs else self.ttl_ms
        is_fresh = age_ms <= effective_ttl
        return RuntimeQueryIdSnapshotInfo(
            snapshot=snapshot,
            cachePath=str(self.cache_path),
            ageMs=age_ms,
            isFresh=is_fresh,
        )

    def get_query_id(self, operation_name: str) -> str | None:
        info = self.get_snapshot_info()
        if not info:
            return None
        return info.snapshot.ids.get(operation_name)

    def refresh(self, operation_names: list[str], *, force: bool = False) -> RuntimeQueryIdSnapshotInfo | None:
        if self._refresh_in_flight:
            return self.get_snapshot_info()
        self._refresh_in_flight = True
        try:
            current = self.get_snapshot_info()
            if current and not force and current.isFresh:
                return current

            targets = set(operation_names)
            bundle_urls = _discover_bundles(self._fetch_impl)
            discovered = _fetch_and_extract(self._fetch_impl, bundle_urls, targets)
            if not discovered:
                return current

            ids: dict[str, str] = {}
            for name in operation_names:
                entry = discovered.get(name)
                if entry:
                    ids[name] = entry["queryId"]

            snapshot = RuntimeQueryIdSnapshot(
                fetchedAt=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                ttlMs=self.ttl_ms,
                ids=ids,
                discovery={
                    "pages": list(_DISCOVERY_PAGES),
                    "bundles": [url.split("/")[-1] for url in bundle_urls],
                },
            )

            _write_snapshot_to_disk(self.cache_path, snapshot)
            self._memory_snapshot = snapshot
            return self.get_snapshot_info()
        finally:
            self._refresh_in_flight = False

    def clear_memory(self) -> None:
        self._memory_snapshot = None
        self._load_once = None


def _fetch_text(url: str) -> str:
    response = httpx.get(url, headers=_HEADERS, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code} for {url}: {response.text[:120]}")
    return response.text


def _resolve_default_cache_path() -> Path:
    override = os.environ.get("BIRD_QUERY_IDS_CACHE")
    if override and override.strip():
        return Path(override.strip()).expanduser().resolve()
    return Path.home() / ".config" / "bird" / _DEFAULT_CACHE_FILENAME


def _parse_snapshot(raw: object) -> RuntimeQueryIdSnapshot | None:
    if not isinstance(raw, dict):
        return None
    fetched_at = raw.get("fetchedAt") if isinstance(raw.get("fetchedAt"), str) else None
    ttl_ms = raw.get("ttlMs") if isinstance(raw.get("ttlMs"), int) else None
    ids = raw.get("ids") if isinstance(raw.get("ids"), dict) else None
    discovery = raw.get("discovery") if isinstance(raw.get("discovery"), dict) else None
    if not fetched_at or not ttl_ms or not ids or not discovery:
        return None
    pages = discovery.get("pages") if isinstance(discovery.get("pages"), list) else None
    bundles = discovery.get("bundles") if isinstance(discovery.get("bundles"), list) else None
    if pages is None or bundles is None:
        return None
    normalized_ids = {k: v.strip() for k, v in ids.items() if isinstance(v, str) and v.strip()}
    return RuntimeQueryIdSnapshot(
        fetchedAt=fetched_at,
        ttlMs=ttl_ms,
        ids=normalized_ids,
        discovery={
            "pages": [p for p in pages if isinstance(p, str)],
            "bundles": [b for b in bundles if isinstance(b, str)],
        },
    )


def _read_snapshot_from_disk(cache_path: Path) -> RuntimeQueryIdSnapshot | None:
    try:
        raw = cache_path.read_text(encoding="utf-8")
        return _parse_snapshot(json.loads(raw))
    except Exception:
        return None


def _write_snapshot_to_disk(cache_path: Path, snapshot: RuntimeQueryIdSnapshot) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(snapshot.__dict__, indent=2) + "\n", encoding="utf-8")


def _parse_iso_timestamp(value: str) -> int | None:
    try:
        from datetime import datetime

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _discover_bundles(fetch_impl: Callable[[str], str]) -> list[str]:
    bundles: set[str] = set()
    for page in _DISCOVERY_PAGES:
        try:
            html = fetch_impl(page)
            for match in _BUNDLE_URL_REGEX.findall(html):
                bundles.add(match)
        except Exception:
            continue
    discovered = list(bundles)
    if not discovered:
        raise RuntimeError("No client bundles discovered; x.com layout may have changed.")
    return discovered


def _extract_operations(
    bundle_contents: str,
    bundle_label: str,
    targets: set[str],
    discovered: dict[str, dict[str, str]],
) -> None:
    for pattern in _OPERATION_PATTERNS:
        for match in pattern["regex"].finditer(bundle_contents):
            operation_name = match.group(pattern["operation_group"])
            query_id = match.group(pattern["query_id_group"])
            if not operation_name or not query_id:
                continue
            if operation_name not in targets:
                continue
            if not _QUERY_ID_REGEX.match(query_id):
                continue
            if operation_name in discovered:
                continue
            discovered[operation_name] = {"queryId": query_id, "bundle": bundle_label}
            if len(discovered) == len(targets):
                return


def _fetch_and_extract(
    fetch_impl: Callable[[str], str],
    bundle_urls: list[str],
    targets: set[str],
) -> dict[str, dict[str, str]]:
    discovered: dict[str, dict[str, str]] = {}
    concurrency = 6

    for i in range(0, len(bundle_urls), concurrency):
        chunk = bundle_urls[i : i + concurrency]
        for url in chunk:
            if len(discovered) == len(targets):
                return discovered
            label = url.split("/")[-1] if "/" in url else url
            try:
                js = fetch_impl(url)
                _extract_operations(js, label, targets, discovered)
            except Exception:
                continue
        if len(discovered) == len(targets):
            break

    return discovered


def create_runtime_query_id_store(options: RuntimeQueryIdsOptions | None = None) -> RuntimeQueryIdStore:
    options = options or RuntimeQueryIdsOptions()
    fetch_impl = options.fetchImpl or _fetch_text
    ttl_ms = options.ttlMs or _DEFAULT_TTL_MS
    cache_path = Path(options.cachePath).expanduser().resolve() if options.cachePath else _resolve_default_cache_path()
    return RuntimeQueryIdStore(cache_path=cache_path, ttl_ms=ttl_ms, fetch_impl=fetch_impl)


runtime_query_ids = create_runtime_query_id_store()
