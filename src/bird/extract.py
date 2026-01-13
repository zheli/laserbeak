from __future__ import annotations

import re

_TWEET_URL_REGEX = re.compile(r"(?:twitter\.com|x\.com)/(?:\w+/status|i/web/status)/(\d+)", re.IGNORECASE)
_LIST_URL_REGEX = re.compile(r"(?:twitter\.com|x\.com)/i/lists/(\d+)", re.IGNORECASE)
_LIST_ID_REGEX = re.compile(r"^\d{5,}$")
_BOOKMARK_FOLDER_URL_REGEX = re.compile(r"(?:twitter\.com|x\.com)/i/bookmarks/(\d+)", re.IGNORECASE)
_BOOKMARK_FOLDER_ID_REGEX = re.compile(r"^\d{5,}$")


def extract_tweet_id(input_value: str) -> str:
    match = _TWEET_URL_REGEX.search(input_value)
    if match:
        return match.group(1)
    return input_value


def extract_list_id(input_value: str) -> str | None:
    trimmed = input_value.strip()
    if not trimmed:
        return None
    match = _LIST_URL_REGEX.search(trimmed)
    if match:
        return match.group(1)
    if _LIST_ID_REGEX.match(trimmed):
        return trimmed
    return None


def extract_bookmark_folder_id(input_value: str) -> str | None:
    trimmed = input_value.strip()
    if not trimmed:
        return None
    match = _BOOKMARK_FOLDER_URL_REGEX.search(trimmed)
    if match:
        return match.group(1)
    if _BOOKMARK_FOLDER_ID_REGEX.match(trimmed):
        return trimmed
    return None
