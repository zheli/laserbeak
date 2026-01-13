from __future__ import annotations

import re

_HANDLE_REGEX = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def normalize_handle(input_value: str | None) -> str | None:
    raw = (input_value or "").strip()
    if not raw:
        return None
    without_at = raw[1:] if raw.startswith("@") else raw
    handle = without_at.strip()
    if not handle:
        return None
    if not _HANDLE_REGEX.match(handle):
        return None
    return handle


def mentions_query_from_user_option(user_option: str | None) -> dict:
    if user_option is None:
        return {"query": None, "error": None}

    handle = normalize_handle(user_option)
    if not handle:
        return {
            "query": None,
            "error": "Invalid --user handle. Expected something like @steipete (letters, digits, underscore; max 15).",
        }

    return {"query": f"@{handle}", "error": None}
