from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_cli_version() -> str:
    try:
        return version("laserbeak")
    except PackageNotFoundError:
        return "0.0.0+dev"
