from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from importlib import resources

from . import data

FeatureOverrides = dict[str, dict[str, bool] | dict[str, dict[str, bool]]]


@dataclass(frozen=True)
class FeatureOverridesSnapshot:
    cachePath: str
    overrides: dict


_DEFAULT_CACHE_FILENAME = "features.json"
_cached_overrides: dict | None = None


def _normalize_feature_map(value: object) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {key: val for key, val in value.items() if isinstance(val, bool)}


def _normalize_overrides(value: object) -> dict:
    if not isinstance(value, dict):
        return {"global": {}, "sets": {}}
    global_map = _normalize_feature_map(value.get("global"))
    sets: dict[str, dict[str, bool]] = {}
    raw_sets = value.get("sets") if isinstance(value.get("sets"), dict) else {}
    for name, entry in (raw_sets or {}).items():
        normalized = _normalize_feature_map(entry)
        if normalized:
            sets[name] = normalized
    return {"global": global_map, "sets": sets}


def _merge_overrides(base: dict, other: dict) -> dict:
    sets = {**base.get("sets", {})}
    for set_name, overrides in other.get("sets", {}).items():
        existing = sets.get(set_name, {})
        sets[set_name] = {**existing, **overrides}
    return {"global": {**base.get("global", {}), **other.get("global", {})}, "sets": sets}


def _to_feature_overrides(overrides: dict) -> dict:
    result: dict[str, dict] = {}
    if overrides.get("global"):
        result["global"] = overrides["global"]
    if overrides.get("sets"):
        result["sets"] = {k: v for k, v in overrides["sets"].items() if v}
    return result


def _resolve_features_cache_path() -> Path:
    override = os.environ.get("BIRD_FEATURES_CACHE") or os.environ.get("BIRD_FEATURES_PATH")
    if override and override.strip():
        return Path(override.strip()).expanduser().resolve()
    return Path.home() / ".config" / "bird" / _DEFAULT_CACHE_FILENAME


def _read_overrides_from_file(cache_path: Path) -> dict | None:
    if not cache_path.exists():
        return None
    try:
        raw = cache_path.read_text(encoding="utf-8")
        return _normalize_overrides(json.loads(raw))
    except Exception:
        return None


def _read_overrides_from_env() -> dict | None:
    raw = os.environ.get("BIRD_FEATURES_JSON")
    if not raw:
        return None
    try:
        return _normalize_overrides(json.loads(raw))
    except Exception:
        return None


def _read_default_overrides() -> dict:
    with resources.files(data).joinpath("features.json").open("r", encoding="utf-8") as handle:
        return _normalize_overrides(json.load(handle))


def _write_overrides_to_disk(cache_path: Path, overrides: dict) -> None:
    payload = _to_feature_overrides(overrides)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_feature_overrides() -> dict:
    global _cached_overrides
    if _cached_overrides is not None:
        return _cached_overrides

    base = _read_default_overrides()
    from_file = _read_overrides_from_file(_resolve_features_cache_path())
    from_env = _read_overrides_from_env()

    merged = base
    if from_file:
        merged = _merge_overrides(merged, from_file)
    if from_env:
        merged = _merge_overrides(merged, from_env)

    _cached_overrides = merged
    return merged


def get_feature_overrides_snapshot() -> FeatureOverridesSnapshot:
    overrides = _to_feature_overrides(load_feature_overrides())
    return FeatureOverridesSnapshot(cachePath=str(_resolve_features_cache_path()), overrides=overrides)


def apply_feature_overrides(set_name: str, base: dict[str, bool]) -> dict[str, bool]:
    overrides = load_feature_overrides()
    global_overrides = overrides.get("global", {})
    set_overrides = overrides.get("sets", {}).get(set_name)
    if not global_overrides and not set_overrides:
        return base
    if set_overrides:
        return {**base, **global_overrides, **set_overrides}
    return {**base, **global_overrides}


def refresh_feature_overrides_cache() -> FeatureOverridesSnapshot:
    cache_path = _resolve_features_cache_path()
    base = _read_default_overrides()
    from_file = _read_overrides_from_file(cache_path)
    merged = _merge_overrides(base, from_file or {"global": {}, "sets": {}})
    _write_overrides_to_disk(cache_path, merged)
    global _cached_overrides
    _cached_overrides = None
    return FeatureOverridesSnapshot(cachePath=str(cache_path), overrides=_to_feature_overrides(merged))


def clear_feature_overrides_cache() -> None:
    global _cached_overrides
    _cached_overrides = None
