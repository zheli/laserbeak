from __future__ import annotations

import json
import os

from .types import TweetData, TweetMedia, TwitterUser


def normalize_quote_depth(value: int | None) -> int:
    if value is None:
        return 1
    if not isinstance(value, int):
        return 1
    return max(0, int(value))


def first_text(*values: str | None) -> str | None:
    for value in values:
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return None


def collect_text_fields(value: object, keys: set[str], output: list[str]) -> None:
    if not value:
        return
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for item in value:
            collect_text_fields(item, keys, output)
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys and isinstance(nested, str):
                trimmed = nested.strip()
                if trimmed:
                    output.append(trimmed)
                continue
            collect_text_fields(nested, keys, output)


def unique_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def extract_article_text(result: dict | None) -> str | None:
    article = (result or {}).get("article")
    if not article:
        return None

    article_result = article.get("article_results", {}).get("result") or article
    if os.environ.get("BIRD_DEBUG_ARTICLE") == "1":
        payload = {
            "rest_id": (result or {}).get("rest_id"),
            "article": article_result,
            "note_tweet": (result or {}).get("note_tweet", {}).get("note_tweet_results", {}).get("result"),
        }
        print("[laserbeak][debug][article] payload:", json.dumps(payload, indent=2))

    title = first_text(article_result.get("title"), article.get("title"))
    body = first_text(
        article_result.get("plain_text"),
        article.get("plain_text"),
        (article_result.get("body") or {}).get("text"),
        (article_result.get("body") or {}).get("richtext", {}).get("text"),
        (article_result.get("body") or {}).get("rich_text", {}).get("text"),
        (article_result.get("content") or {}).get("text"),
        (article_result.get("content") or {}).get("richtext", {}).get("text"),
        (article_result.get("content") or {}).get("rich_text", {}).get("text"),
        article_result.get("text"),
        (article_result.get("richtext") or {}).get("text"),
        (article_result.get("rich_text") or {}).get("text"),
        (article.get("body") or {}).get("text"),
        (article.get("body") or {}).get("richtext", {}).get("text"),
        (article.get("body") or {}).get("rich_text", {}).get("text"),
        (article.get("content") or {}).get("text"),
        (article.get("content") or {}).get("richtext", {}).get("text"),
        (article.get("content") or {}).get("rich_text", {}).get("text"),
        article.get("text"),
        (article.get("richtext") or {}).get("text"),
        (article.get("rich_text") or {}).get("text"),
    )

    if body and title and body.strip() == title.strip():
        body = None

    if not body:
        collected: list[str] = []
        collect_text_fields(article_result, {"text", "title"}, collected)
        collect_text_fields(article, {"text", "title"}, collected)
        unique = unique_ordered(collected)
        filtered = [value for value in unique if value != title] if title else unique
        if filtered:
            body = "\n\n".join(filtered)

    if title and body and not body.startswith(title):
        return f"{title}\n\n{body}"

    return body or title


def extract_note_tweet_text(result: dict | None) -> str | None:
    note = (result or {}).get("note_tweet", {}).get("note_tweet_results", {}).get("result")
    if not note:
        return None
    return first_text(
        note.get("text"),
        (note.get("richtext") or {}).get("text"),
        (note.get("rich_text") or {}).get("text"),
        (note.get("content") or {}).get("text"),
        (note.get("content") or {}).get("richtext", {}).get("text"),
        (note.get("content") or {}).get("rich_text", {}).get("text"),
    )


def extract_tweet_text(result: dict | None) -> str | None:
    legacy = (result or {}).get("legacy") or {}
    return extract_article_text(result) or extract_note_tweet_text(result) or first_text(legacy.get("full_text"))


def extract_media(result: dict | None) -> list[TweetMedia] | None:
    legacy = (result or {}).get("legacy") or {}
    raw_media = (legacy.get("extended_entities") or {}).get("media") or (legacy.get("entities") or {}).get("media")
    if not raw_media:
        return None

    media: list[TweetMedia] = []

    for item in raw_media:
        if not isinstance(item, dict):
            continue
        if not item.get("type") or not item.get("media_url_https"):
            continue
        media_item: TweetMedia = {
            "type": item.get("type"),
            "url": item.get("media_url_https"),
        }
        sizes = item.get("sizes") or {}
        if isinstance(sizes.get("large"), dict):
            media_item["width"] = sizes["large"].get("w")
            media_item["height"] = sizes["large"].get("h")
        elif isinstance(sizes.get("medium"), dict):
            media_item["width"] = sizes["medium"].get("w")
            media_item["height"] = sizes["medium"].get("h")
        if isinstance(sizes.get("small"), dict):
            media_item["previewUrl"] = f"{item.get('media_url_https')}:small"

        if item.get("type") in {"video", "animated_gif"}:
            variants = (item.get("video_info") or {}).get("variants") or []
            mp4_variants = [
                v
                for v in variants
                if isinstance(v, dict) and v.get("content_type") == "video/mp4" and isinstance(v.get("url"), str)
            ]
            with_bitrate = [v for v in mp4_variants if isinstance(v.get("bitrate"), int)]
            with_bitrate.sort(key=lambda v: v.get("bitrate", 0), reverse=True)
            selected = with_bitrate[0] if with_bitrate else (mp4_variants[0] if mp4_variants else None)
            if selected and selected.get("url"):
                media_item["videoUrl"] = selected.get("url")
            duration_ms = (item.get("video_info") or {}).get("duration_millis")
            if isinstance(duration_ms, int):
                media_item["durationMs"] = duration_ms

        media.append(media_item)

    return media or None


def unwrap_tweet_result(result: dict | None) -> dict | None:
    if not result:
        return None
    return result.get("tweet") if result.get("tweet") else result


def map_tweet_result(result: dict | None, *, quote_depth: int, include_raw: bool = False) -> TweetData | None:
    if not result:
        return None
    user_result = ((result.get("core") or {}).get("user_results") or {}).get("result") or {}
    user_legacy = user_result.get("legacy") or {}
    user_core = user_result.get("core") or {}
    username = user_legacy.get("screen_name") or user_core.get("screen_name")
    name = user_legacy.get("name") or user_core.get("name") or username
    user_id = user_result.get("rest_id")
    if not result.get("rest_id") or not username:
        return None

    text = extract_tweet_text(result)
    if not text:
        return None

    quoted_tweet: TweetData | None = None
    if quote_depth > 0:
        quoted_result = unwrap_tweet_result((result.get("quoted_status_result") or {}).get("result"))
        if quoted_result:
            quoted_tweet = map_tweet_result(quoted_result, quote_depth=quote_depth - 1, include_raw=include_raw)

    media = extract_media(result)

    tweet_data: TweetData = {
        "id": result.get("rest_id"),
        "text": text,
        "createdAt": (result.get("legacy") or {}).get("created_at"),
        "replyCount": (result.get("legacy") or {}).get("reply_count"),
        "retweetCount": (result.get("legacy") or {}).get("retweet_count"),
        "likeCount": (result.get("legacy") or {}).get("favorite_count"),
        "conversationId": (result.get("legacy") or {}).get("conversation_id_str"),
        "inReplyToStatusId": (result.get("legacy") or {}).get("in_reply_to_status_id_str") or None,
        "author": {"username": username, "name": name or username},
        "authorId": user_id,
        "quotedTweet": quoted_tweet,
        "media": media,
    }

    if include_raw:
        tweet_data["_raw"] = result

    return tweet_data


def find_tweet_in_instructions(instructions: list[dict] | None, tweet_id: str) -> dict | None:
    if not instructions:
        return None
    for instruction in instructions:
        for entry in instruction.get("entries", []) or []:
            content = entry.get("content") or {}
            result = ((content.get("itemContent") or {}).get("tweet_results") or {}).get("result")
            if isinstance(result, dict) and result.get("rest_id") == tweet_id:
                return result
    return None


def collect_tweet_results_from_entry(entry: dict) -> list[dict]:
    results: list[dict] = []

    def push_result(candidate: dict | None):
        if candidate and candidate.get("rest_id"):
            results.append(candidate)

    content = entry.get("content") or {}
    push_result(((content.get("itemContent") or {}).get("tweet_results") or {}).get("result"))
    push_result((((content.get("item") or {}).get("itemContent") or {}).get("tweet_results") or {}).get("result"))

    for item in content.get("items") or []:
        push_result((((item.get("item") or {}).get("itemContent") or {}).get("tweet_results") or {}).get("result"))
        push_result(((item.get("itemContent") or {}).get("tweet_results") or {}).get("result"))
        push_result((((item.get("content") or {}).get("itemContent") or {}).get("tweet_results") or {}).get("result"))

    return results


def parse_tweets_from_instructions(instructions: list[dict] | None, *, quote_depth: int, include_raw: bool = False) -> list[TweetData]:
    tweets: list[TweetData] = []
    seen: set[str] = set()

    for instruction in instructions or []:
        for entry in instruction.get("entries", []) or []:
            results = collect_tweet_results_from_entry(entry)
            for result in results:
                mapped = map_tweet_result(result, quote_depth=quote_depth, include_raw=include_raw)
                if not mapped or mapped.get("id") in seen:
                    continue
                seen.add(mapped["id"])
                tweets.append(mapped)

    return tweets


def extract_cursor_from_instructions(instructions: list[dict] | None, cursor_type: str = "Bottom") -> str | None:
    for instruction in instructions or []:
        for entry in instruction.get("entries", []) or []:
            content = entry.get("content") or {}
            if content.get("cursorType") == cursor_type and isinstance(content.get("value"), str):
                if content["value"]:
                    return content["value"]
    return None


def parse_users_from_instructions(instructions: list[dict] | None) -> list[TwitterUser]:
    if not instructions:
        return []
    users: list[TwitterUser] = []

    for instruction in instructions:
        entries = instruction.get("entries") or []
        for entry in entries:
            content = (entry or {}).get("content") or {}
            raw_user_result = ((content.get("itemContent") or {}).get("user_results") or {}).get("result")
            user_result = raw_user_result
            if isinstance(raw_user_result, dict) and raw_user_result.get("__typename") == "UserWithVisibilityResults":
                user_result = raw_user_result.get("user") or raw_user_result

            if not isinstance(user_result, dict) or user_result.get("__typename") != "User":
                continue

            legacy = user_result.get("legacy") or {}
            core = user_result.get("core") or {}
            avatar = user_result.get("avatar") or {}
            username = legacy.get("screen_name") or core.get("screen_name")
            name = legacy.get("name") or core.get("name")

            if not user_result.get("rest_id") or not username:
                continue

            users.append(
                {
                    "id": user_result.get("rest_id"),
                    "username": username,
                    "name": name or username,
                    "description": legacy.get("description"),
                    "followersCount": legacy.get("followers_count"),
                    "followingCount": legacy.get("friends_count"),
                    "isBlueVerified": user_result.get("is_blue_verified"),
                    "profileImageUrl": legacy.get("profile_image_url_https") or avatar.get("image_url"),
                    "createdAt": legacy.get("created_at") or core.get("created_at"),
                }
            )

    return users


def _extract_list_result(raw_list_result: dict) -> dict | None:
    if raw_list_result.get("__typename") == "ListWithVisibilityResults" and raw_list_result.get("list"):
        raw_list_result = raw_list_result.get("list")
    if raw_list_result.get("__typename") != "List":
        return None
    legacy = raw_list_result.get("legacy") or {}
    owner = legacy.get("user_results", {}).get("result")
    owner_legacy = (owner or {}).get("legacy") or {}
    owner_core = (owner or {}).get("core") or {}
    owner_username = owner_legacy.get("screen_name") or owner_core.get("screen_name")
    owner_name = owner_legacy.get("name") or owner_core.get("name") or owner_username

    owner_data = None
    if owner and owner_username:
        owner_data = {
            "id": owner.get("rest_id"),
            "username": owner_username,
            "name": owner_name,
        }

    return {
        "id": raw_list_result.get("rest_id"),
        "name": legacy.get("name") or raw_list_result.get("name") or "",
        "description": legacy.get("description"),
        "memberCount": legacy.get("member_count"),
        "subscriberCount": legacy.get("subscriber_count"),
        "isPrivate": legacy.get("is_private"),
        "createdAt": legacy.get("created_at"),
        "owner": owner_data,
    }


def parse_lists_from_instructions(instructions: list[dict] | None) -> list[dict]:
    if not instructions:
        return []
    lists: list[dict] = []
    for instruction in instructions:
        entries = instruction.get("entries") or []
        for entry in entries:
            content = (entry or {}).get("content") or {}
            raw_list_result = ((content.get("itemContent") or {}).get("list_results") or {}).get("result")
            if not isinstance(raw_list_result, dict):
                continue
            parsed = _extract_list_result(raw_list_result)
            if parsed and parsed.get("id"):
                lists.append(parsed)
    return lists
