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
    assert format_display_datetime("2026-10-26T02:31:14.910+09:00") == "2026-10-26 02:31:14"
    assert format_display_datetime("2026-10-26T02:31:14+09:00") == "2026-10-26 02:31:14"
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
    assert item.published_at == "2026-10-27T10:00:00.000+09:00"
    assert item.liked_count == 5


def test_format_timeline_table():
    items = [
        TimelineItem(
            url="https://zenn.dev/alice/articles/art1",
            slug="art1",
            title="First Article | Review",
            emoji="📘",
            username="alice",
            published_at="2026-10-27T10:00:00.000+09:00",
            liked_count=3,
        ),
        TimelineItem(
            url="https://zenn.dev/bob/articles/art2",
            slug="art2",
            title="Second Article",
            emoji="💡",
            username="bob",
            published_at="2026-10-27T09:00:00.000+09:00",
            liked_count=0,
        ),
    ]

    table = format_timeline_table(items)
    lines = table.strip().split("\n")

    assert lines[0] == "| favicon | title | user名 | 投稿時間 | like数 |"
    assert lines[1] == "| :---: | :--- | :--- | :---: | :---: |"
    assert r"📘 | [First Article \| Review](https://zenn.dev/alice/articles/art1) | [@alice](https://zenn.dev/alice) | 2026-10-27 10:00:00 | ❤️ 3" in lines[2]
    assert r"💡 | [Second Article](https://zenn.dev/bob/articles/art2) | [@bob](https://zenn.dev/bob) | 2026-10-27 09:00:00 | ❤️ 0" in lines[3]


def test_split_markdown_for_scrap():
    items = [
        TimelineItem(
            url=f"https://zenn.dev/user{i}/articles/art{i}",
            slug=f"art{i}",
            title=f"Article {i} " + "X" * 100,
            emoji="📝",
            username=f"user{i}",
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
    assert "(1〜10件)" in chunks_split[0]
    assert "(11〜20件)" in chunks_split[1]
