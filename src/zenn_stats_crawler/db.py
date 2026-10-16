from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Dict, Optional, Union

from zenn_stats_crawler.parser import ArticleData

logger = logging.getLogger(__name__)


def parse_iso_datetime(dt_str: str) -> datetime:
    """ISO8601文字列をtimezone-awareなdatetimeにパースする"""
    try:
        # 末尾のZを+00:00に置換
        if dt_str.endswith("Z"):
            dt_str = dt_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


class Database:
    """
    SQLiteデータベースの初期化・問い合わせ・挿入を管理するクラス
    """

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_pragmas()
        self.init_schema()

    def _init_pragmas(self) -> None:
        """パフォーマンスと安全性のためのSQLite PRAGMA設定"""
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode = WAL;")
        cur.execute("PRAGMA synchronous = NORMAL;")
        cur.close()

    def init_schema(self) -> None:
        """テーブルおよびインデックスの作成"""
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT NOT NULL,
                article_type TEXT,
                title_hash TEXT,
                user_name_hash TEXT,
                published_at TEXT,
                comments_count INTEGER,
                liked_count INTEGER,
                authenticated_liked_count INTEGER,
                anonymous_liked_count INTEGER,
                bookmarked_count INTEGER,
                topics TEXT,
                publication_plan TEXT,
                publication_name_hash TEXT,
                crawled_at TEXT NOT NULL,
                status TEXT NOT NULL,
                http_status INTEGER,
                error_message TEXT
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles(url_hash);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_crawled_at ON articles(crawled_at);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_articles_url_crawled ON articles(url_hash, crawled_at DESC);"
        )
        self.conn.commit()
        cur.close()

    def get_latest_crawled_map(self, success_only: bool = False) -> Dict[str, datetime]:
        """
        各 url_hash の最新クロール日時を取得してマップ (url_hash -> datetime) で返す。
        success_only=True の場合は成功したクロールレコードのみを対象とする。
        """
        cur = self.conn.cursor()
        if success_only:
            query = "SELECT url_hash, MAX(crawled_at) FROM articles WHERE status = 'success' GROUP BY url_hash;"
        else:
            query = "SELECT url_hash, MAX(crawled_at) FROM articles GROUP BY url_hash;"

        cur.execute(query)
        result: Dict[str, datetime] = {}
        for url_hash, max_crawled_at in cur.fetchall():
            if url_hash and max_crawled_at:
                result[url_hash] = parse_iso_datetime(max_crawled_at)
        cur.close()
        return result

    def insert_article_snapshot(
        self,
        data: ArticleData,
        status: str = "success",
        http_status: Optional[int] = 200,
        error_message: Optional[str] = None,
    ) -> int:
        """正常取得できた記事スナップショットを挿入する"""
        cur = self.conn.cursor()
        topics_json = json.dumps(data.topics, ensure_ascii=False) if data.topics else "[]"
        cur.execute(
            """
            INSERT INTO articles (
                url_hash, article_type, title_hash, user_name_hash,
                published_at, comments_count, liked_count,
                authenticated_liked_count, anonymous_liked_count, bookmarked_count,
                topics, publication_plan, publication_name_hash,
                crawled_at, status, http_status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                data.url_hash,
                data.article_type,
                data.title_hash,
                data.user_name_hash,
                data.published_at,
                data.comments_count,
                data.liked_count,
                data.authenticated_liked_count,
                data.anonymous_liked_count,
                data.bookmarked_count,
                topics_json,
                data.publication_plan,
                data.publication_name_hash,
                data.crawled_at,
                status,
                http_status,
                error_message,
            ),
        )
        last_id = cur.lastrowid or 0
        self.conn.commit()
        cur.close()
        return last_id

    def insert_failed_snapshot(
        self,
        url_hash: str,
        error_message: str,
        http_status: Optional[int] = None,
        crawled_at: Optional[str] = None,
    ) -> int:
        """取得失敗レコードを挿入する"""
        if crawled_at is None:
            crawled_at = datetime.now(timezone.utc).isoformat()

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO articles (
                url_hash, crawled_at, status, http_status, error_message
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (url_hash, crawled_at, "failed", http_status, error_message),
        )
        last_id = cur.lastrowid or 0
        self.conn.commit()
        cur.close()
        return last_id

    def close(self) -> None:
        """DB接続をクローズする"""
        self.conn.close()

