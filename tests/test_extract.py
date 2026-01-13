from laserbeak.extract import extract_bookmark_folder_id, extract_list_id, extract_tweet_id


def test_extract_tweet_id_from_url():
    assert extract_tweet_id("https://x.com/user/status/1234567890") == "1234567890"


def test_extract_tweet_id_from_id():
    assert extract_tweet_id("1234567890") == "1234567890"


def test_extract_list_id():
    assert extract_list_id("https://x.com/i/lists/1234567") == "1234567"
    assert extract_list_id("1234567") == "1234567"
    assert extract_list_id("not-a-list") is None


def test_extract_bookmark_folder_id():
    assert extract_bookmark_folder_id("https://x.com/i/bookmarks/1234567") == "1234567"
    assert extract_bookmark_folder_id("1234567") == "1234567"
    assert extract_bookmark_folder_id("not-a-folder") is None
