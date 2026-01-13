from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Literal

StatusKind = Literal["ok", "warn", "err", "info", "hint"]
LabelKind = Literal["url", "date", "source", "engine", "credentials", "user", "userId", "email"]


@dataclass(frozen=True)
class OutputConfig:
    plain: bool
    emoji: bool
    color: bool


_STATUS = {
    "ok": {"emoji": "✅", "text": "OK:", "plain": "[ok]"},
    "warn": {"emoji": "⚠️", "text": "Warning:", "plain": "[warn]"},
    "err": {"emoji": "❌", "text": "Error:", "plain": "[err]"},
    "info": {"emoji": "ℹ️", "text": "Info:", "plain": "[info]"},
    "hint": {"emoji": "ℹ️", "text": "Hint:", "plain": "[hint]"},
}

_LABELS = {
    "url": {"emoji": "🔗", "text": "URL:", "plain": "url:"},
    "date": {"emoji": "📅", "text": "Date:", "plain": "date:"},
    "source": {"emoji": "📍", "text": "Source:", "plain": "source:"},
    "engine": {"emoji": "⚙️", "text": "Engine:", "plain": "engine:"},
    "credentials": {"emoji": "🔑", "text": "Credentials:", "plain": "credentials:"},
    "user": {"emoji": "🙋", "text": "User:", "plain": "user:"},
    "userId": {"emoji": "🪪", "text": "User ID:", "plain": "user_id:"},
    "email": {"emoji": "📧", "text": "Email:", "plain": "email:"},
}


def resolve_output_config_from_argv(argv: list[str], env: dict[str, str], is_tty: bool) -> OutputConfig:
    has_no_color_env = "NO_COLOR" in env or env.get("TERM") == "dumb"
    default_color = is_tty and not has_no_color_env

    plain = "--plain" in argv
    emoji = not plain and "--no-emoji" not in argv
    color = not plain and "--no-color" not in argv and default_color

    return OutputConfig(plain=plain, emoji=emoji, color=color)


def resolve_output_config_from_options(opts: dict[str, bool | None], env: dict[str, str], is_tty: bool) -> OutputConfig:
    has_no_color_env = "NO_COLOR" in env or env.get("TERM") == "dumb"
    default_color = is_tty and not has_no_color_env

    plain = bool(opts.get("plain"))
    emoji = not plain and (opts.get("emoji") if opts.get("emoji") is not None else True)
    color = not plain and (opts.get("color") if opts.get("color") is not None else True) and default_color

    return OutputConfig(plain=plain, emoji=emoji, color=color)


def status_prefix(kind: StatusKind, cfg: OutputConfig) -> str:
    if cfg.plain:
        return f"{_STATUS[kind]['plain']} "
    if cfg.emoji:
        return f"{_STATUS[kind]['emoji']} "
    return f"{_STATUS[kind]['text']} "


def label_prefix(kind: LabelKind, cfg: OutputConfig) -> str:
    if cfg.plain:
        return f"{_LABELS[kind]['plain']} "
    if cfg.emoji:
        return f"{_LABELS[kind]['emoji']} "
    return f"{_LABELS[kind]['text']} "


def format_stats_line(stats: dict[str, int | None], cfg: OutputConfig) -> str:
    like_count = stats.get("likeCount") or 0
    retweet_count = stats.get("retweetCount") or 0
    reply_count = stats.get("replyCount") or 0

    if cfg.plain:
        return f"likes: {like_count}  retweets: {retweet_count}  replies: {reply_count}"
    if not cfg.emoji:
        return f"Likes {like_count}  Retweets {retweet_count}  Replies {reply_count}"
    return f"❤️ {like_count}  🔁 {retweet_count}  💬 {reply_count}"


def format_tweet_url(tweet_id: str) -> str:
    return f"https://x.com/i/status/{tweet_id}"


def format_tweet_url_line(tweet_id: str, cfg: OutputConfig) -> str:
    return f"{label_prefix('url', cfg)}{format_tweet_url(tweet_id)}"
