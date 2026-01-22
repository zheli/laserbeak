from __future__ import annotations

import json
from importlib import resources

from . import data

TWITTER_API_BASE = "https://x.com/i/api/graphql"
TWITTER_GRAPHQL_POST_URL = "https://x.com/i/api/graphql"
TWITTER_UPLOAD_URL = "https://upload.twitter.com/i/media/upload.json"
TWITTER_MEDIA_METADATA_URL = "https://x.com/i/api/1.1/media/metadata/create.json"
TWITTER_STATUS_UPDATE_URL = "https://x.com/i/api/1.1/statuses/update.json"
SETTINGS_SCREEN_NAME_REGEX = r"\"screen_name\":\"([^\"]+)\""
SETTINGS_USER_ID_REGEX = r"\"user_id\"\s*:\s*\"(\d+)\""
SETTINGS_NAME_REGEX = r"\"name\":\"([^\"\\]*(?:\\.[^\"\\]*)*)\""

FALLBACK_QUERY_IDS = {
    "CreateTweet": "TAJw1rBsjAtdNgTdlo2oeg",
    "CreateRetweet": "ojPdsZsimiJrUGLR1sjUtA",
    "FavoriteTweet": "lI07N6Otwv1PhnEgXILM7A",
    "DeleteBookmark": "Wlmlj2-xzyS1GN3a6cj-mQ",
    "TweetDetail": "97JF30KziU00483E_8elBA",
    "SearchTimeline": "M1jEez78PEfVfbQLvlWMvQ",
    "UserArticlesTweets": "8zBy9h4L90aDL02RsBcCFg",
    "Bookmarks": "RV1g3b8n_SGOHwkqKYSCFw",
    "Following": "BEkNpEt5pNETESoqMsTEGA",
    "Followers": "kuFUYP9eV1FPoEy4N-pi7w",
    "Likes": "JR2gceKucIKcVNB_9JkhsA",
    "BookmarkFolderTimeline": "KJIQpsvxrTfRIlbaRIySHQ",
    "ListOwnerships": "wQcOSjSQ8NtgxIwvYl1lMg",
    "ListMemberships": "BlEXXdARdSeL_0KyKHHvvg",
    "ListLatestTweetsTimeline": "2TemLyqrMpTeAmysdbnVqw",
    "ListByRestId": "wXzyA5vM_aVkBL9G8Vp3kw",
}

with resources.files(data).joinpath("query-ids.json").open("r", encoding="utf-8") as handle:
    _QUERY_IDS = json.load(handle)

QUERY_IDS = {**FALLBACK_QUERY_IDS, **_QUERY_IDS}
TARGET_QUERY_ID_OPERATIONS = list(FALLBACK_QUERY_IDS.keys())
