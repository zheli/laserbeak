from bird.normalize import mentions_query_from_user_option, normalize_handle


def test_normalize_handle():
    assert normalize_handle("@steipete") == "steipete"
    assert normalize_handle("steipete") == "steipete"
    assert normalize_handle("") is None
    assert normalize_handle("invalid-handle") is None


def test_mentions_query_from_user_option():
    result = mentions_query_from_user_option("@steipete")
    assert result["query"] == "@steipete"
    assert result["error"] is None

    invalid = mentions_query_from_user_option("bad-handle")
    assert invalid["query"] is None
    assert invalid["error"]
