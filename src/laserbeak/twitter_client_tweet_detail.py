from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE
from .twitter_client_features import build_article_features, build_article_field_toggles, build_tweet_detail_features
from .twitter_client_utils import (
    extract_article_text,
    find_tweet_in_instructions,
    first_text,
    map_tweet_result,
    parse_tweets_from_instructions,
)


class TwitterClientTweetDetailMixin(TwitterClientBase):
    def _fetch_user_article_plain_text(self, user_id: str, tweet_id: str) -> dict:
        variables = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": True,
            "withVoice": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withCommunity": True,
            "withSafetyModeUserFields": True,
            "withSuperFollowsUserFields": True,
            "withDownvotePerspective": False,
            "withReactionsMetadata": False,
            "withReactionsPerspective": False,
            "withSuperFollowsTweetFields": True,
            "withSuperFollowsReplyCount": False,
            "withClientEventToken": False,
        }

        params = urlencode(
            {
                "variables": json.dumps(variables),
                "features": json.dumps(build_article_features()),
                "fieldToggles": json.dumps(build_article_field_toggles()),
            }
        )

        query_id = self._get_query_id("UserArticlesTweets")
        url = f"{TWITTER_API_BASE}/{query_id}/UserArticlesTweets?{params}"

        try:
            response = self._request("GET", url, headers=self._get_headers())
            if response.status_code >= 400:
                return {}

            data = response.json()
            instructions = (
                (data.get("data") or {})
                .get("user", {})
                .get("result", {})
                .get("timeline", {})
                .get("timeline", {})
                .get("instructions")
                or []
            )
            for instruction in instructions:
                for entry in instruction.get("entries", []) or []:
                    result = ((entry.get("content") or {}).get("itemContent") or {}).get("tweet_results", {}).get(
                        "result"
                    )
                    if not result or result.get("rest_id") != tweet_id:
                        continue
                    article_result = (result.get("article") or {}).get("article_results", {}).get("result")
                    title = first_text((article_result or {}).get("title"), (result.get("article") or {}).get("title"))
                    plain_text = first_text(
                        (article_result or {}).get("plain_text"), (result.get("article") or {}).get("plain_text")
                    )
                    return {"title": title, "plainText": plain_text}
        except Exception:
            return {}

        return {}

    def _fetch_tweet_detail(self, tweet_id: str) -> dict:
        variables = {
            "focalTweetId": tweet_id,
            "with_rux_injections": False,
            "rankingMode": "Relevance",
            "includePromotedContent": True,
            "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True,
            "withVoice": True,
        }

        features = {
            **build_tweet_detail_features(),
            "articles_preview_enabled": True,
            "articles_rest_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "rweb_video_timestamps_enabled": True,
        }

        params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

        def parse_response(response):
            if response.status_code >= 400:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}
            data = response.json()
            if data.get("errors"):
                return {"success": False, "error": ", ".join(err.get("message", "") for err in data.get("errors", []))}
            return {"success": True, "data": data.get("data") or {}}

        try:
            last_error = None
            had_404 = False

            def try_once():
                nonlocal last_error, had_404
                query_ids = self._get_tweet_detail_query_ids()
                for query_id in query_ids:
                    url = f"{TWITTER_API_BASE}/{query_id}/TweetDetail?{params}"
                    response = self._request("GET", url, headers=self._get_headers())
                    if response.status_code != 404:
                        return parse_response(response)
                    had_404 = True

                    post_response = self._request(
                        "POST",
                        f"{TWITTER_API_BASE}/{query_id}/TweetDetail",
                        headers=self._get_headers(),
                        json_data={"variables": variables, "features": features, "queryId": query_id},
                    )
                    if post_response.status_code != 404:
                        return parse_response(post_response)

                    last_error = "HTTP 404"
                return {"success": False, "error": last_error or "Unknown error fetching tweet detail"}

            first_attempt = try_once()
            if first_attempt.get("success"):
                return first_attempt
            if had_404:
                self._refresh_query_ids()
                return try_once()
            return first_attempt
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_tweet(self, tweet_id: str, *, include_raw: bool = False) -> dict:
        response = self._fetch_tweet_detail(tweet_id)
        if not response.get("success"):
            return response

        data = response.get("data", {})
        tweet_result = (data.get("tweetResult") or {}).get("result")
        if not tweet_result:
            tweet_result = find_tweet_in_instructions(
                (data.get("threaded_conversation_with_injections_v2") or {}).get("instructions"),
                tweet_id,
            )

        mapped = map_tweet_result(tweet_result, quote_depth=self.quote_depth, include_raw=include_raw)
        if mapped:
            if tweet_result and tweet_result.get("article"):
                title = first_text(
                    ((tweet_result.get("article") or {}).get("article_results") or {}).get("result", {}).get("title"),
                    (tweet_result.get("article") or {}).get("title"),
                )
                article_text = extract_article_text(tweet_result)
                if title and (not article_text or article_text.strip() == title.strip()):
                    user_id = (((tweet_result.get("core") or {}).get("user_results") or {}).get("result") or {}).get(
                        "rest_id"
                    )
                    if user_id:
                        fallback = self._fetch_user_article_plain_text(user_id, tweet_id)
                        if fallback.get("plainText"):
                            if fallback.get("title"):
                                mapped["text"] = f"{fallback['title']}\n\n{fallback['plainText']}"
                            else:
                                mapped["text"] = fallback["plainText"]
            return {"success": True, "tweet": mapped}

        return {"success": False, "error": "Tweet not found in response"}

    def get_replies(self, tweet_id: str, *, include_raw: bool = False) -> dict:
        response = self._fetch_tweet_detail(tweet_id)
        if not response.get("success"):
            return response
        instructions = (response.get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions"))
        tweets = parse_tweets_from_instructions(instructions, quote_depth=self.quote_depth, include_raw=include_raw)
        replies = [tweet for tweet in tweets if tweet.get("inReplyToStatusId") == tweet_id]
        return {"success": True, "tweets": replies}

    def get_thread(self, tweet_id: str, *, include_raw: bool = False) -> dict:
        response = self._fetch_tweet_detail(tweet_id)
        if not response.get("success"):
            return response
        instructions = (response.get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions"))
        tweets = parse_tweets_from_instructions(instructions, quote_depth=self.quote_depth, include_raw=include_raw)
        target = next((tweet for tweet in tweets if tweet.get("id") == tweet_id), None)
        root_id = (target or {}).get("conversationId") or tweet_id
        thread = [tweet for tweet in tweets if tweet.get("conversationId") == root_id]

        def sort_key(tweet: dict) -> float:
            value = tweet.get("createdAt")
            if not value:
                return 0.0
            try:
                return parsedate_to_datetime(value).timestamp()
            except Exception:
                return 0.0

        thread.sort(key=sort_key)
        return {"success": True, "tweets": thread}
