from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from .twitter_client_base import TwitterClientBase
from .twitter_client_constants import (
    SETTINGS_NAME_REGEX,
    SETTINGS_SCREEN_NAME_REGEX,
    SETTINGS_USER_ID_REGEX,
    TWITTER_API_BASE,
)
from .twitter_client_features import build_following_features
from .twitter_client_utils import parse_users_from_instructions


class TwitterClientUsersMixin(TwitterClientBase):
    def _get_following_query_ids(self) -> list[str]:
        primary = self._get_query_id("Following")
        return list({primary, "BEkNpEt5pNETESoqMsTEGA"})

    def _get_followers_query_ids(self) -> list[str]:
        primary = self._get_query_id("Followers")
        return list({primary, "kuFUYP9eV1FPoEy4N-pi7w"})

    def _get_followers_via_rest(self, user_id: str, count: int) -> dict:
        params = urlencode(
            {
                "user_id": user_id,
                "count": str(count),
                "skip_status": "true",
                "include_user_entities": "false",
            }
        )
        urls = [
            f"https://x.com/i/api/1.1/followers/list.json?{params}",
            f"https://api.twitter.com/1.1/followers/list.json?{params}",
        ]

        last_error = None
        for url in urls:
            try:
                response = self._request("GET", url, headers=self._get_headers())
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    continue

                data = response.json()
                users = []
                for user in data.get("users", []) or []:
                    user_id_val = user.get("id_str") or user.get("id")
                    username = user.get("screen_name")
                    if not user_id_val or not username:
                        continue
                    users.append(
                        {
                            "id": str(user_id_val),
                            "username": username,
                            "name": user.get("name") or username,
                            "description": user.get("description"),
                            "followersCount": user.get("followers_count"),
                            "followingCount": user.get("friends_count"),
                            "isBlueVerified": user.get("verified"),
                            "profileImageUrl": user.get("profile_image_url_https"),
                            "createdAt": user.get("created_at"),
                        }
                    )

                return {"success": True, "users": users}
            except Exception as exc:
                last_error = str(exc)

        return {"success": False, "error": last_error or "Unknown error fetching followers"}

    def _get_following_via_rest(self, user_id: str, count: int) -> dict:
        params = urlencode(
            {
                "user_id": user_id,
                "count": str(count),
                "skip_status": "true",
                "include_user_entities": "false",
            }
        )
        urls = [
            f"https://x.com/i/api/1.1/friends/list.json?{params}",
            f"https://api.twitter.com/1.1/friends/list.json?{params}",
        ]

        last_error = None
        for url in urls:
            try:
                response = self._request("GET", url, headers=self._get_headers())
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    continue

                data = response.json()
                users = []
                for user in data.get("users", []) or []:
                    user_id_val = user.get("id_str") or user.get("id")
                    username = user.get("screen_name")
                    if not user_id_val or not username:
                        continue
                    users.append(
                        {
                            "id": str(user_id_val),
                            "username": username,
                            "name": user.get("name") or username,
                            "description": user.get("description"),
                            "followersCount": user.get("followers_count"),
                            "followingCount": user.get("friends_count"),
                            "isBlueVerified": user.get("verified"),
                            "profileImageUrl": user.get("profile_image_url_https"),
                            "createdAt": user.get("created_at"),
                        }
                    )

                return {"success": True, "users": users}
            except Exception as exc:
                last_error = str(exc)

        return {"success": False, "error": last_error or "Unknown error fetching following"}

    def get_current_user(self) -> dict:
        candidate_urls = [
            "https://x.com/i/api/account/settings.json",
            "https://api.twitter.com/1.1/account/settings.json",
            "https://x.com/i/api/account/verify_credentials.json?skip_status=true&include_entities=false",
            "https://api.twitter.com/1.1/account/verify_credentials.json?skip_status=true&include_entities=false",
        ]

        last_error = None
        for url in candidate_urls:
            try:
                response = self._request("GET", url, headers=self._get_headers())
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    continue

                text = response.text
                data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                screen_name = data.get("screen_name")
                name = data.get("name")
                user_id = data.get("user_id") or data.get("id") or data.get("id_str")

                if not screen_name:
                    match = re.search(SETTINGS_SCREEN_NAME_REGEX, text)
                    if match:
                        screen_name = match.group(1)
                if not user_id:
                    match = re.search(SETTINGS_USER_ID_REGEX, text)
                    if match:
                        user_id = match.group(1)
                if not name:
                    match = re.search(SETTINGS_NAME_REGEX, text)
                    if match:
                        name = match.group(1)

                if screen_name and user_id:
                    return {
                        "success": True,
                        "user": {
                            "id": str(user_id),
                            "username": screen_name,
                            "name": name or screen_name,
                        },
                    }

                last_error = "Failed to parse current user"
            except Exception as exc:
                last_error = str(exc)

        return {"success": False, "error": last_error or "Unknown error fetching current user"}

    def _get_following_or_followers(self, kind: str, user_id: str, count: int) -> dict:
        variables = {
            "userId": user_id,
            "count": count,
            "includePromotedContent": False,
            "withClientEventToken": False,
            "withBirdwatchNotes": False,
            "withVoice": True,
        }
        features = build_following_features()
        params = urlencode({"variables": json.dumps(variables), "features": json.dumps(features)})

        query_ids = self._get_following_query_ids() if kind == "Following" else self._get_followers_query_ids()

        last_error = None
        had_404 = False
        for query_id in query_ids:
            url = f"{TWITTER_API_BASE}/{query_id}/{kind}?{params}"
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
                users = parse_users_from_instructions(instructions)
                return {"success": True, "users": users, "had404": had_404}
            except Exception as exc:
                last_error = str(exc)

        return {"success": False, "error": last_error or "Unknown error", "had404": had_404}

    def get_following(self, user_id: str, count: int = 20) -> dict:
        result = self._get_following_or_followers("Following", user_id, count)
        if result.get("success"):
            return {"success": True, "users": result.get("users")}
        if result.get("had404"):
            self._refresh_query_ids()
            retry = self._get_following_or_followers("Following", user_id, count)
            if retry.get("success"):
                return {"success": True, "users": retry.get("users")}
            return {"success": False, "error": retry.get("error")}
        if result.get("error"):
            fallback = self._get_following_via_rest(user_id, count)
            if fallback.get("success"):
                return fallback
        return {"success": False, "error": result.get("error")}

    def get_followers(self, user_id: str, count: int = 20) -> dict:
        result = self._get_following_or_followers("Followers", user_id, count)
        if result.get("success"):
            return {"success": True, "users": result.get("users")}
        if result.get("had404"):
            self._refresh_query_ids()
            retry = self._get_following_or_followers("Followers", user_id, count)
            if retry.get("success"):
                return {"success": True, "users": retry.get("users")}
            return {"success": False, "error": retry.get("error")}
        if result.get("error"):
            fallback = self._get_followers_via_rest(user_id, count)
            if fallback.get("success"):
                return fallback
        return {"success": False, "error": result.get("error")}
