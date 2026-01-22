from __future__ import annotations

import json
import random
import time
from urllib.parse import urlencode

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE
from .twitter_client_features import build_bookmarks_features, build_likes_features
from .twitter_client_utils import extract_cursor_from_instructions, parse_tweets_from_instructions


class TwitterClientTimelinesMixin(TwitterClientBase):
    def _get_bookmarks_query_ids(self) -> list[str]:
        primary = self._get_query_id("Bookmarks")
        return list({primary, "RV1g3b8n_SGOHwkqKYSCFw", "tmd4ifV8RHltzn8ymGg1aw"})

    def _get_bookmark_folder_query_ids(self) -> list[str]:
        primary = self._get_query_id("BookmarkFolderTimeline")
        return list({primary, "KJIQpsvxrTfRIlbaRIySHQ"})

    def _get_likes_query_ids(self) -> list[str]:
        primary = self._get_query_id("Likes")
        return list({primary, "JR2gceKucIKcVNB_9JkhsA"})

    def get_bookmarks(self, count: int = 20, *, include_raw: bool = False) -> dict:
        return self._get_bookmarks_paged(count, include_raw=include_raw)

    def get_all_bookmarks(self, *, include_raw: bool = False, max_pages: int | None = None, cursor: str | None = None) -> dict:
        return self._get_bookmarks_paged(float("inf"), include_raw=include_raw, max_pages=max_pages, cursor=cursor)

    def get_likes(self, count: int = 20, *, include_raw: bool = False) -> dict:
        user_result = self.get_current_user()
        if not user_result.get("success") or not user_result.get("user"):
            return {"success": False, "error": user_result.get("error") or "Could not determine current user"}

        variables = {
            "userId": user_result["user"]["id"],
            "count": count,
            "includePromotedContent": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
        }
        features = build_likes_features()
        params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

        def try_once():
            last_error = None
            had_404 = False
            for query_id in self._get_likes_query_ids():
                url = f"{TWITTER_API_BASE}/{query_id}/Likes?{params}"
                try:
                    response = self._request("GET", url, headers=self._get_headers())
                    if response.status_code == 404:
                        had_404 = True
                        last_error = f"HTTP {response.status_code}"
                        continue
                    if response.status_code >= 400:
                        return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}", "had404": had_404}

                    data = response.json()
                    if data.get("errors"):
                        return {
                            "success": False,
                            "error": ", ".join(err.get("message", "") for err in data.get("errors", [])),
                            "had404": had_404,
                        }

                    instructions = (
                        (data.get("data") or {})
                        .get("user", {})
                        .get("result", {})
                        .get("timeline", {})
                        .get("timeline", {})
                        .get("instructions")
                    )
                    tweets = parse_tweets_from_instructions(instructions, quote_depth=self.quote_depth, include_raw=include_raw)
                    return {"success": True, "tweets": tweets, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)
            return {"success": False, "error": last_error or "Unknown error fetching likes", "had404": had_404}

        first = try_once()
        if first.get("success"):
            return {"success": True, "tweets": first.get("tweets")}
        if first.get("had404"):
            self._refresh_query_ids()
            second = try_once()
            if second.get("success"):
                return {"success": True, "tweets": second.get("tweets")}
            return {"success": False, "error": second.get("error")}
        return {"success": False, "error": first.get("error")}

    def get_bookmark_folder_timeline(self, folder_id: str, count: int = 20, *, include_raw: bool = False) -> dict:
        return self._get_bookmark_folder_timeline_paged(folder_id, count, include_raw=include_raw)

    def get_all_bookmark_folder_timeline(
        self,
        folder_id: str,
        *,
        include_raw: bool = False,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        return self._get_bookmark_folder_timeline_paged(
            folder_id, float("inf"), include_raw=include_raw, max_pages=max_pages, cursor=cursor
        )

    def _get_bookmarks_paged(
        self,
        limit: float,
        *,
        include_raw: bool = False,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        features = build_bookmarks_features()
        page_size = 20
        seen: set[str] = set()
        tweets: list[dict] = []
        next_cursor = None
        pages_fetched = 0

        def fetch_page(page_count: int, page_cursor: str | None = None):
            last_error = None
            had_404 = False
            query_ids = self._get_bookmarks_query_ids()
            variables = {
                "count": page_count,
                "includePromotedContent": False,
                "withDownvotePerspective": False,
                "withReactionsMetadata": False,
                "withReactionsPerspective": False,
                **({"cursor": page_cursor} if page_cursor else {}),
            }
            params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

            for query_id in query_ids:
                url = f"{TWITTER_API_BASE}/{query_id}/Bookmarks?{params}"
                try:
                    response = self._fetch_with_retry(url)
                    if response.status_code == 404:
                        had_404 = True
                        last_error = f"HTTP {response.status_code}"
                        continue
                    if response.status_code >= 400:
                        return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}", "had404": had_404}

                    data = response.json()
                    instructions = (
                        (data.get("data") or {})
                        .get("bookmark_timeline_v2", {})
                        .get("timeline", {})
                        .get("instructions")
                    )
                    page_tweets = parse_tweets_from_instructions(instructions, quote_depth=self.quote_depth, include_raw=include_raw)
                    cursor_value = extract_cursor_from_instructions(instructions)
                    if data.get("errors") and not instructions:
                        last_error = ", ".join(err.get("message", "") for err in data.get("errors", []))
                        continue

                    return {"success": True, "tweets": page_tweets, "cursor": cursor_value, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)

            return {"success": False, "error": last_error or "Unknown error fetching bookmarks", "had404": had_404}

        def fetch_with_refresh(page_count: int, page_cursor: str | None = None):
            first = fetch_page(page_count, page_cursor)
            if first.get("success"):
                return first
            if first.get("had404"):
                self._refresh_query_ids()
                second = fetch_page(page_count, page_cursor)
                if second.get("success"):
                    return second
                return {"success": False, "error": second.get("error")}
            return {"success": False, "error": first.get("error")}

        unlimited = limit == float("inf")
        while unlimited or len(tweets) < limit:
            page_count = page_size if unlimited else min(page_size, int(limit - len(tweets)))
            page = fetch_with_refresh(page_count, cursor)
            if not page.get("success"):
                return {"success": False, "error": page.get("error")}
            pages_fetched += 1

            for tweet in page.get("tweets") or []:
                if tweet.get("id") in seen:
                    continue
                seen.add(tweet.get("id"))
                tweets.append(tweet)
                if not unlimited and len(tweets) >= limit:
                    break

            page_cursor = page.get("cursor")
            if not page_cursor or page_cursor == cursor or not page.get("tweets"):
                next_cursor = None
                break
            if max_pages and pages_fetched >= max_pages:
                next_cursor = page_cursor
                break
            cursor = page_cursor
            next_cursor = page_cursor

        return {"success": True, "tweets": tweets, "nextCursor": next_cursor}

    def _get_bookmark_folder_timeline_paged(
        self,
        folder_id: str,
        limit: float,
        *,
        include_raw: bool = False,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        features = build_bookmarks_features()
        page_size = 20
        seen: set[str] = set()
        tweets: list[dict] = []
        next_cursor = None
        pages_fetched = 0

        def build_variables(page_count: int, page_cursor: str | None, include_count: bool):
            variables = {
                "bookmark_collection_id": folder_id,
                "includePromotedContent": True,
                **({"cursor": page_cursor} if page_cursor else {}),
            }
            if include_count:
                variables["count"] = page_count
            return variables

        def fetch_page(page_count: int, page_cursor: str | None = None):
            last_error = None
            had_404 = False
            query_ids = self._get_bookmark_folder_query_ids()

            def try_once(variables: dict):
                nonlocal had_404, last_error
                params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
                for query_id in query_ids:
                    url = f"{TWITTER_API_BASE}/{query_id}/BookmarkFolderTimeline?{params}"
                    try:
                        response = self._fetch_with_retry(url)
                        if response.status_code == 404:
                            had_404 = True
                            last_error = f"HTTP {response.status_code}"
                            continue
                        if response.status_code >= 400:
                            return {
                                "success": False,
                                "error": f"HTTP {response.status_code}: {response.text[:200]}",
                                "had404": had_404,
                            }
                        data = response.json()
                        instructions = (
                            (data.get("data") or {})
                            .get("bookmark_timeline_v2", {})
                            .get("timeline", {})
                            .get("instructions")
                        )
                        page_tweets = parse_tweets_from_instructions(
                            instructions, quote_depth=self.quote_depth, include_raw=include_raw
                        )
                        cursor_value = extract_cursor_from_instructions(instructions)
                        return {"success": True, "tweets": page_tweets, "cursor": cursor_value, "had404": had_404}
                    except Exception as exc:
                        last_error = str(exc)
                return {"success": False, "error": last_error or "Unknown error", "had404": had_404}

            with_count = try_once(build_variables(page_count, page_cursor, True))
            if with_count.get("success"):
                return with_count
            if with_count.get("error") and "rate limit" in str(with_count.get("error")).lower():
                return with_count
            return try_once(build_variables(page_count, page_cursor, False))

        def fetch_with_refresh(page_count: int, page_cursor: str | None = None):
            first = fetch_page(page_count, page_cursor)
            if first.get("success"):
                return first
            if first.get("had404"):
                self._refresh_query_ids()
                second = fetch_page(page_count, page_cursor)
                if second.get("success"):
                    return second
                return {"success": False, "error": second.get("error")}
            return {"success": False, "error": first.get("error")}

        unlimited = limit == float("inf")
        while unlimited or len(tweets) < limit:
            page_count = page_size if unlimited else min(page_size, int(limit - len(tweets)))
            page = fetch_with_refresh(page_count, cursor)
            if not page.get("success"):
                return {"success": False, "error": page.get("error")}
            pages_fetched += 1

            for tweet in page.get("tweets") or []:
                if tweet.get("id") in seen:
                    continue
                seen.add(tweet.get("id"))
                tweets.append(tweet)
                if not unlimited and len(tweets) >= limit:
                    break

            page_cursor = page.get("cursor")
            if not page_cursor or page_cursor == cursor or not page.get("tweets"):
                next_cursor = None
                break
            if max_pages and pages_fetched >= max_pages:
                next_cursor = page_cursor
                break
            cursor = page_cursor
            next_cursor = page_cursor

        return {"success": True, "tweets": tweets, "nextCursor": next_cursor}

    def _fetch_with_retry(self, url: str):
        max_retries = 2
        base_delay_ms = 500
        retryable = {429, 500, 502, 503, 504}

        for attempt in range(max_retries + 1):
            response = self._request("GET", url, headers=self._get_headers())
            if response.status_code not in retryable or attempt == max_retries:
                return response

            retry_after = response.headers.get("retry-after")
            retry_after_ms = int(retry_after) * 1000 if retry_after and retry_after.isdigit() else None
            backoff_ms = retry_after_ms or base_delay_ms * (2**attempt) + int(random.random() * base_delay_ms)
            time.sleep(backoff_ms / 1000)

        return self._request("GET", url, headers=self._get_headers())
