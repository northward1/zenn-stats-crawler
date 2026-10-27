import json
import pytest

from zenn_stats_crawler.timeline import (
    TimelineItem,
    escape_markdown_table_cell,
    format_display_datetime,
    format_timeline_markdown,
    format_timeline_table,
    parse_timeline_item_from_html,
    split_markdown_for_scrap,
)


def test_escape_markdown_table_cell():
    raw = "Hello | World \n Test \r\n Pipe | "
    escaped = escape_markdown_table_cell(raw)
    assert r"\|" in escaped
    assert "\n" not in escaped
    assert "\r" not in escaped
    assert escaped == r"Hello \| World   Test   Pipe \|"


def test_format_display_datetime():
    assert format_display_datetime("2026-10-26T02:31:14.910+09:00") == "10/26 02:31"
    assert format_display_datetime("2026-10-26T02:31:14+09:00") == "10/26 02:31"
    assert format_display_datetime(None) == "-"
    assert format_display_datetime("") == "-"


def test_parse_timeline_item_from_html():
    next_data = {
        "props": {
            "pageProps": {
                "article": {
                    "slug": "test-article",
                    "title": "Title with | pipe",
                    "emoji": "🚀",
                    "publishedAt": "2026-10-27T10:00:00.000+09:00",
                    "likedCount": 5,
                },
                "user": {
                    "username": "alice",
                    "name": "Alice",
                },
                "publication": {
                    "name": "techcorp",
                    "displayName": "Tech Corp Blog",
                },
            }
        }
    }
    html = f'<html><head><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></head><body></body></html>'
    item = parse_timeline_item_from_html(html, "https://zenn.dev/alice/articles/test-article")

    assert item is not None
    assert item.slug == "test-article"
    assert item.title == "Title with | pipe"
    assert item.emoji == "🚀"
    assert item.username == "alice"
    assert item.display_name == "Alice"
    assert item.published_at == "2026-10-27T10:00:00.000+09:00"
    assert item.liked_count == 5
    assert item.publication_name == "techcorp"
    assert item.publication_display_name == "Tech Corp Blog"


def test_format_timeline_table():
    items = [
        TimelineItem(
            url="https://zenn.dev/alice/articles/art1",
            slug="art1",
            title="First Article | Review",
            emoji="📘",
            username="alice",
            display_name="Alice",
            published_at="2026-10-27T10:00:00.000+09:00",
            liked_count=3,
            publication_name="techcorp",
            publication_display_name="Tech Corp Blog",
        ),
        TimelineItem(
            url="https://zenn.dev/bob/articles/art2",
            slug="art2",
            title="Second Article",
            emoji="💡",
            username="bob",
            display_name="bob",
            published_at="2026-10-27T09:00:00.000+09:00",
            liked_count=0,
        ),
    ]

    table = format_timeline_table(items)
    lines = table.strip().split("\n")

    assert lines[0] == "| | タイトル | ユーザー名 | 投稿日時 | ♡ |"
    assert lines[1] == "| :---: | :--- | :--- | :---: | :---: |"
    assert r"📘 | [First Article \| Review](https://zenn.dev/alice/articles/art1) | [Alice](https://zenn.dev/alice) in [Tech Corp Blog](https://zenn.dev/p/techcorp) | 10/27 10:00 | 3" in lines[2]
    assert r"💡 | [Second Article](https://zenn.dev/bob/articles/art2) | [bob](https://zenn.dev/bob) | 10/27 09:00 | 0" in lines[3]


def test_split_markdown_for_scrap():
    items = [
        TimelineItem(
            url=f"https://zenn.dev/user{i}/articles/art{i}",
            slug=f"art{i}",
            title=f"Article {i} " + "X" * 100,
            emoji="📝",
            username=f"user{i}",
            display_name=f"User {i}",
            published_at="2026-10-27T10:00:00.000+09:00",
            liked_count=i,
        )
        for i in range(20)
    ]

    # When limit is high enough, single chunk returned
    chunks = split_markdown_for_scrap(items, base_title="### Title", max_chars=50000)
    assert len(chunks) == 1

    # When limit is small, splits into 2 chunks
    chunks_split = split_markdown_for_scrap(items, base_title="### Title", max_chars=1000)
    assert len(chunks_split) == 2
    assert "### Title" in chunks_split[0]
    assert "### 新着タイムライン (続き)" in chunks_split[1]


def test_delete_old_timeline_comments(monkeypatch):
    from zenn_stats_crawler.timeline import delete_old_timeline_comments

    mock_details = {
        "scrap": {"slug": "test_scrap"},
        "comments": [
            {"slug": "c0_root_desc"},
            {"slug": "c1_old_timeline"},
            {"slug": "c2_old_timeline"},
        ],
    }

    deleted_slugs = []

    def mock_get_scrap_details(scrap_slug_or_url, zenn_cmd="zenn"):
        return mock_details

    def mock_delete_scrap_comment(scrap_slug_or_url, comment_slug, zenn_cmd="zenn"):
        deleted_slugs.append(comment_slug)
        return True

    monkeypatch.setattr("zenn_stats_crawler.timeline.get_scrap_details", mock_get_scrap_details)
    monkeypatch.setattr("zenn_stats_crawler.timeline.delete_scrap_comment", mock_delete_scrap_comment)

    # keep_root=True should preserve c0_root_desc and only delete c1 and c2
    count = delete_old_timeline_comments("test_scrap", keep_root=True)
    assert count == 2
    assert deleted_slugs == ["c1_old_timeline", "c2_old_timeline"]
    assert "c0_root_desc" not in deleted_slugs


