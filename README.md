# laserbeak 🐦 — fast X CLI for tweeting, replying, and reading

`laserbeak` is a fast X CLI for tweeting, replying, and reading via X/Twitter GraphQL (cookie auth).

## Disclaimer

This project uses X/Twitter’s **undocumented** web GraphQL API (and cookie auth). X can change endpoints, query IDs,
and anti-bot behavior at any time — **expect this to break without notice**.

## Install

With `uv`:

```bash
uv tool install laserbeak
```

From source:

```bash
uv sync --dev
uv run laserbeak whoami
```

## Quickstart

```bash
# Show the logged-in account
laserbeak whoami

# Discover command help
laserbeak help whoami

# Read a tweet (URL or ID)
laserbeak read https://x.com/user/status/1234567890123456789
laserbeak 1234567890123456789 --json

# Thread + replies
laserbeak thread https://x.com/user/status/1234567890123456789
laserbeak replies 1234567890123456789

# Search + mentions
laserbeak search "from:steipete" -n 5
laserbeak mentions -n 5
laserbeak mentions --user @steipete -n 5

# Bookmarks
laserbeak bookmarks -n 5
laserbeak bookmarks --folder-id 123456789123456789 -n 5 # https://x.com/i/bookmarks/<folder-id>
laserbeak bookmarks --all --json
laserbeak bookmarks --all --max-pages 2 --json
laserbeak unbookmark 1234567890123456789
laserbeak unbookmark https://x.com/user/status/1234567890123456789

# Likes
laserbeak likes -n 5

# Lists
laserbeak list-timeline 1234567890 -n 20
laserbeak list-timeline https://x.com/i/lists/1234567890 --all --json
laserbeak list-timeline 1234567890 --max-pages 3 --json

# Following (who you follow)
laserbeak following -n 20
laserbeak following --user 12345678 -n 10  # by user ID

# Followers (who follows you)
laserbeak followers -n 20
laserbeak followers --user 12345678 -n 10  # by user ID

# Refresh GraphQL query IDs cache (no rebuild)
laserbeak query-ids --fresh
```

## Library

`laserbeak` can be used as a library (same GraphQL client as the CLI):

```python
from laserbeak import TwitterClient, resolve_credentials

creds = resolve_credentials(cookie_source=["safari"])
client = TwitterClient({"cookies": creds["cookies"]})
result = client.search("from:steipete", 50)
```

## Commands

- `laserbeak tweet "<text>"` — post a new tweet.
- `laserbeak reply <tweet-id-or-url> "<text>"` — reply to a tweet using its ID or URL.
- `laserbeak help [command]` — show help (or help for a subcommand).
- `laserbeak query-ids [--fresh] [--json]` — inspect or refresh cached GraphQL query IDs.
- `laserbeak read <tweet-id-or-url> [--json]` — fetch tweet content as text or JSON.
- `laserbeak <tweet-id-or-url> [--json]` — shorthand for `read` when only a URL or ID is provided.
- `laserbeak replies <tweet-id-or-url> [--json]` — list replies to a tweet.
- `laserbeak thread <tweet-id-or-url> [--json]` — show the full conversation thread.
- `laserbeak search "<query>" [-n count] [--json]` — search for tweets matching a query.
- `laserbeak mentions [-n count] [--user @handle] [--json]` — find tweets mentioning a user (defaults to the authenticated user).
- `laserbeak bookmarks [-n count] [--folder-id id] [--all] [--max-pages n] [--json]` — list your bookmarked tweets (or a specific bookmark folder); `--max-pages` requires `--all`.
- `laserbeak unbookmark <tweet-id-or-url...>` — remove one or more bookmarks by tweet ID or URL.
- `laserbeak likes [-n count] [--json]` — list your liked tweets.
- `laserbeak list-timeline <list-id-or-url> [-n count] [--all] [--max-pages n] [--cursor string] [--json]` — get tweets from a list timeline; `--max-pages` implies `--all`.
- `laserbeak following [--user <userId>] [-n count] [--json]` — list users that you (or another user) follow.
- `laserbeak followers [--user <userId>] [-n count] [--json]` — list users that follow you (or another user).
- `laserbeak whoami` — print which Twitter account your cookies belong to.
- `laserbeak check` — show which credentials are available and where they were sourced from.

Global options:
- `--auth-token <token>`: set the `auth_token` cookie manually.
- `--ct0 <token>`: set the `ct0` cookie manually.
- `--cookie-source <safari|chrome|firefox>`: choose browser cookie source (repeatable; order matters).
- `--chrome-profile <name>`: Chrome profile for cookie extraction.
- `--firefox-profile <name>`: Firefox profile for cookie extraction.
- `--cookie-timeout <ms>`: cookie extraction timeout for keychain/OS helpers (milliseconds).
- `--timeout <ms>`: abort requests after the given timeout (milliseconds).
- `--quote-depth <n>`: max quoted tweet depth in JSON output (default: 1; 0 disables).
- `--plain`: stable output (no emoji, no color).
- `--no-emoji`: disable emoji output.
- `--no-color`: disable ANSI colors (or set `NO_COLOR=1`).
- `--media <path>`: attach media file (repeatable, up to 4 images or 1 video).
- `--alt <text>`: alt text for the corresponding `--media` (repeatable).

## Authentication (GraphQL)

GraphQL mode uses your existing X/Twitter web session (no password prompt). It sends requests to internal
X endpoints and authenticates via cookies (`auth_token`, `ct0`).

Write operations:
- `tweet`/`reply` primarily use GraphQL (`CreateTweet`).
- If GraphQL returns error `226` (“automated request”), `laserbeak` falls back to the legacy `statuses/update.json` endpoint.

`laserbeak` resolves credentials in this order:

1. CLI flags: `--auth-token`, `--ct0`
2. Environment variables: `AUTH_TOKEN`, `CT0` (fallback: `TWITTER_AUTH_TOKEN`, `TWITTER_CT0`)
3. Browser cookies via `browser-cookie3` (override via `--cookie-source` order)

## Config (JSON5)

Config precedence: CLI flags > env vars > project config > global config.

- Global: `~/.config/laserbeak/config.json5`
- Project: `./.laserbeakrc.json5`

Example `~/.config/laserbeak/config.json5`:

```json5
{
  // Cookie source order for browser extraction (string or array)
  cookieSource: ["firefox", "safari"],
  firefoxProfile: "default-release",
  timeoutMs: 15000,
  quoteDepth: 1,
}
```

## Development

```bash
uv venv
uv sync --dev
uv run pytest
```
