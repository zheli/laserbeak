from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import json5

from .types import CookieSource


@dataclass(frozen=True)
class LaserbeakConfig:
    chromeProfile: str | None = None
    firefoxProfile: str | None = None
    cookieSource: CookieSource | list[CookieSource] | None = None
    cookieTimeoutMs: int | None = None
    timeoutMs: int | None = None
    quoteDepth: int | None = None


def _read_config_file(path: Path, warn: Callable[[str], None]) -> dict:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json5.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except Exception as exc:  # pragma: no cover - defensive
        warn(f"Failed to parse config at {path}: {exc}")
        return {}


def load_config(warn: Callable[[str], None]) -> LaserbeakConfig:
    global_path = Path.home() / ".config" / "laserbeak" / "config.json5"
    local_path = Path.cwd() / ".laserbeakrc.json5"

    merged: dict = {}
    merged.update(_read_config_file(global_path, warn))
    merged.update(_read_config_file(local_path, warn))

    return LaserbeakConfig(
        chromeProfile=merged.get("chromeProfile"),
        firefoxProfile=merged.get("firefoxProfile"),
        cookieSource=merged.get("cookieSource"),
        cookieTimeoutMs=merged.get("cookieTimeoutMs"),
        timeoutMs=merged.get("timeoutMs"),
        quoteDepth=merged.get("quoteDepth"),
    )
