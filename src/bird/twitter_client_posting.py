from __future__ import annotations

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import TWITTER_API_BASE, TWITTER_GRAPHQL_POST_URL, TWITTER_STATUS_UPDATE_URL
from .twitter_client_features import build_tweet_create_features


class TwitterClientPostingMixin(TwitterClientBase):
    def tweet(self, text: str, media_ids: list[str] | None = None) -> dict:
        variables = {
            "tweet_text": text,
            "dark_request": False,
            "media": {
                "media_entities": [{"media_id": media_id, "tagged_users": []} for media_id in (media_ids or [])],
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": [],
        }
        features = build_tweet_create_features()
        return self._create_tweet(variables, features)

    def reply(self, text: str, reply_to_tweet_id: str, media_ids: list[str] | None = None) -> dict:
        variables = {
            "tweet_text": text,
            "reply": {"in_reply_to_tweet_id": reply_to_tweet_id, "exclude_reply_user_ids": []},
            "dark_request": False,
            "media": {
                "media_entities": [{"media_id": media_id, "tagged_users": []} for media_id in (media_ids or [])],
                "possibly_sensitive": False,
            },
            "semantic_annotation_ids": [],
        }
        features = build_tweet_create_features()
        return self._create_tweet(variables, features)

    def _create_tweet(self, variables: dict, features: dict) -> dict:
        self._ensure_client_user_id()
        query_id = self._get_query_id("CreateTweet")
        url_with_operation = f"{TWITTER_API_BASE}/{query_id}/CreateTweet"

        def build_body():
            return {"variables": variables, "features": features, "queryId": query_id}

        try:
            headers = {**self._get_headers(), "referer": "https://x.com/compose/post"}
            response = self._request("POST", url_with_operation, headers=headers, json_data=build_body())

            if response.status_code == 404:
                self._refresh_query_ids()
                query_id = self._get_query_id("CreateTweet")
                url_with_operation = f"{TWITTER_API_BASE}/{query_id}/CreateTweet"
                response = self._request("POST", url_with_operation, headers=headers, json_data=build_body())

                if response.status_code == 404:
                    retry = self._request("POST", TWITTER_GRAPHQL_POST_URL, headers=headers, json_data=build_body())
                    if retry.status_code >= 400:
                        return {"success": False, "error": f"HTTP {retry.status_code}: {retry.text[:200]}"}
                    data = retry.json()
                    if data.get("errors"):
                        fallback = self._try_status_update_fallback(data.get("errors", []), variables)
                        if fallback:
                            return fallback
                        return {"success": False, "error": self._format_errors(data.get("errors", []))}
                    tweet_id = (
                        (data.get("data") or {})
                        .get("create_tweet", {})
                        .get("tweet_results", {})
                        .get("result", {})
                        .get("rest_id")
                    )
                    if tweet_id:
                        return {"success": True, "tweetId": tweet_id}
                    return {"success": False, "error": "Tweet created but no ID returned"}

            if response.status_code >= 400:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:200]}"}

            data = response.json()
            if data.get("errors"):
                fallback = self._try_status_update_fallback(data.get("errors", []), variables)
                if fallback:
                    return fallback
                return {"success": False, "error": self._format_errors(data.get("errors", []))}

            tweet_id = (
                (data.get("data") or {})
                .get("create_tweet", {})
                .get("tweet_results", {})
                .get("result", {})
                .get("rest_id")
            )
            if tweet_id:
                return {"success": True, "tweetId": tweet_id}

            return {"success": False, "error": "Tweet created but no ID returned"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _format_errors(self, errors: list[dict]) -> str:
        parts = []
        for error in errors:
            message = error.get("message")
            code = error.get("code")
            if isinstance(code, int):
                parts.append(f"{message} ({code})")
            elif message:
                parts.append(str(message))
        return ", ".join(parts)

    def _status_update_input_from_create_tweet_variables(self, variables: dict) -> dict | None:
        text = variables.get("tweet_text") if isinstance(variables.get("tweet_text"), str) else None
        if not text:
            return None

        reply = variables.get("reply") if isinstance(variables.get("reply"), dict) else None
        in_reply_to_tweet_id = reply.get("in_reply_to_tweet_id") if reply else None

        media_entities = None
        if isinstance(variables.get("media"), dict):
            media_entities = variables.get("media", {}).get("media_entities")

        media_ids = []
        if isinstance(media_entities, list):
            for entity in media_entities:
                if isinstance(entity, dict) and entity.get("media_id"):
                    media_ids.append(entity.get("media_id"))

        return {
            "text": text,
            "inReplyToTweetId": in_reply_to_tweet_id,
            "mediaIds": media_ids,
        }

    def _try_status_update_fallback(self, errors: list[dict], variables: dict) -> dict | None:
        if not any(err.get("code") == 226 for err in errors if isinstance(err, dict)):
            return None
        payload = self._status_update_input_from_create_tweet_variables(variables)
        if not payload:
            return None

        text = payload.get("text")
        media_ids = payload.get("mediaIds") or []
        in_reply_to_tweet_id = payload.get("inReplyToTweetId")

        params = {
            "status": text,
            "tweet_mode": "extended",
        }
        if in_reply_to_tweet_id:
            params["in_reply_to_status_id"] = in_reply_to_tweet_id
            params["auto_populate_reply_metadata"] = "true"
        if media_ids:
            params["media_ids"] = ",".join(media_ids)

        try:
            response = self._request(
                "POST",
                TWITTER_STATUS_UPDATE_URL,
                headers=self._get_headers(),
                data=params,
            )
            if response.status_code >= 400:
                return None
            data = response.json()
            tweet_id = data.get("id_str") or data.get("id")
            if tweet_id:
                return {"success": True, "tweetId": str(tweet_id)}
        except Exception:
            return None

        return None
