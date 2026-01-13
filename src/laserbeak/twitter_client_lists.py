from __future__ import annotations

import json
from urllib.parse import urlencode

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE
from .twitter_client_features import build_lists_features
from .twitter_client_utils import extract_cursor_from_instructions, parse_tweets_from_instructions


class TwitterClientListsMixin(TwitterClientBase):
    def _get_list_ownerships_query_ids(self) -> list[str]:
        primary = self._get_query_id("ListOwnerships")
        return list({primary, "wQcOSjSQ8NtgxIwvYl1lMg"})

    def _get_list_memberships_query_ids(self) -> list[str]:
        primary = self._get_query_id("ListMemberships")
        return list({primary, "BlEXXdARdSeL_0KyKHHvvg"})

    def _get_list_timeline_query_ids(self) -> list[str]:
        primary = self._get_query_id("ListLatestTweetsTimeline")
        return list({primary, "2TemLyqrMpTeAmysdbnVqw"})

    def get_owned_lists(self, count: int = 100) -> dict:
        user_result = self.get_current_user()
        if not user_result.get("success") or not user_result.get("user"):
            return {"success": False, "error": user_result.get("error") or "Could not determine current user"}

        variables = {
            "userId": user_result["user"]["id"],
            "count": count,
            "isListMembershipShown": True,
            "isListMemberTargetUserId": user_result["user"]["id"],
        }
        features = build_lists_features()
        params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

        def try_once():
            last_error = None
            had_404 = False
            for query_id in self._get_list_ownerships_query_ids():
                url = f"{TWITTER_API_BASE}/{query_id}/ListOwnerships?{params}"
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
                    lists = []
                    for instruction in instructions or []:
                        for entry in instruction.get("entries", []) or []:
                            list_result = ((entry.get("content") or {}).get("itemContent") or {}).get("list")
                            if list_result:
                                parsed = self._parse_list(list_result)
                                if parsed:
                                    lists.append(parsed)
                    return {"success": True, "lists": lists, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)
            return {"success": False, "error": last_error or "Unknown error fetching lists", "had404": had_404}

        first = try_once()
        if first.get("success"):
            return {"success": True, "lists": first.get("lists")}
        if first.get("had404"):
            self._refresh_query_ids()
            second = try_once()
            if second.get("success"):
                return {"success": True, "lists": second.get("lists")}
            return {"success": False, "error": second.get("error")}
        return {"success": False, "error": first.get("error")}

    def get_list_memberships(self, count: int = 100) -> dict:
        user_result = self.get_current_user()
        if not user_result.get("success") or not user_result.get("user"):
            return {"success": False, "error": user_result.get("error") or "Could not determine current user"}

        variables = {
            "userId": user_result["user"]["id"],
            "count": count,
            "isListMembershipShown": True,
            "isListMemberTargetUserId": user_result["user"]["id"],
        }
        features = build_lists_features()
        params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

        def try_once():
            last_error = None
            had_404 = False
            for query_id in self._get_list_memberships_query_ids():
                url = f"{TWITTER_API_BASE}/{query_id}/ListMemberships?{params}"
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
                    lists = []
                    for instruction in instructions or []:
                        for entry in instruction.get("entries", []) or []:
                            list_result = ((entry.get("content") or {}).get("itemContent") or {}).get("list")
                            if list_result:
                                parsed = self._parse_list(list_result)
                                if parsed:
                                    lists.append(parsed)
                    return {"success": True, "lists": lists, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)
            return {"success": False, "error": last_error or "Unknown error fetching lists", "had404": had_404}

        first = try_once()
        if first.get("success"):
            return {"success": True, "lists": first.get("lists")}
        if first.get("had404"):
            self._refresh_query_ids()
            second = try_once()
            if second.get("success"):
                return {"success": True, "lists": second.get("lists")}
            return {"success": False, "error": second.get("error")}
        return {"success": False, "error": first.get("error")}

    def _parse_list(self, list_result: dict) -> dict | None:
        if not list_result.get("id_str") or not list_result.get("name"):
            return None
        owner = (list_result.get("user_results") or {}).get("result")
        return {
            "id": list_result.get("id_str"),
            "name": list_result.get("name"),
            "description": list_result.get("description"),
            "memberCount": list_result.get("member_count"),
            "subscriberCount": list_result.get("subscriber_count"),
            "isPrivate": (list_result.get("mode") or "").lower() == "private",
            "createdAt": list_result.get("created_at"),
            "owner": {
                "id": (owner or {}).get("rest_id", ""),
                "username": ((owner or {}).get("legacy") or {}).get("screen_name", ""),
                "name": ((owner or {}).get("legacy") or {}).get("name", ""),
            }
            if owner
            else None,
        }

    def get_list_timeline(self, list_id: str, count: int = 20, *, include_raw: bool = False) -> dict:
        return self._get_list_timeline_paged(list_id, count, include_raw=include_raw)

    def get_all_list_timeline(
        self,
        list_id: str,
        *,
        include_raw: bool = False,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        return self._get_list_timeline_paged(list_id, float("inf"), include_raw=include_raw, max_pages=max_pages, cursor=cursor)

    def _get_list_timeline_paged(
        self,
        list_id: str,
        limit: float,
        *,
        include_raw: bool = False,
        max_pages: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        features = build_lists_features()
        page_size = 20
        seen: set[str] = set()
        tweets: list[dict] = []
        next_cursor = None
        pages_fetched = 0

        def fetch_page(page_count: int, page_cursor: str | None = None):
            last_error = None
            had_404 = False
            query_ids = self._get_list_timeline_query_ids()

            variables = {
                "listId": list_id,
                "count": page_count,
                "cursor": page_cursor,
                "includePromotedContent": False,
                "withClientEventToken": False,
                "withBirdwatchNotes": False,
                "withVoice": True,
            }
            if not page_cursor:
                variables.pop("cursor")

            params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})
            for query_id in query_ids:
                url = f"{TWITTER_API_BASE}/{query_id}/ListLatestTweetsTimeline?{params}"
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
                        .get("list", {})
                        .get("timeline", {})
                        .get("timeline", {})
                        .get("instructions")
                    )
                    page_tweets = parse_tweets_from_instructions(instructions, quote_depth=self.quote_depth, include_raw=include_raw)
                    cursor_value = extract_cursor_from_instructions(instructions)
                    return {"success": True, "tweets": page_tweets, "cursor": cursor_value, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)
            return {"success": False, "error": last_error or "Unknown error fetching list timeline", "had404": had_404}

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
