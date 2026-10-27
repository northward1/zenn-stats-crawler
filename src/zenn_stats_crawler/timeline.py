"""
最新記事のクロールおよび新着タイムライン生成・Scrap投稿モジュール
"""

from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import subprocess
import tempfile
from typing import List, Optional

from tqdm import tqdm

from zenn_stats_crawler.client import RateLimitedClient
from zenn_stats_crawler.config import Config
from zenn_stats_crawler.parser import extract_next_data
from zenn_stats_crawler.sitemap import SitemapCrawler
from zenn_stats_crawler.url import normalize_url

logger = logging.getLogger(__name__)


@dataclass
class TimelineItem:
    url: str
    slug: str
    title: str
    emoji: str
    username: str
    display_name: str
    published_at: str
    liked_count: int
    publication_name: Optional[str] = None
    publication_display_name: Optional[str] = None


def escape_markdown_table_cell(text: str) -> str:
    """Markdownテーブルの区切り文字（パイプ）や改行をエスケープする"""
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return text.replace("|", r"\|").strip()


def format_display_datetime(iso_str: Optional[str]) -> str:
    """ISO8601形式の公開日時を表示用 (MM/DD HH:MM) に整形する"""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        if "T" in iso_str:
            date_part, time_part = iso_str.split("T")
            parts = date_part.split("-")
            mm_dd = f"{parts[1]}/{parts[2]}" if len(parts) >= 3 else date_part
            hh_mm = time_part[:5]
            return f"{mm_dd} {hh_mm}"
        return iso_str


def parse_timeline_item_from_html(html: str, url: str) -> Optional[TimelineItem]:
    """記事詳細HTMLの __NEXT_DATA__ からタイムライン表示用データを抽出する"""
    try:
        next_data = extract_next_data(html)
    except Exception as exc:
        logger.warning(f"__NEXT_DATA__ の抽出に失敗しました ({url}): {exc}")
        return None

    page_props = next_data.get("props", {}).get("pageProps", {})
    article = page_props.get("article")
    if not article or not isinstance(article, dict):
        logger.warning(f"article オブジェクトが見つかりません ({url})")
        return None

    user = page_props.get("user") or article.get("user") or {}
    username = user.get("username") if isinstance(user, dict) else ""
    display_name = user.get("name") if isinstance(user, dict) else ""

    # URLからも username をフォールバック抽出可能
    if not username:
        m = re.match(r"^https://zenn\.dev/([^/]+)/articles/", url)
        if m:
            username = m.group(1)

    slug = article.get("slug") or url.rstrip("/").split("/")[-1]
    title = article.get("title") or slug
    emoji = article.get("emoji") or "📝"
    published_at = article.get("publishedAt") or ""
    liked_count = article.get("likedCount") or 0

    publication = page_props.get("publication") or article.get("publication")
    pub_name = None
    pub_display_name = None
    if publication and isinstance(publication, dict):
        pub_name = publication.get("name")
        pub_display_name = publication.get("displayName") or pub_name

    return TimelineItem(
        url=normalize_url(url),
        slug=slug,
        title=title,
        emoji=emoji,
        username=username or "不明",
        display_name=display_name or username or "不明",
        published_at=published_at,
        liked_count=liked_count,
        publication_name=pub_name,
        publication_display_name=pub_display_name,
    )


def fetch_recent_article_urls(
    sitemap_crawler: SitemapCrawler,
    index_url: str = "https://zenn.dev/sitemaps/_index.xml",
    limit: int = 100,
    show_progress: bool = False,
) -> List[str]:
    """
    サイトマップインデックスから新しい順にサイトマップを辿り、
    最新の指定件数（limit）の記事URLを抽出する。
    """
    sitemap_urls = sitemap_crawler.fetch_sitemap_urls(index_url)
    # 最新のサイトマップから逆順に走査
    sitemap_urls.reverse()

    urls: List[str] = []
    seen = set()

    for s_url in sitemap_urls:
        if len(urls) >= limit:
            break
        try:
            items = sitemap_crawler.fetch_urls_from_sitemap(s_url)
            # 各サイトマップ内のURLも末尾（最新）から逆順に走査
            for item in reversed(items):
                norm = normalize_url(item.loc)
                if norm and norm not in seen:
                    seen.add(norm)
                    urls.append(norm)
                    if len(urls) >= limit:
                        break
        except Exception as exc:
            logger.warning(f"サイトマップ取得エラー ({s_url}): {exc}")

    return urls[:limit]


def crawl_recent_timeline_items(
    client: RateLimitedClient,
    config: Optional[Config] = None,
    limit: int = 100,
    show_progress: bool = True,
) -> List[TimelineItem]:
    """
    最新のサイトマップから最新記事URLを収集し、
    RateLimitedClientでページをクロールしてタイムライン用データを取得する。
    """
    config = config or Config.from_env()
    sitemap_crawler = SitemapCrawler(client)

    candidate_limit = max(limit, int(limit * 1.2) + 5)
    logger.info(f"サイトマップから最新候補URLを {candidate_limit} 件抽出中 (最終出力: {limit} 件)...")
    urls = fetch_recent_article_urls(
        sitemap_crawler=sitemap_crawler,
        index_url=config.sitemap_index_url,
        limit=candidate_limit,
    )
    logger.info(f"取得した候補URL: {len(urls)} 件。記事詳細のクロールを開始します。")

    items: List[TimelineItem] = []
    for url in tqdm(urls, desc="最新記事クロール", disable=not show_progress):
        try:
            response = client.get(url)
            item = parse_timeline_item_from_html(response.text, url)
            if item:
                items.append(item)
        except Exception as exc:
            logger.warning(f"記事クロールエラー ({url}): {exc}")

    # 公開日時の降順でソート（完全新着順）
    items.sort(key=lambda x: x.published_at or "", reverse=True)
    items = items[:limit]
    logger.info(f"記事クロール完了: 有効件数 {len(items)} 件 (published_at 降順で上位 {limit} 件に確定)")
    return items


def format_timeline_table(items: List[TimelineItem]) -> str:
    """
    記事一覧を指定フォーマットのMarkdownテーブルに整形する
    カラム: | (favicon) | タイトル | ユーザー名 | 投稿日時 | ♡ |
    """
    lines: List[str] = [
        "| | タイトル | ユーザー名 | 投稿日時 | ♡ |",
        "| :---: | :--- | :--- | :---: | :---: |",
    ]

    for item in items:
        favicon = item.emoji or "📝"
        safe_title = escape_markdown_table_cell(item.title)
        title_link = f"[{safe_title}]({item.url})"

        user_display = item.display_name or item.username
        safe_user = escape_markdown_table_cell(user_display)
        if item.username and item.username != "不明":
            user_link = f"[{safe_user}](https://zenn.dev/{item.username})"
        else:
            user_link = safe_user or "不明"

        if item.publication_name:
            pub_display = item.publication_display_name or item.publication_name
            safe_pub = escape_markdown_table_cell(pub_display)
            pub_link = f"[{safe_pub}](https://zenn.dev/p/{item.publication_name})"
            user_col = f"{user_link} in {pub_link}"
        else:
            user_col = user_link

        dt_str = format_display_datetime(item.published_at)
        likes_str = str(item.liked_count)

        lines.append(f"| {favicon} | {title_link} | {user_col} | {dt_str} | {likes_str} |")

    return "\n".join(lines)


def format_timeline_markdown(
    items: List[TimelineItem],
    header_title: Optional[str] = None,
) -> str:
    """ヘッダー付きでタイムラインMarkdownを生成する"""
    table_md = format_timeline_table(items)
    if header_title:
        return f"{header_title}\n\n{table_md}\n"
    return f"{table_md}\n"


def split_markdown_for_scrap(
    items: List[TimelineItem],
    base_title: str,
    max_chars: int = 19000,
) -> List[str]:
    """
    Zenn Scrap の 20,000 文字制限に収まるように必要に応じて分割する。
    19,000文字以内であれば1コメント、超過する場合は前半・後半に分割する。
    """
    full_md = format_timeline_markdown(items, header_title=base_title)
    if len(full_md) <= max_chars:
        return [full_md]

    # 50件ずつに分割
    mid = len(items) // 2
    part1_items = items[:mid]
    part2_items = items[mid:]

    part1_title = base_title
    part2_title = "### 新着タイムライン (続き)"

    part1_md = format_timeline_markdown(part1_items, header_title=part1_title)
    part2_md = format_timeline_markdown(part2_items, header_title=part2_title)

    return [part1_md, part2_md]


def post_to_scrap(
    scrap_slug_or_url: str,
    markdown_content: str,
    zenn_cmd: str = "zenn",
) -> str:
    """
    Zenn CLI を呼び出して既存の Scrap に新しいコメントを投稿する。
    戻り値として投稿されたコメントのURLを返す。
    """
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write(markdown_content)
        temp_file_path = f.name

    try:
        cmd = [
            zenn_cmd,
            "scrap",
            "post",
            scrap_slug_or_url,
            "--file",
            temp_file_path,
            "--machine-readable",
        ]
        logger.info(f"Zenn CLI コマンド実行: {' '.join(cmd[:4])} --file <temp> --machine-readable")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        # machine-readable はURLを行で返す
        comment_url = output.splitlines()[-1] if output else ""
        logger.info(f"Scrapコメント投稿完了: {comment_url}")
        return comment_url
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.strip() if exc.stderr else str(exc)
        logger.error(f"Zenn CLI 実行エラー: {stderr_msg}")
        raise RuntimeError(f"Failed to post scrap comment: {stderr_msg}") from exc
    finally:
        Path(temp_file_path).unlink(missing_ok=True)


def create_scrap(
    title: str,
    markdown_content: str,
    unlisted: bool = True,
    disallow_others_post: bool = True,
    topics: Optional[List[str]] = None,
    zenn_cmd: str = "zenn",
) -> str:
    """
    Zenn CLI を呼び出して新規 Scrap を作成する。
    戻り値として作成された Scrap の URL を返す。
    """
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write(markdown_content)
        temp_file_path = f.name

    try:
        cmd = [
            zenn_cmd,
            "scrap",
            "create",
            "--title",
            title,
            "--file",
            temp_file_path,
            "--machine-readable",
        ]
        if unlisted:
            cmd.append("--unlisted")
        if disallow_others_post:
            cmd.append("--disallow-others-post")
        if topics:
            cmd.extend(["--topics", ",".join(topics)])

        logger.info(f"Zenn CLI コマンド実行: {' '.join(cmd[:6])} ...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        scrap_url = output.splitlines()[-1] if output else ""
        logger.info(f"Scrap作成完了: {scrap_url}")
        return scrap_url
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.strip() if exc.stderr else str(exc)
        logger.error(f"Zenn CLI 実行エラー: {stderr_msg}")
        raise RuntimeError(f"Failed to create scrap: {stderr_msg}") from exc
    finally:
        Path(temp_file_path).unlink(missing_ok=True)


def get_scrap_details(scrap_slug_or_url: str, zenn_cmd: str = "zenn") -> dict:
    """
    Zenn CLI を呼び出して Scrap の詳細およびコメント一覧を取得する。
    """
    cmd = [
        zenn_cmd,
        "scrap",
        "get",
        scrap_slug_or_url,
        "--machine-readable",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.strip() if exc.stderr else str(exc)
        logger.error(f"Zenn CLI scrap get エラー: {stderr_msg}")
        raise RuntimeError(f"Failed to get scrap details: {stderr_msg}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse scrap get output as JSON: {exc}") from exc


def delete_scrap_comment(
    scrap_slug_or_url: str,
    comment_slug: str,
    zenn_cmd: str = "zenn",
) -> bool:
    """
    Zenn CLI を呼び出して特定のコメントを削除する。
    """
    cmd = [
        zenn_cmd,
        "scrap",
        "delete-comment",
        scrap_slug_or_url,
        comment_slug,
        "--yes",
        "--machine-readable",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Scrapコメント削除完了: slug={comment_slug}")
        return True
    except subprocess.CalledProcessError as exc:
        stderr_msg = exc.stderr.strip() if exc.stderr else str(exc)
        logger.warning(f"Zenn CLI delete-comment エラー ({comment_slug}): {stderr_msg}")
        return False


def delete_old_timeline_comments(
    scrap_slug_or_url: str,
    keep_root: bool = True,
    zenn_cmd: str = "zenn",
) -> int:
    """
    Scrap 内の古いコメントを削除する。
    keep_root=True の場合、最初の投稿（コメント #0: 説明用投稿）は残し、
    2番目以降のコメント（過去のタイムライン）のみを削除する。
    削除したコメント数を返す。
    """
    try:
        details = get_scrap_details(scrap_slug_or_url, zenn_cmd=zenn_cmd)
    except Exception as exc:
        logger.warning(f"既存コメント一覧の取得に失敗したため、古いコメントの削除をスキップします: {exc}")
        return 0

    comments = details.get("comments", [])
    if not comments:
        return 0

    # keep_root=True なら最初のコメント（インデックス0）は説明用として保護
    targets = comments[1:] if keep_root else comments
    if not targets:
        logger.info("削除対象の古いタイムラインコメントはありません。")
        return 0

    logger.info(f"古いタイムラインコメント {len(targets)} 件を削除中...")
    deleted_count = 0
    for c in targets:
        c_slug = c.get("slug")
        if c_slug and delete_scrap_comment(scrap_slug_or_url, c_slug, zenn_cmd=zenn_cmd):
            deleted_count += 1

    logger.info(f"古いタイムラインコメントのクリーンアップ完了: {deleted_count} 件削除")
    return deleted_count


