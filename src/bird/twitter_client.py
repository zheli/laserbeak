from __future__ import annotations

from .twitter_client_base import TwitterClientBase
from .twitter_client_bookmarks import TwitterClientBookmarksMixin
from .twitter_client_lists import TwitterClientListsMixin
from .twitter_client_media import TwitterClientMediaMixin
from .twitter_client_posting import TwitterClientPostingMixin
from .twitter_client_search import TwitterClientSearchMixin
from .twitter_client_timelines import TwitterClientTimelinesMixin
from .twitter_client_tweet_detail import TwitterClientTweetDetailMixin
from .twitter_client_users import TwitterClientUsersMixin


class TwitterClient(
    TwitterClientUsersMixin,
    TwitterClientListsMixin,
    TwitterClientTimelinesMixin,
    TwitterClientSearchMixin,
    TwitterClientTweetDetailMixin,
    TwitterClientPostingMixin,
    TwitterClientBookmarksMixin,
    TwitterClientMediaMixin,
    TwitterClientBase,
):
    pass
