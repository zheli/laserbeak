from __future__ import annotations

import os
from collections.abc import Iterable

import browser_cookie3

from .types import CookieExtractionResult, CookieSource, TwitterCookies

TWITTER_COOKIE_NAMES = ("auth_token", "ct0")
TWITTER_DOMAINS = ("x.com", "twitter.com")
DEFAULT_COOKIE_TIMEOUT_MS = 30_000


def _normalize_value(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _cookie_header(auth_token: str, ct0: str) -> str:
    return f"auth_token={auth_token}; ct0={ct0}"


def _build_empty() -> TwitterCookies:
    return {"authToken": None, "ct0": None, "cookieHeader": None, "source": None}


def _read_env_cookie(cookies: TwitterCookies, keys: Iterable[str], field: str) -> None:
    if cookies.get(field):
        return
    for key in keys:
        value = _normalize_value(os.environ.get(key))
        if not value:
            continue
        cookies[field] = value
        if not cookies.get("source"):
            cookies["source"] = f"env {key}"
        break


def _resolve_sources(cookie_source: CookieSource | list[CookieSource] | None) -> list[CookieSource]:
    if isinstance(cookie_source, list):
        return cookie_source
    if cookie_source:
        return [cookie_source]
    return ["safari", "chrome", "firefox"]


def _label_for_source(source: CookieSource, profile: str | None) -> str:
    if source == "safari":
        return "Safari"
    if source == "chrome":
        return f"Chrome profile \"{profile}\"" if profile else "Chrome default profile"
    return f"Firefox profile \"{profile}\"" if profile else "Firefox default profile"


def _pick_cookie_value(cookies: list[dict], name: str) -> str | None:
    matches = [c for c in cookies if c.get("name") == name and isinstance(c.get("value"), str)]
    if not matches:
        return None

    preferred = next((c for c in matches if str(c.get("domain", "")).endswith("x.com")), None)
    if preferred and preferred.get("value"):
        return preferred["value"]

    fallback = next((c for c in matches if str(c.get("domain", "")).endswith("twitter.com")), None)
    if fallback and fallback.get("value"):
        return fallback["value"]

    return matches[0].get("value")


def _cookiejar_to_list(jar) -> list[dict]:
    cookies: list[dict] = []
    for cookie in jar:
        cookies.append({"name": cookie.name, "value": cookie.value, "domain": cookie.domain})
    return cookies


def _load_cookiejar(source: CookieSource, profile: str | None, domain: str):
    if source == "chrome":
        return browser_cookie3.chrome(domain_name=domain, chrome_profile=profile)
    if source == "firefox":
        return browser_cookie3.firefox(domain_name=domain, profile=profile)
    if source == "safari":
        return browser_cookie3.safari(domain_name=domain)
    raise ValueError(f"Unknown cookie source: {source}")


def _read_twitter_cookies_from_browser(
    *,
    source: CookieSource,
    chrome_profile: str | None = None,
    firefox_profile: str | None = None,
    cookie_timeout_ms: int | None = None,
) -> CookieExtractionResult:
    warnings: list[str] = []
    out = _build_empty()

    profile = chrome_profile if source == "chrome" else firefox_profile

    cookies: list[dict] = []
    for domain in TWITTER_DOMAINS:
        try:
            jar = _load_cookiejar(source, profile, domain)
            cookies.extend(_cookiejar_to_list(jar))
        except Exception as exc:
            warnings.append(str(exc))

    auth_token = _pick_cookie_value(cookies, "auth_token")
    ct0 = _pick_cookie_value(cookies, "ct0")
    if auth_token:
        out["authToken"] = auth_token
    if ct0:
        out["ct0"] = ct0

    if out.get("authToken") and out.get("ct0"):
        out["cookieHeader"] = _cookie_header(out["authToken"], out["ct0"])  # type: ignore[arg-type]
        out["source"] = _label_for_source(source, profile)
        return {"cookies": out, "warnings": warnings}

    if source == "safari":
        warnings.append("No Twitter cookies found in Safari. Make sure you are logged into x.com in Safari.")
    elif source == "chrome":
        warnings.append("No Twitter cookies found in Chrome. Make sure you are logged into x.com in Chrome.")
    else:
        warnings.append(
            "No Twitter cookies found in Firefox. Make sure you are logged into x.com in Firefox and the profile exists."
        )

    return {"cookies": out, "warnings": warnings}


def extract_cookies_from_safari() -> CookieExtractionResult:
    return _read_twitter_cookies_from_browser(source="safari")


def extract_cookies_from_chrome(profile: str | None = None) -> CookieExtractionResult:
    return _read_twitter_cookies_from_browser(source="chrome", chrome_profile=profile)


def extract_cookies_from_firefox(profile: str | None = None) -> CookieExtractionResult:
    return _read_twitter_cookies_from_browser(source="firefox", firefox_profile=profile)


def resolve_credentials(
    *,
    auth_token: str | None = None,
    ct0: str | None = None,
    cookie_source: CookieSource | list[CookieSource] | None = None,
    chrome_profile: str | None = None,
    firefox_profile: str | None = None,
    cookie_timeout_ms: int | None = None,
) -> CookieExtractionResult:
    warnings: list[str] = []
    cookies = _build_empty()

    if auth_token:
        cookies["authToken"] = auth_token
        cookies["source"] = "CLI argument"
    if ct0:
        cookies["ct0"] = ct0
        if not cookies.get("source"):
            cookies["source"] = "CLI argument"

    _read_env_cookie(cookies, ["AUTH_TOKEN", "TWITTER_AUTH_TOKEN"], "authToken")
    _read_env_cookie(cookies, ["CT0", "TWITTER_CT0"], "ct0")

    if cookies.get("authToken") and cookies.get("ct0"):
        cookies["cookieHeader"] = _cookie_header(cookies["authToken"], cookies["ct0"])  # type: ignore[arg-type]
        return {"cookies": cookies, "warnings": warnings}

    sources_to_try = _resolve_sources(cookie_source)
    for source in sources_to_try:
        res = _read_twitter_cookies_from_browser(
            source=source,
            chrome_profile=chrome_profile,
            firefox_profile=firefox_profile,
            cookie_timeout_ms=cookie_timeout_ms,
        )
        warnings.extend(res["warnings"])
        if res["cookies"].get("authToken") and res["cookies"].get("ct0"):
            return res

    if not cookies.get("authToken"):
        warnings.append(
            "Missing auth_token - provide via --auth-token, AUTH_TOKEN env var, or login to x.com in Safari/Chrome/Firefox"
        )
    if not cookies.get("ct0"):
        warnings.append(
            "Missing ct0 - provide via --ct0, CT0 env var, or login to x.com in Safari/Chrome/Firefox"
        )
    if cookies.get("authToken") and cookies.get("ct0"):
        cookies["cookieHeader"] = _cookie_header(cookies["authToken"], cookies["ct0"])  # type: ignore[arg-type]

    return {"cookies": cookies, "warnings": warnings}
