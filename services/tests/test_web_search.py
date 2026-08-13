"""web_search 结构化结果单元测试（不发起真实网络请求）。"""

from shared.capabilities.knowledge.search.web import _format_hits, _normalize_hit, build_site_scoped_query


def test_normalize_hit_prefers_href_and_body():
    hit = _normalize_hit(
        {"title": "面经", "href": "https://example.com/a", "body": "摘要内容"}
    )
    assert hit == {
        "title": "面经",
        "url": "https://example.com/a",
        "snippet": "摘要内容",
    }


def test_normalize_hit_falls_back_link_snippet():
    hit = _normalize_hit(
        {"title": "", "link": "https://example.com/b", "snippet": "x" * 300}
    )
    assert hit is not None
    assert hit["title"] == "https://example.com/b"
    assert hit["url"] == "https://example.com/b"
    assert len(hit["snippet"]) == 280


def test_normalize_hit_skips_missing_url():
    assert _normalize_hit({"title": "无链接", "body": "…"}) is None


def test_format_hits_empty():
    assert _format_hits([]) == "未找到相关结果。"


def test_format_hits_list():
    text = _format_hits(
        [{"title": "T", "url": "https://x.test", "snippet": "S"}]
    )
    assert "[1] T" in text
    assert "URL: https://x.test" in text
    assert "摘要: S" in text


def test_site_scoped_query():
    assert build_site_scoped_query("agent 面经", ["nowcoder.com"]) == (
        "(site:nowcoder.com) agent 面经"
    )
    assert build_site_scoped_query("  ", None) == ""
