from __future__ import annotations

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE, TWITTER_GRAPHQL_POST_URL


class TwitterClientBookmarksMixin(TwitterClientBase):
    def unbookmark(self, tweet_id: str) -> dict:
        variables = {"tweet_id": tweet_id}
        query_id = self._get_query_id("DeleteBookmark")
        url_with_operation = f"{TWITTER_API_BASE}/{query_id}/DeleteBookmark"

        def build_body():
            return {"variables": variables, "queryId": query_id}

        def build_headers():
            return {**self._get_headers(), "referer": f"https://x.com/i/status/{tweet_id}"}

        def parse_response(response):
            if response.status_code >= 400:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}
            data = response.json()
            if data.get("errors"):
                return {"success": False, "error": ", ".join(err.get("message", "") for err in data.get("errors", []))}
            return {"success": True}

        try:
            response = self._request("POST", url_with_operation, headers=build_headers(), json_data=build_body())
            if response.status_code == 404:
                self._refresh_query_ids()
                query_id = self._get_query_id("DeleteBookmark")
                url_with_operation = f"{TWITTER_API_BASE}/{query_id}/DeleteBookmark"
                response = self._request("POST", url_with_operation, headers=build_headers(), json_data=build_body())

                if response.status_code == 404:
                    retry = self._request("POST", TWITTER_GRAPHQL_POST_URL, headers=build_headers(), json_data=build_body())
                    return parse_response(retry)

            return parse_response(response)
        except Exception as exc:
            return {"success": False, "error": str(exc)}
