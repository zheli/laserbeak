from __future__ import annotations

from typing import Literal, TypedDict


class TwitterCookies(TypedDict, total=False):
    authToken: str | None
    ct0: str | None
    cookieHeader: str | None
    source: str | None


class CookieExtractionResult(TypedDict):
    cookies: TwitterCookies
    warnings: list[str]


CookieSource = Literal["safari", "chrome", "firefox"]


class TweetMedia(TypedDict, total=False):
    type: Literal["photo", "video", "animated_gif"]
    url: str
    previewUrl: str
    width: int
    height: int
    videoUrl: str
    durationMs: int


class TweetAuthor(TypedDict):
    username: str
    name: str


class TweetData(TypedDict, total=False):
    id: str
    text: str
    author: TweetAuthor
    authorId: str
    createdAt: str
    replyCount: int
    retweetCount: int
    likeCount: int
    conversationId: str
    inReplyToStatusId: str
    quotedTweet: TweetData
    media: list[TweetMedia]
    _raw: dict


class GetTweetResult(TypedDict, total=False):
    success: bool
    tweet: TweetData
    error: str


class SearchResult(TypedDict, total=False):
    success: bool
    tweets: list[TweetData]
    error: str
    nextCursor: str


class CurrentUserResult(TypedDict, total=False):
    success: bool
    user: dict
    error: str


class TwitterUser(TypedDict, total=False):
    id: str
    username: str
    name: str
    description: str
    followersCount: int
    followingCount: int
    isBlueVerified: bool
    profileImageUrl: str
    createdAt: str


class FollowingResult(TypedDict, total=False):
    success: bool
    users: list[TwitterUser]
    error: str


class TweetResult(TypedDict, total=False):
    success: bool
    tweetId: str
    error: str


class BookmarkMutationResult(TypedDict, total=False):
    success: bool
    error: str


class UploadMediaResult(TypedDict, total=False):
    success: bool
    mediaId: str
    error: str


class TwitterList(TypedDict, total=False):
    id: str
    name: str
    description: str
    memberCount: int
    subscriberCount: int
    isPrivate: bool
    createdAt: str
    owner: dict


class ListsResult(TypedDict, total=False):
    success: bool
    lists: list[TwitterList]
    error: str


class TwitterClientOptions(TypedDict, total=False):
    cookies: TwitterCookies
    userAgent: str
    timeoutMs: int
    quoteDepth: int
