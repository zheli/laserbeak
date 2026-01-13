from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import typer
import click
from typer.main import get_command

from .config import LaserbeakConfig, load_config
from .cookies import resolve_credentials
from .extract import extract_bookmark_folder_id, extract_list_id, extract_tweet_id
from .normalize import mentions_query_from_user_option, normalize_handle
from .output import (
    format_stats_line,
    format_tweet_url_line,
    label_prefix,
    resolve_output_config_from_options,
    status_prefix,
)
from .runtime_features import get_feature_overrides_snapshot, refresh_feature_overrides_cache
from .runtime_query_ids import runtime_query_ids
from .styles import style_text
from .twitter_client import TwitterClient
from .types import TweetData

app = typer.Typer(add_completion=False)

KNOWN_COMMANDS = {
    "tweet",
    "reply",
    "query-ids",
    "read",
    "replies",
    "thread",
    "search",
    "mentions",
    "bookmarks",
    "unbookmark",
    "following",
    "followers",
    "likes",
    "lists",
    "list-timeline",
    "help",
    "whoami",
    "check",
}


def _parse_cookie_source(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"safari", "chrome", "firefox"}:
        return normalized
    raise typer.BadParameter(f"Invalid --cookie-source '{value}'. Allowed: safari, chrome, firefox.")


def _resolve_cookie_source_order(input_value: object) -> list[str] | None:
    if isinstance(input_value, str):
        return [_parse_cookie_source(input_value)]
    if isinstance(input_value, list):
        result: list[str] = []
        for entry in input_value:
            if isinstance(entry, str):
                result.append(_parse_cookie_source(entry))
        return result or None
    return None


def _resolve_timeout_ms(*values) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed > 0:
            return parsed
    return None


def _resolve_quote_depth(*values) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed >= 0:
            return max(0, parsed)
    return None


def _detect_mime(path: str) -> str | None:
    lower = path.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith((".mp4", ".m4v")):
        return "video/mp4"
    if lower.endswith(".mov"):
        return "video/quicktime"
    return None


@dataclass
class MediaSpec:
    path: str
    mime: str
    buffer: bytes
    alt: str | None = None


@dataclass
class CliContext:
    is_tty: bool
    output: object
    config: LaserbeakConfig

    def colors(self, *, color: str | None = None, bold: bool = False) -> Callable[[str], str]:
        def wrap(text: str) -> str:
            return style_text(text, color=color, bold=bold, enabled=self.is_tty and self.output.color)
        return wrap

    @property
    def banner(self):
        return self.colors(color="blue", bold=True)

    @property
    def subtitle(self):
        return self.colors(color="gray")

    @property
    def section(self):
        return self.colors(color="white", bold=True)

    @property
    def bullet(self):
        return self.colors(color="blue")

    @property
    def command(self):
        return self.colors(color="cyan", bold=True)

    @property
    def option(self):
        return self.colors(color="cyan")

    @property
    def argument(self):
        return self.colors(color="magenta")

    @property
    def description(self):
        return self.colors(color="white")

    @property
    def muted(self):
        return self.colors(color="gray")

    @property
    def accent(self):
        return self.colors(color="green")

    def p(self, kind: str) -> str:
        prefix = status_prefix(kind, self.output)
        if self.output.plain or not self.output.color:
            return prefix
        color = {
            "ok": "green",
            "warn": "yellow",
            "err": "red",
            "info": "cyan",
        }.get(kind, "gray")
        return style_text(prefix, color=color, enabled=self.is_tty and self.output.color)

    def l(self, kind: str) -> str:
        prefix = label_prefix(kind, self.output)
        if self.output.plain or not self.output.color:
            return prefix
        color = {
            "url": "cyan",
            "date": "magenta",
            "source": "gray",
            "engine": "blue",
            "credentials": "yellow",
            "user": "cyan",
            "userId": "magenta",
            "email": "green",
        }.get(kind, "gray")
        return style_text(prefix, color=color, enabled=self.is_tty and self.output.color)

    def resolve_timeout_from_options(self, timeout: str | None) -> int | None:
        return _resolve_timeout_ms(timeout, self.config.timeoutMs, os.environ.get("BIRD_TIMEOUT_MS"))

    def resolve_cookie_timeout_from_options(self, timeout: str | None) -> int | None:
        return _resolve_timeout_ms(timeout, self.config.cookieTimeoutMs, os.environ.get("BIRD_COOKIE_TIMEOUT_MS"))

    def resolve_quote_depth_from_options(self, quote_depth: str | None) -> int | None:
        return _resolve_quote_depth(quote_depth, self.config.quoteDepth, os.environ.get("BIRD_QUOTE_DEPTH"))

    def resolve_credentials_from_options(self, opts: dict) -> dict:
        raw_sources = opts.get("cookie_source") or []
        parsed_sources = [_parse_cookie_source(value) for value in raw_sources] if raw_sources else []
        cookie_source = parsed_sources or _resolve_cookie_source_order(self.config.cookieSource)
        if not cookie_source:
            cookie_source = ["safari", "chrome", "firefox"]
        return resolve_credentials(
            auth_token=opts.get("auth_token"),
            ct0=opts.get("ct0"),
            cookie_source=cookie_source,
            chrome_profile=opts.get("chrome_profile") or self.config.chromeProfile,
            firefox_profile=opts.get("firefox_profile") or self.config.firefoxProfile,
            cookie_timeout_ms=self.resolve_cookie_timeout_from_options(opts.get("cookie_timeout")),
        )

    def load_media(self, media: list[str], alts: list[str]) -> list[MediaSpec]:
        if not media:
            return []
        specs: list[MediaSpec] = []
        for index, path in enumerate(media):
            mime = _detect_mime(path)
            if not mime:
                raise ValueError(f"Unsupported media type for {path}. Supported: jpg, jpeg, png, webp, gif, mp4, mov")
            buffer = Path(path).read_bytes()
            specs.append(MediaSpec(path=path, mime=mime, buffer=buffer, alt=alts[index] if index < len(alts) else None))

        video_count = sum(1 for spec in specs if spec.mime.startswith("video/"))
        if video_count > 1:
            raise ValueError("Only one video can be attached")
        if video_count == 1 and len(specs) > 1:
            raise ValueError("Video cannot be combined with other media")
        if len(specs) > 4:
            raise ValueError("Maximum 4 media attachments")
        return specs

    def print_tweets(self, tweets: list[TweetData], *, json_output: bool = False, empty_message: str | None = None, show_separator: bool = True) -> None:
        if json_output:
            print(json.dumps(tweets, indent=2))
            return
        if not tweets:
            print(empty_message or "No tweets found.")
            return
        for tweet in tweets:
            print(f"\n@{tweet['author']['username']} ({tweet['author']['name']}):")
            print(tweet["text"])
            if tweet.get("createdAt"):
                print(f"{self.l('date')}{tweet['createdAt']}")
            print(f"{self.l('url')}https://x.com/{tweet['author']['username']}/status/{tweet['id']}")
            if show_separator:
                print("-" * 50)


def _build_context(ctx: typer.Context) -> CliContext:
    is_tty = sys.stdout.isatty()
    output = resolve_output_config_from_options(ctx.obj.get("output_opts", {}), os.environ, is_tty)
    config = load_config(lambda message: print(f"{message}", file=sys.stderr))
    return CliContext(is_tty=is_tty, output=output, config=config)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    auth_token: str | None = typer.Option(None, "--auth-token", help="Twitter auth_token cookie"),
    ct0: str | None = typer.Option(None, "--ct0", help="Twitter ct0 cookie"),
    chrome_profile: str | None = typer.Option(None, "--chrome-profile", help="Chrome profile name for cookie extraction"),
    firefox_profile: str | None = typer.Option(None, "--firefox-profile", help="Firefox profile name for cookie extraction"),
    cookie_timeout: str | None = typer.Option(None, "--cookie-timeout", help="Cookie extraction timeout in milliseconds"),
    cookie_source: List[str] = typer.Option(None, "--cookie-source", help="Cookie source for browser cookie extraction (repeatable)"),
    media: List[str] = typer.Option(None, "--media", help="Attach media file (repeatable, up to 4 images or 1 video)"),
    alt: List[str] = typer.Option(None, "--alt", help="Alt text for the corresponding --media (repeatable)"),
    timeout: str | None = typer.Option(None, "--timeout", help="Request timeout in milliseconds"),
    quote_depth: str | None = typer.Option(None, "--quote-depth", help="Max quoted tweet depth (default: 1; 0 disables)"),
    plain: bool = typer.Option(False, "--plain", help="Plain output (stable, no emoji, no color)"),
    no_emoji: bool = typer.Option(False, "--no-emoji", help="Disable emoji output"),
    no_color: bool = typer.Option(False, "--no-color", help="Disable ANSI colors (or set NO_COLOR)"),
):
    if ctx.obj is None:
        ctx.obj = {}
    ctx.obj["output_opts"] = {"plain": plain, "emoji": not no_emoji, "color": not no_color}
    ctx.obj["global_opts"] = {
        "auth_token": auth_token,
        "ct0": ct0,
        "chrome_profile": chrome_profile,
        "firefox_profile": firefox_profile,
        "cookie_timeout": cookie_timeout,
        "cookie_source": cookie_source or [],
        "media": media or [],
        "alt": alt or [],
        "timeout": timeout,
        "quote_depth": quote_depth,
    }
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command("help")
def help_command(ctx: typer.Context, command: str | None = typer.Argument(None)) -> None:
    click_cmd = get_command(app)
    if not command:
        typer.echo(click_cmd.get_help(ctx))
        return
    subcommand = click_cmd.get_command(ctx, command)
    if subcommand is None:
        typer.echo(f"Unknown command: {command}", err=True)
        raise typer.Exit(code=2)
    sub_ctx = click.Context(subcommand, info_name=command, parent=ctx)
    typer.echo(subcommand.get_help(sub_ctx))


@app.command("tweet")
def tweet_command(ctx: typer.Context, text: str) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    try:
        media_specs = context.load_media(opts.get("media", []), opts.get("alt", []))
    except Exception as exc:
        typer.echo(f"{context.p('err')}{exc}", err=True)
        raise typer.Exit(code=1)

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)

    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)
    if cookies.get("source"):
        typer.echo(f"{context.l('source')}{cookies.get('source')}", err=True)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    media_ids = []
    for item in media_specs:
        upload = client.upload_media(data=item.buffer, mime_type=item.mime, alt=item.alt)
        if not upload.get("success") or not upload.get("mediaId"):
            typer.echo(f"{context.p('err')}Media upload failed: {upload.get('error') or 'Unknown error'}", err=True)
            raise typer.Exit(code=1)
        media_ids.append(upload.get("mediaId"))

    result = client.tweet(text, media_ids)
    if result.get("success"):
        typer.echo(f"{context.p('ok')}Tweet posted successfully!")
        typer.echo(format_tweet_url_line(result.get("tweetId"), context.output))
        return
    typer.echo(f"{context.p('err')}Failed to post tweet: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("reply")
def reply_command(ctx: typer.Context, tweet_id_or_url: str, text: str) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    try:
        media_specs = context.load_media(opts.get("media", []), opts.get("alt", []))
    except Exception as exc:
        typer.echo(f"{context.p('err')}{exc}", err=True)
        raise typer.Exit(code=1)

    tweet_id = extract_tweet_id(tweet_id_or_url)
    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)

    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)
    if cookies.get("source"):
        typer.echo(f"{context.l('source')}{cookies.get('source')}", err=True)

    typer.echo(f"{context.p('info')}Replying to tweet: {tweet_id}", err=True)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    media_ids = []
    for item in media_specs:
        upload = client.upload_media(data=item.buffer, mime_type=item.mime, alt=item.alt)
        if not upload.get("success") or not upload.get("mediaId"):
            typer.echo(f"{context.p('err')}Media upload failed: {upload.get('error') or 'Unknown error'}", err=True)
            raise typer.Exit(code=1)
        media_ids.append(upload.get("mediaId"))

    result = client.reply(text, tweet_id, media_ids)
    if result.get("success"):
        typer.echo(f"{context.p('ok')}Reply posted successfully!")
        typer.echo(format_tweet_url_line(result.get("tweetId"), context.output))
        return
    typer.echo(f"{context.p('err')}Failed to post reply: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("read")
def read_command(
    ctx: typer.Context,
    tweet_id_or_url: str,
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))
    tweet_id = extract_tweet_id(tweet_id_or_url)

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = client.get_tweet(tweet_id, include_raw=include_raw)
    if result.get("success") and result.get("tweet"):
        if json_output or json_full:
            typer.echo(json.dumps(result.get("tweet"), indent=2))
        else:
            tweet = result["tweet"]
            typer.echo(f"@{tweet['author']['username']} ({tweet['author']['name']}):")
            typer.echo(tweet["text"])
            if tweet.get("createdAt"):
                typer.echo(f"\n{context.l('date')}{tweet.get('createdAt')}")
            typer.echo(format_stats_line(tweet, context.output))
        return
    typer.echo(f"{context.p('err')}Failed to read tweet: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("replies")
def replies_command(
    ctx: typer.Context,
    tweet_id_or_url: str,
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))
    tweet_id = extract_tweet_id(tweet_id_or_url)

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = client.get_replies(tweet_id, include_raw=include_raw)
    if result.get("success") and result.get("tweets") is not None:
        context.print_tweets(result.get("tweets"), json_output=json_output or json_full, empty_message="No replies found.")
        return
    typer.echo(f"{context.p('err')}Failed to fetch replies: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("thread")
def thread_command(
    ctx: typer.Context,
    tweet_id_or_url: str,
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))
    tweet_id = extract_tweet_id(tweet_id_or_url)

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = client.get_thread(tweet_id, include_raw=include_raw)
    if result.get("success") and result.get("tweets") is not None:
        context.print_tweets(result.get("tweets"), json_output=json_output or json_full, empty_message="No thread tweets found.")
        return
    typer.echo(f"{context.p('err')}Failed to fetch thread: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: str,
    count: int = typer.Option(10, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = client.search(query, count, include_raw=include_raw)
    if result.get("success") and result.get("tweets") is not None:
        context.print_tweets(result.get("tweets"), json_output=json_output or json_full, empty_message="No tweets found.")
        return
    typer.echo(f"{context.p('err')}Search failed: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("mentions")
def mentions_command(
    ctx: typer.Context,
    user: str | None = typer.Option(None, "-u", "--user"),
    count: int = typer.Option(10, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    query_info = mentions_query_from_user_option(user)
    if query_info.get("error"):
        typer.echo(f"{context.p('err')}{query_info.get('error')}", err=True)
        raise typer.Exit(code=2)

    query = query_info.get("query")

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    if not query:
        who = client.get_current_user()
        handle = normalize_handle((who.get("user") or {}).get("username")) if who.get("success") else None
        if handle:
            query = f"@{handle}"
        else:
            typer.echo(
                f"{context.p('err')}Could not determine current user ({who.get('error') or 'Unknown error'}). Use --user <handle>.",
                err=True,
            )
            raise typer.Exit(code=1)

    include_raw = json_full
    result = client.search(query, count, include_raw=include_raw)
    if result.get("success") and result.get("tweets") is not None:
        context.print_tweets(result.get("tweets"), json_output=json_output or json_full, empty_message="No mentions found.")
        return
    typer.echo(f"{context.p('err')}Failed to fetch mentions: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("bookmarks")
def bookmarks_command(
    ctx: typer.Context,
    count: int = typer.Option(20, "-n", "--count"),
    folder_id: str | None = typer.Option(None, "--folder-id"),
    all_pages: bool = typer.Option(False, "--all"),
    max_pages: int | None = typer.Option(None, "--max-pages"),
    cursor: str | None = typer.Option(None, "--cursor"),
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    use_pagination = all_pages or cursor
    if max_pages is not None and not use_pagination:
        typer.echo(f"{context.p('err')}--max-pages requires --all or --cursor.", err=True)
        raise typer.Exit(code=1)
    if not use_pagination and count <= 0:
        typer.echo(f"{context.p('err')}Invalid --count. Expected a positive integer.", err=True)
        raise typer.Exit(code=1)
    if max_pages is not None and max_pages <= 0:
        typer.echo(f"{context.p('err')}Invalid --max-pages. Expected a positive integer.", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms})
    parsed_folder_id = extract_bookmark_folder_id(folder_id) if folder_id else None
    if folder_id and not parsed_folder_id:
        typer.echo(
            f"{context.p('err')}Invalid --folder-id. Expected numeric ID or https://x.com/i/bookmarks/<id>.",
            err=True,
        )
        raise typer.Exit(code=1)

    include_raw = json_full
    if parsed_folder_id:
        result = (
            client.get_all_bookmark_folder_timeline(
                parsed_folder_id, include_raw=include_raw, max_pages=max_pages, cursor=cursor
            )
            if use_pagination
            else client.get_bookmark_folder_timeline(parsed_folder_id, count, include_raw=include_raw)
        )
        empty_message = "No bookmarks found in folder."
    else:
        result = (
            client.get_all_bookmarks(include_raw=include_raw, max_pages=max_pages, cursor=cursor)
            if use_pagination
            else client.get_bookmarks(count, include_raw=include_raw)
        )
        empty_message = "No bookmarks found."

    if result.get("success") and result.get("tweets") is not None:
        is_json = json_output or json_full
        if is_json and use_pagination:
            typer.echo(json.dumps({"tweets": result.get("tweets"), "nextCursor": result.get("nextCursor")}, indent=2))
        else:
            context.print_tweets(result.get("tweets"), json_output=is_json, empty_message=empty_message)
        return

    typer.echo(f"{context.p('err')}Failed to fetch bookmarks: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("unbookmark")
def unbookmark_command(ctx: typer.Context, tweet_ids: List[str] = typer.Argument(...)) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms})
    failures = 0
    for input_value in tweet_ids:
        tweet_id = extract_tweet_id(input_value)
        result = client.unbookmark(tweet_id)
        if result.get("success"):
            typer.echo(f"{context.p('ok')}Removed bookmark for {tweet_id}")
        else:
            failures += 1
            typer.echo(f"{context.p('err')}Failed to remove bookmark for {tweet_id}: {result.get('error')}", err=True)

    if failures > 0:
        raise typer.Exit(code=1)


@app.command("lists")
def lists_command(
    ctx: typer.Context,
    member_of: bool = typer.Option(False, "--member-of"),
    count: int = typer.Option(100, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms})
    result = client.get_list_memberships(count) if member_of else client.get_owned_lists(count)
    if result.get("success") and result.get("lists") is not None:
        if json_output:
            typer.echo(json.dumps(result.get("lists"), indent=2))
            return
        lists = result.get("lists") or []
        empty_message = "You are not a member of any lists." if member_of else "You do not own any lists."
        if not lists:
            typer.echo(empty_message)
            return
        for entry in lists:
            visibility = "[private]" if entry.get("isPrivate") else "[public]"
            typer.echo(f"{entry.get('name')} {context.muted(visibility)}")
            if entry.get("description"):
                desc = entry["description"]
                typer.echo(f"  {desc[:100]}{'...' if len(desc) > 100 else ''}")
            typer.echo(f"  {context.p('info')}{entry.get('memberCount') or 0} members")
            if entry.get("owner"):
                typer.echo(f"  {context.muted('Owner: @' + entry['owner']['username'])}")
            typer.echo(f"  {context.accent('https://x.com/i/lists/' + entry['id'])}")
            typer.echo("-" * 50)
        return
    typer.echo(f"{context.p('err')}Failed to fetch lists: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("list-timeline")
def list_timeline_command(
    ctx: typer.Context,
    list_id_or_url: str,
    count: int = typer.Option(20, "-n", "--count"),
    all_pages: bool = typer.Option(False, "--all"),
    max_pages: int | None = typer.Option(None, "--max-pages"),
    cursor: str | None = typer.Option(None, "--cursor"),
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    list_id = extract_list_id(list_id_or_url)
    if not list_id:
        typer.echo(
            f"{context.p('err')}Invalid list ID or URL. Expected numeric ID or https://x.com/i/lists/<id>.",
            err=True,
        )
        raise typer.Exit(code=2)

    use_pagination = all_pages or cursor or max_pages is not None
    if not use_pagination and count <= 0:
        typer.echo(f"{context.p('err')}Invalid --count. Expected a positive integer.", err=True)
        raise typer.Exit(code=1)
    if max_pages is not None and max_pages <= 0:
        typer.echo(f"{context.p('err')}Invalid --max-pages. Expected a positive integer.", err=True)
        raise typer.Exit(code=1)

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = (
        client.get_all_list_timeline(list_id, include_raw=include_raw, max_pages=max_pages, cursor=cursor)
        if use_pagination
        else client.get_list_timeline(list_id, count, include_raw=include_raw)
    )
    if result.get("success") and result.get("tweets") is not None:
        is_json = json_output or json_full
        if is_json and use_pagination:
            typer.echo(json.dumps({"tweets": result.get("tweets"), "nextCursor": result.get("nextCursor")}, indent=2))
        else:
            context.print_tweets(result.get("tweets"), json_output=is_json, empty_message="No tweets found in this list.")
        return

    typer.echo(f"{context.p('err')}Failed to fetch list timeline: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("following")
def following_command(
    ctx: typer.Context,
    user: str | None = typer.Option(None, "--user"),
    count: int = typer.Option(20, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms})
    user_id = user
    if not user_id:
        current = client.get_current_user()
        if not current.get("success") or not current.get("user"):
            typer.echo(f"{context.p('err')}Failed to get current user: {current.get('error') or 'Unknown error'}", err=True)
            raise typer.Exit(code=1)
        user_id = current["user"]["id"]

    result = client.get_following(user_id, count)
    if result.get("success") and result.get("users") is not None:
        if json_output:
            typer.echo(json.dumps(result.get("users"), indent=2))
            return
        users = result.get("users") or []
        if not users:
            typer.echo("No users found.")
            return
        for entry in users:
            typer.echo(f"@{entry['username']} ({entry['name']})")
            if entry.get("description"):
                desc = entry["description"]
                typer.echo(f"  {desc[:100]}{'...' if len(desc) > 100 else ''}")
            if entry.get("followersCount") is not None:
                typer.echo(f"  {context.p('info')}{entry['followersCount']} followers")
            typer.echo("-" * 50)
        return
    typer.echo(f"{context.p('err')}Failed to fetch following: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("followers")
def followers_command(
    ctx: typer.Context,
    user: str | None = typer.Option(None, "--user"),
    count: int = typer.Option(20, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms})
    user_id = user
    if not user_id:
        current = client.get_current_user()
        if not current.get("success") or not current.get("user"):
            typer.echo(f"{context.p('err')}Failed to get current user: {current.get('error') or 'Unknown error'}", err=True)
            raise typer.Exit(code=1)
        user_id = current["user"]["id"]

    result = client.get_followers(user_id, count)
    if result.get("success") and result.get("users") is not None:
        if json_output:
            typer.echo(json.dumps(result.get("users"), indent=2))
            return
        users = result.get("users") or []
        if not users:
            typer.echo("No users found.")
            return
        for entry in users:
            typer.echo(f"@{entry['username']} ({entry['name']})")
            if entry.get("description"):
                desc = entry["description"]
                typer.echo(f"  {desc[:100]}{'...' if len(desc) > 100 else ''}")
            if entry.get("followersCount") is not None:
                typer.echo(f"  {context.p('info')}{entry['followersCount']} followers")
            typer.echo("-" * 50)
        return
    typer.echo(f"{context.p('err')}Failed to fetch followers: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("likes")
def likes_command(
    ctx: typer.Context,
    count: int = typer.Option(20, "-n", "--count"),
    json_output: bool = typer.Option(False, "--json"),
    json_full: bool = typer.Option(False, "--json-full"),
) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    include_raw = json_full
    result = client.get_likes(count, include_raw=include_raw)
    if result.get("success") and result.get("tweets") is not None:
        context.print_tweets(result.get("tweets"), json_output=json_output or json_full, empty_message="No liked tweets found.")
        return
    typer.echo(f"{context.p('err')}Failed to fetch likes: {result.get('error')}", err=True)
    raise typer.Exit(code=1)


@app.command("whoami")
def whoami_command(ctx: typer.Context) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    timeout_ms = context.resolve_timeout_from_options(opts.get("timeout"))
    quote_depth = context.resolve_quote_depth_from_options(opts.get("quote_depth"))

    res = context.resolve_credentials_from_options(opts)
    for warning in res["warnings"]:
        typer.echo(f"{context.p('warn')}{warning}", err=True)
    cookies = res["cookies"]
    if not cookies.get("authToken") or not cookies.get("ct0"):
        typer.echo(f"{context.p('err')}Missing required credentials", err=True)
        raise typer.Exit(code=1)

    if cookies.get("source"):
        typer.echo(f"{context.l('source')}{cookies.get('source')}", err=True)

    client = TwitterClient({"cookies": cookies, "timeoutMs": timeout_ms, "quoteDepth": quote_depth})
    result = client.get_current_user()
    credential_source = cookies.get("source") or "env/auto-detected cookies"

    if result.get("success") and result.get("user"):
        user = result["user"]
        typer.echo(f"{context.l('user')}@{user['username']} ({user['name']})")
        typer.echo(f"{context.l('userId')}{user['id']}")
        typer.echo(f"{context.l('engine')}graphql")
        typer.echo(f"{context.l('credentials')}{credential_source}")
        return

    typer.echo(f"{context.p('err')}Failed to determine current user: {result.get('error') or 'Unknown error'}", err=True)
    raise typer.Exit(code=1)


@app.command("check")
def check_command(ctx: typer.Context) -> None:
    context = _build_context(ctx)
    opts = ctx.obj["global_opts"]
    res = context.resolve_credentials_from_options(opts)

    typer.echo(f"{context.p('info')}Credential check")
    typer.echo("-" * 40)

    cookies = res["cookies"]
    if cookies.get("authToken"):
        typer.echo(f"{context.p('ok')}auth_token: {cookies.get('authToken')[:10]}...")
    else:
        typer.echo(f"{context.p('err')}auth_token: not found")

    if cookies.get("ct0"):
        typer.echo(f"{context.p('ok')}ct0: {cookies.get('ct0')[:10]}...")
    else:
        typer.echo(f"{context.p('err')}ct0: not found")

    if cookies.get("source"):
        typer.echo(f"{context.l('source')}{cookies.get('source')}")

    if res["warnings"]:
        typer.echo(f"\n{context.p('warn')}Warnings:")
        for warning in res["warnings"]:
            typer.echo(f"   - {warning}")

    if cookies.get("authToken") and cookies.get("ct0"):
        typer.echo(f"\n{context.p('ok')}Ready to tweet!")
        return

    typer.echo(f"\n{context.p('err')}Missing credentials. Options:")
    typer.echo("   1. Login to x.com in Safari/Chrome/Firefox")
    typer.echo("   2. Set AUTH_TOKEN and CT0 environment variables")
    typer.echo("   3. Use --auth-token and --ct0 flags")
    raise typer.Exit(code=1)


@app.command("query-ids")
def query_ids_command(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
    fresh: bool = typer.Option(False, "--fresh"),
) -> None:
    context = _build_context(ctx)
    operations = [
        "CreateTweet",
        "CreateRetweet",
        "FavoriteTweet",
        "TweetDetail",
        "SearchTimeline",
        "UserArticlesTweets",
        "Bookmarks",
        "Following",
        "Followers",
        "Likes",
    ]

    if fresh:
        typer.echo(f"{context.p('info')}Refreshing GraphQL query IDs…", err=True)
        runtime_query_ids.refresh(operations, force=True)
        typer.echo(f"{context.p('info')}Refreshing feature overrides…", err=True)
        refresh_feature_overrides_cache()

    feature_snapshot = get_feature_overrides_snapshot()
    info = runtime_query_ids.get_snapshot_info()
    if not info:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "cached": False,
                        "cachePath": runtime_query_ids.cache_path,
                        "featuresPath": feature_snapshot.cachePath,
                        "features": feature_snapshot.overrides,
                    },
                    indent=2,
                )
            )
            return
        typer.echo(f"{context.p('warn')}No cached query IDs yet.")
        typer.echo(f"{context.p('info')}Run: laserbeak query-ids --fresh")
        typer.echo(f"features_path: {feature_snapshot.cachePath}")
        return

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "cached": True,
                    "cachePath": info.cachePath,
                    "fetchedAt": info.snapshot.fetchedAt,
                    "isFresh": info.isFresh,
                    "ageMs": info.ageMs,
                    "ids": info.snapshot.ids,
                    "discovery": info.snapshot.discovery,
                    "featuresPath": feature_snapshot.cachePath,
                    "features": feature_snapshot.overrides,
                },
                indent=2,
            )
        )
        return

    def count_feature_overrides(overrides: dict) -> int:
        count = 0
        if overrides.get("global"):
            count += len(overrides["global"])
        if overrides.get("sets"):
            for overrides_set in overrides["sets"].values():
                count += len(overrides_set)
        return count

    typer.echo(f"{context.p('ok')}GraphQL query IDs cached")
    typer.echo(f"path: {info.cachePath}")
    typer.echo(f"fetched_at: {info.snapshot.fetchedAt}")
    typer.echo(f"fresh: {'yes' if info.isFresh else 'no'}")
    typer.echo(f"ops: {len(info.snapshot.ids)}")
    typer.echo(f"features_path: {feature_snapshot.cachePath}")
    typer.echo(f"features: {count_feature_overrides(feature_snapshot.overrides)}")
