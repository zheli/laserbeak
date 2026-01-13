from __future__ import annotations

import os
import secrets
import uuid
from typing import Any

import httpx

from .runtime_query_ids import runtime_query_ids
from .twitter_client_constants import QUERY_IDS, TARGET_QUERY_ID_OPERATIONS
from .types import CurrentUserResult, TwitterClientOptions
from .twitter_client_utils import normalize_quote_depth


class TwitterClientBase:
    def __init__(self, options: TwitterClientOptions):
        cookies = options.get("cookies")
        if not cookies or not cookies.get("authToken") or not cookies.get("ct0"):
            raise ValueError("Both authToken and ct0 cookies are required")
        self.auth_token = cookies["authToken"]
        self.ct0 = cookies["ct0"]
        self.cookie_header = cookies.get("cookieHeader") or f"auth_token={self.auth_token}; ct0={self.ct0}"
        self.user_agent = options.get(
            "userAgent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        self.timeout_ms = options.get("timeoutMs")
        self.quote_depth = normalize_quote_depth(options.get("quoteDepth"))
        self.client_uuid = str(uuid.uuid4())
        self.client_device_id = str(uuid.uuid4())
        self.client_user_id: str | None = None

    def get_current_user(self) -> CurrentUserResult:
        raise NotImplementedError

    def _get_query_id(self, operation_name: str) -> str:
        cached = runtime_query_ids.get_query_id(operation_name)
        return cached or QUERY_IDS[operation_name]

    def _refresh_query_ids(self) -> None:
        if os.environ.get("NODE_ENV") == "test":
            return
        try:
            runtime_query_ids.refresh(TARGET_QUERY_ID_OPERATIONS, force=True)
        except Exception:
            return

    def _get_tweet_detail_query_ids(self) -> list[str]:
        primary = self._get_query_id("TweetDetail")
        return list({primary, "97JF30KziU00483E_8elBA", "aFvUsJm2c-oDkJV75blV6g"})

    def _get_search_timeline_query_ids(self) -> list[str]:
        primary = self._get_query_id("SearchTimeline")
        return list({primary, "M1jEez78PEfVfbQLvlWMvQ", "5h0kNbk3ii97rmfY6CdgAA", "Tp1sewRU1AsZpBWhqCZicQ"})

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: Any = None,
        json_data: Any = None,
        files: Any = None,
    ):
        timeout = None
        if self.timeout_ms and self.timeout_ms > 0:
            timeout = self.timeout_ms / 1000
        return httpx.request(method, url, headers=headers, data=data, json=json_data, files=files, timeout=timeout)

    def _get_headers(self) -> dict[str, str]:
        return self._get_json_headers()

    def _create_transaction_id(self) -> str:
        return secrets.token_hex(16)

    def _get_base_headers(self) -> dict[str, str]:
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": (
                "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
                "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
            ),
            "x-csrf-token": self.ct0,
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-active-user": "yes",
            "x-twitter-client-language": "en",
            "x-client-uuid": self.client_uuid,
            "x-twitter-client-deviceid": self.client_device_id,
            "x-client-transaction-id": self._create_transaction_id(),
            "cookie": self.cookie_header,
            "user-agent": self.user_agent,
            "origin": "https://x.com",
            "referer": "https://x.com/",
        }
        if self.client_user_id:
            headers["x-twitter-client-user-id"] = self.client_user_id
        return headers

    def _get_json_headers(self) -> dict[str, str]:
        headers = self._get_base_headers()
        headers["content-type"] = "application/json"
        return headers

    def _get_upload_headers(self) -> dict[str, str]:
        return self._get_base_headers()

    def _ensure_client_user_id(self) -> None:
        if os.environ.get("NODE_ENV") == "test":
            return
        if self.client_user_id:
            return
        result = self.get_current_user()
        if result.get("success") and result.get("user") and result["user"].get("id"):
            self.client_user_id = result["user"]["id"]
