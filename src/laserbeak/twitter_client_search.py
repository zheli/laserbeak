from __future__ import annotations

import json
from urllib.parse import urlencode

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE
from .twitter_client_features import build_search_features
from .twitter_client_utils import extract_cursor_from_instructions, parse_tweets_from_instructions


class TwitterClientSearchMixin(TwitterClientBase):
    def search(self, query: str, count: int = 20, *, include_raw: bool = False) -> dict:
        features = build_search_features()
        page_size = 20
        seen: set[str] = set()
        tweets: list[dict] = []
        cursor: str | None = None

        def fetch_page(page_count: int, page_cursor: str | None = None):
            last_error = None
            had_404 = False
            query_ids = self._get_search_timeline_query_ids()

            for query_id in query_ids:
                variables = {
                    "rawQuery": query,
                    "count": page_count,
                    "querySource": "typed_query",
                    "product": "Latest",
                    **({"cursor": page_cursor} if page_cursor else {}),
                }

                params = urlencode({"variables": json.dumps(variables)})
                url = f"{TWITTER_API_BASE}/{query_id}/SearchTimeline?{params}"

                try:
                    response = self._request(
                        "POST",
                        url,
                        headers=self._get_headers(),
                        data=None,
                        json_data={"features": features, "queryId": query_id},
                    )
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
                        .get("search_by_raw_query", {})
                        .get("search_timeline", {})
                        .get("timeline", {})
                        .get("instructions")
                    )
                    page_tweets = parse_tweets_from_instructions(
                        instructions,
                        quote_depth=self.quote_depth,
                        include_raw=include_raw,
                    )
                    next_cursor = extract_cursor_from_instructions(instructions)

                    return {"success": True, "tweets": page_tweets, "cursor": next_cursor, "had404": had_404}
                except Exception as exc:
                    last_error = str(exc)

            return {"success": False, "error": last_error or "Unknown error fetching search results", "had404": had_404}

        def fetch_with_refresh(page_count: int, page_cursor: str | None = None):
            first_attempt = fetch_page(page_count, page_cursor)
            if first_attempt.get("success"):
                return first_attempt
            if first_attempt.get("had404"):
                self._refresh_query_ids()
                second_attempt = fetch_page(page_count, page_cursor)
                if second_attempt.get("success"):
                    return second_attempt
                return {"success": False, "error": second_attempt.get("error")}
            return {"success": False, "error": first_attempt.get("error")}

        while len(tweets) < count:
            page_count = min(page_size, count - len(tweets))
            page = fetch_with_refresh(page_count, cursor)
            if not page.get("success"):
                return {"success": False, "error": page.get("error")}

            for tweet in page.get("tweets", []) or []:
                if tweet.get("id") in seen:
                    continue
                seen.add(tweet["id"])
                tweets.append(tweet)
                if len(tweets) >= count:
                    break

            if not page.get("cursor") or page.get("cursor") == cursor or not page.get("tweets"):
                break
            cursor = page.get("cursor")

        return {"success": True, "tweets": tweets}
