from __future__ import annotations

import re

_TWEET_URL_REGEX = re.compile(r"^(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[^/]+/status/\d+", re.IGNORECASE)
_TWEET_ID_REGEX = re.compile(r"^\d{8,}$")


def looks_like_tweet_input(value: str) -> bool:
    trimmed = value.strip()
    if not trimmed:
        return False
    return bool(_TWEET_URL_REGEX.match(trimmed) or _TWEET_ID_REGEX.match(trimmed))


def resolve_cli_invocation(raw_args: list[str], known_commands: set[str]) -> dict:
    if not raw_args:
        return {"argv": None, "show_help": True}

    has_known_command = any(arg in known_commands for arg in raw_args)
    if not has_known_command:
        tweet_arg_index = next((i for i, arg in enumerate(raw_args) if looks_like_tweet_input(arg)), -1)
        if tweet_arg_index >= 0:
            rewritten_args = raw_args[:]
            rewritten_args.insert(tweet_arg_index, "read")
            return {"argv": rewritten_args, "show_help": False}

    return {"argv": None, "show_help": False}
