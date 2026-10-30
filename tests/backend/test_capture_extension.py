from backend.app.core.security import create_capture_token, decode_token
from backend.app.api.files import _source_platform


def test_capture_token_has_separate_scope():
    payload = decode_token(create_capture_token(7))
    assert payload["user_id"] == 7
    assert payload["token_type"] == "capture"


def test_source_platform_is_derived_from_page_host():
    assert _source_platform("https://www.xiaohongshu.com/explore/123") == "xhs"
    assert _source_platform("https://www.douyin.com/video/123") == "douyin"
    assert _source_platform("https://item.taobao.com/item.htm?id=1") == "taobao"
    assert _source_platform("https://item.jd.com/123.html") == "jd"
    assert _source_platform("https://example.com/photo") == "other"
