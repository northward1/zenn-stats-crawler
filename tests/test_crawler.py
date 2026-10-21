from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from zenn_stats_crawler.anonymizer import hash_text
from zenn_stats_crawler.db import Database
from zenn_stats_crawler.parser import ArticleData, parse_article_data
from zenn_stats_crawler.sitemap import parse_content_sitemap, parse_sitemap_index
from zenn_stats_crawler.url import normalize_url


def test_normalize_url():
    assert normalize_url("https://zenn.dev/user/articles/slug?foo=bar#frag") == "https://zenn.dev/user/articles/slug"
    assert normalize_url("https://ZENN.DEV/user/articles/slug/") == "https://zenn.dev/user/articles/slug"
    assert normalize_url("") == ""


def test_hash_text():
    h1 = hash_text("https://zenn.dev/user/articles/123", salt="test-salt")
    h2 = hash_text("https://zenn.dev/user/articles/123", salt="test-salt")
    h3 = hash_text("https://zenn.dev/user/articles/123", salt="different-salt")
    assert h1 == h2
    assert h1 != h3
    assert hash_text(None) is None


def test_sitemap_parsing():
    sitemap_index_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap>
            <loc>https://zenn.dev/sitemaps/article1.xml.gz</loc>
        </sitemap>
        <sitemap>
            <loc>https://zenn.dev/sitemaps/topics.xml.gz</loc>
        </sitemap>
        <sitemap>
            <loc>https://zenn.dev/sitemaps/books1.xml.gz</loc>
        </sitemap>
    </sitemapindex>
    """
    article_sitemaps = parse_sitemap_index(sitemap_index_xml)
    assert article_sitemaps == ["https://zenn.dev/sitemaps/article1.xml.gz"]

    all_sitemaps = parse_sitemap_index(sitemap_index_xml, pattern=r"/(article|books?)\d*\.xml(\.gz)?$")
    assert len(all_sitemaps) == 2

    content_sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
            <loc>https://zenn.dev/alice/articles/sample-slug</loc>
            <lastmod>2026-01-01T00:00:00Z</lastmod>
        </url>
    </urlset>
    """
    urls = parse_content_sitemap(content_sitemap_xml)
    assert len(urls) == 1
    assert urls[0].loc == "https://zenn.dev/alice/articles/sample-slug"


def test_fetch_all_urls_from_sitemaps_newest_first():
    from unittest.mock import MagicMock
    from zenn_stats_crawler.config import Config
    from zenn_stats_crawler.crawler import StatsCrawler
    from zenn_stats_crawler.sitemap import SitemapUrlInfo

    crawler = StatsCrawler(config=Config(hash_salt="test"))
    crawler.sitemap_crawler.fetch_sitemap_urls = MagicMock(
        return_value=[
            "https://zenn.dev/sitemaps/article1.xml.gz",
            "https://zenn.dev/sitemaps/article2.xml.gz",
        ]
    )

    def mock_fetch_urls(s_url):
        if "article1" in s_url:
            return [
                SitemapUrlInfo(loc="https://zenn.dev/u/articles/a1-1"),
                SitemapUrlInfo(loc="https://zenn.dev/u/articles/a1-2"),
            ]
        else:
            return [
                SitemapUrlInfo(loc="https://zenn.dev/u/articles/a2-1"),
                SitemapUrlInfo(loc="https://zenn.dev/u/articles/a2-2"),
            ]

    crawler.sitemap_crawler.fetch_urls_from_sitemap = MagicMock(side_effect=mock_fetch_urls)

    urls = crawler.fetch_all_urls_from_sitemaps(show_progress=False)
    # article2(最新サイトマップ)の末尾から先頭、続いてarticle1の末尾から先頭の順になること
    assert urls == [
        "https://zenn.dev/u/articles/a2-2",
        "https://zenn.dev/u/articles/a2-1",
        "https://zenn.dev/u/articles/a1-2",
        "https://zenn.dev/u/articles/a1-1",
    ]


def test_article_parsing():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "article": {
                        "id": 12345,
                        "title": "Zenn Test Article",
                        "articleType": "tech",
                        "publishedAt": "2026-03-01T12:00:00.000Z",
                        "likedCount": 42,
                        "authenticatedLikedCount": 40,
                        "anonymousLikedCount": 2,
                        "bookmarkedCount": 15,
                        "commentsCount": 3,
                        "user": {
                            "username": "bob"
                        },
                        "publication": {
                            "name": "sample_corp",
                            "plan": "pro"
                        },
                        "topics": [
                            {"name": "Python"},
                            {"name": "SQLite"}
                        ]
                    }
                }
            }
        }
        </script>
    </head>
    <body></body>
    </html>
    """
    data = parse_article_data(html, "https://zenn.dev/bob/articles/12345", salt="salt123")
    assert data.article_type == "tech"
    assert data.liked_count == 42
    assert data.bookmarked_count == 15
    assert data.comments_count == 3
    assert data.topics == ["Python", "SQLite"]
    assert data.publication_plan == "pro"
    assert data.url_hash == hash_text("https://zenn.dev/bob/articles/12345", "salt123")
    assert data.title_hash == hash_text("Zenn Test Article", "salt123")
    assert data.user_name_hash == hash_text("bob", "salt123")


def test_database_crud(tmp_path: Path):
    db_file = tmp_path / "test.db"
    db = Database(db_file)

    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(days=40)).isoformat()
    recent_time = (now - timedelta(days=10)).isoformat()

    # レコード挿入: 1つ目は40日前
    data1 = ArticleData(
        url_hash="hash_a",
        article_type="tech",
        title_hash="t_a",
        user_name_hash="u_a",
        published_at="2026-01-01T00:00:00Z",
        comments_count=1,
        liked_count=10,
        authenticated_liked_count=10,
        anonymous_liked_count=0,
        bookmarked_count=5,
        topics=["python"],
        publication_plan=None,
        publication_name_hash=None,
        crawled_at=old_time,
    )
    db.insert_article_snapshot(data1)

    # 2回目のクロール: 10日前 (推移レコード)
    data2 = ArticleData(
        url_hash="hash_a",
        article_type="tech",
        title_hash="t_a",
        user_name_hash="u_a",
        published_at="2026-01-01T00:00:00Z",
        comments_count=2,
        liked_count=15,
        authenticated_liked_count=14,
        anonymous_liked_count=1,
        bookmarked_count=7,
        topics=["python"],
        publication_plan=None,
        publication_name_hash=None,
        crawled_at=recent_time,
    )
    db.insert_article_snapshot(data2)

    # 失敗レコード
    db.insert_failed_snapshot(
        url_hash="hash_b",
        error_message="HTTP Error: 404 Not Found",
        http_status=404,
        crawled_at=old_time,
    )

    # 最新取得日時のマップ取得
    latest_map = db.get_latest_crawled_map()
    assert "hash_a" in latest_map
    assert "hash_b" in latest_map

    # hash_a の最新時刻は recent_time の方になっていること
    assert abs((latest_map["hash_a"] - datetime.fromisoformat(recent_time)).total_seconds()) < 1

    # レコード総数確認 (hash_a が2件、hash_b が1件で合計3件)
    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM articles;")
    assert cur.fetchone()[0] == 3

    # hash_a の推移が確認できること
    cur.execute("SELECT liked_count, crawled_at FROM articles WHERE url_hash = 'hash_a' ORDER BY id ASC;")
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 10
    assert rows[1][0] == 15

    db.close()


def test_stats_crawler_expiration_and_flow(tmp_path: Path, monkeypatch):
    from unittest.mock import MagicMock
    from zenn_stats_crawler.config import Config
    from zenn_stats_crawler.crawler import StatsCrawler

    db_path = tmp_path / "crawler_test.db"
    config = Config(hash_salt="salt", db_path=db_path)
    crawler = StatsCrawler(config=config)

    url_fresh = "https://zenn.dev/user/articles/fresh"
    url_expired = "https://zenn.dev/user/articles/expired"
    url_new = "https://zenn.dev/user/articles/new"

    hash_fresh = hash_text(url_fresh, "salt")
    hash_expired = hash_text(url_expired, "salt")

    now = datetime.now(timezone.utc)
    # fresh は 5 日前 (30日以内)
    crawler.db.insert_article_snapshot(
        ArticleData(
            url_hash=hash_fresh,
            article_type="tech",
            title_hash="t",
            user_name_hash="u",
            published_at="2026-01-01T00:00:00Z",
            comments_count=0,
            liked_count=5,
            authenticated_liked_count=5,
            anonymous_liked_count=0,
            bookmarked_count=1,
            topics=[],
            publication_plan=None,
            publication_name_hash=None,
            crawled_at=(now - timedelta(days=5)).isoformat(),
        )
    )
    # expired は 45 日前 (30日超過)
    crawler.db.insert_article_snapshot(
        ArticleData(
            url_hash=hash_expired,
            article_type="tech",
            title_hash="t",
            user_name_hash="u",
            published_at="2026-01-01T00:00:00Z",
            comments_count=0,
            liked_count=10,
            authenticated_liked_count=10,
            anonymous_liked_count=0,
            bookmarked_count=2,
            topics=[],
            publication_plan=None,
            publication_name_hash=None,
            crawled_at=(now - timedelta(days=45)).isoformat(),
        )
    )

    # モック: サイトマップから3つのURLが返る
    crawler.fetch_all_urls_from_sitemaps = MagicMock(return_value=[url_fresh, url_expired, url_new])

    # モック: client.get
    def mock_get(url):
        mock_resp = MagicMock()
        if "expired" in url:
            mock_resp.status_code = 200
            mock_resp.text = """
            <script id="__NEXT_DATA__" type="application/json">
            {"props":{"pageProps":{"article":{"title":"Expired","articleType":"tech","likedCount":12,"user":{"username":"bob"}}}}}
            </script>
            """
            return mock_resp
        elif "new" in url:
            # 失敗するケースをテスト
            import requests
            err_resp = MagicMock()
            err_resp.status_code = 404
            raise requests.HTTPError("404 Client Error", response=err_resp)
        return mock_resp

    crawler.client.get = MagicMock(side_effect=mock_get)

    stats = crawler.run(expire_days=30.0)

    assert stats["total_found"] == 3
    assert stats["skipped"] == 1  # fresh はスキップ
    assert stats["targets"] == 2  # expired と new が対象
    assert stats["crawled_success"] == 1  # expired
    assert stats["crawled_failed"] == 1   # new (404)

    # DBの中身を検証
    cur = crawler.db.conn.cursor()
    # expired は初回(liked=10)と今回(liked=12)で2件あること
    cur.execute("SELECT liked_count FROM articles WHERE url_hash = ? ORDER BY id ASC;", (hash_expired,))
    records = cur.fetchall()
    assert len(records) == 2
    assert records[0][0] == 10
    assert records[1][0] == 12

    # new は failed として記録されていること
    hash_new = hash_text(url_new, "salt")
    cur.execute("SELECT status, http_status FROM articles WHERE url_hash = ?;", (hash_new,))
    fail_rec = cur.fetchone()
    assert fail_rec is not None
    assert fail_rec[0] == "failed"
    assert fail_rec[1] == 404

    crawler.db.close()

