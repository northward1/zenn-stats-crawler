import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zenn_stats_crawler.anonymizer import hash_text
from zenn_stats_crawler.url import normalize_url

logger = logging.getLogger(__name__)

NEXT_DATA_PATTERN = re.compile(
    r'<script\s+[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


class ArticleParseError(Exception):
    """記事データのパースに失敗した場合の例外"""
    pass


@dataclass
class ArticleData:
    url_hash: Optional[str]
    article_type: Optional[str]
    title_hash: Optional[str]
    user_name_hash: Optional[str]
    published_at: Optional[str]
    comments_count: Optional[int]
    liked_count: Optional[int]
    authenticated_liked_count: Optional[int]
    anonymous_liked_count: Optional[int]
    bookmarked_count: Optional[int]
    topics: List[str]
    publication_plan: Optional[str]
    publication_name_hash: Optional[str]
    crawled_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def extract_next_data(html: str) -> Dict[str, Any]:
    """
    HTML文字列から __NEXT_DATA__ スクリプトタグの内容を抽出し、JSONとしてパースする
    """
    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise ArticleParseError("__NEXT_DATA__ script tag not found in HTML")

    json_str = match.group(1).strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ArticleParseError(f"Failed to parse __NEXT_DATA__ JSON: {exc}") from exc


def parse_article_data(
    html: str,
    url: str,
    salt: Optional[str] = None,
    crawled_at: Optional[str] = None,
) -> ArticleData:
    """
    記事ページのHTML文字列とURLを受け取り、匿名化された記事データを抽出する
    """
    next_data = extract_next_data(html)
    page_props = next_data.get("props", {}).get("pageProps", {})

    article = page_props.get("article")
    if not article or not isinstance(article, dict):
        raise ArticleParseError("Article object not found in pageProps")

    user = page_props.get("user") or article.get("user") or {}
    publication = page_props.get("publication") or article.get("publication")
    topics_raw = page_props.get("topics") or article.get("topics") or []

    # トピック名の抽出
    topics: List[str] = []
    if isinstance(topics_raw, list):
        for t in topics_raw:
            if isinstance(t, dict) and t.get("name"):
                topics.append(str(t["name"]))
            elif isinstance(t, str) and t.strip():
                topics.append(t.strip())

    # Publication情報の抽出
    publication_plan: Optional[str] = None
    publication_name_hash: Optional[str] = None
    if publication and isinstance(publication, dict):
        publication_plan = publication.get("plan")
        pub_name = publication.get("name")
        if pub_name:
            publication_name_hash = hash_text(str(pub_name), salt)

    user_username = user.get("username") if isinstance(user, dict) else None
    article_title = article.get("title")

    if crawled_at is None:
        crawled_at = datetime.now(timezone.utc).isoformat()

    normalized_url = normalize_url(url)

    return ArticleData(
        url_hash=hash_text(normalized_url, salt),
        article_type=article.get("articleType"),
        title_hash=hash_text(article_title, salt),
        user_name_hash=hash_text(user_username, salt),
        published_at=article.get("publishedAt"),
        comments_count=article.get("commentsCount"),
        liked_count=article.get("likedCount"),
        authenticated_liked_count=article.get("authenticatedLikedCount"),
        anonymous_liked_count=article.get("anonymousLikedCount"),
        bookmarked_count=article.get("bookmarkedCount"),
        topics=topics,
        publication_plan=publication_plan,
        publication_name_hash=publication_name_hash,
        crawled_at=crawled_at,
    )

