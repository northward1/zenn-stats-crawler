from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Dict, List, Optional
import requests
from tqdm import tqdm

from zenn_stats_crawler.anonymizer import hash_text
from zenn_stats_crawler.client import RateLimitedClient
from zenn_stats_crawler.config import Config
from zenn_stats_crawler.db import Database
from zenn_stats_crawler.parser import ArticleParseError, parse_article_data
from zenn_stats_crawler.sitemap import SitemapCrawler
from zenn_stats_crawler.url import normalize_url

logger = logging.getLogger(__name__)


class StatsCrawler:
    """
    MEMO.md に基づく定期統計データ収集クローラー
    - 期限 L (expire_days) より前に取得されたURL、または未取得URLをクロール
    - 履歴推移をすべてSQLiteに追記
    - エラー発生時もDBに記録
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        db: Optional[Database] = None,
        client: Optional[RateLimitedClient] = None,
    ):
        self.config = config or Config.from_env()
        self.db = db or Database(self.config.db_path)
        self.client = client or RateLimitedClient(self.config)
        self.sitemap_crawler = SitemapCrawler(self.client)

    def fetch_all_urls_from_sitemaps(
        self,
        max_sitemaps: Optional[int] = None,
        sitemap_pattern: str = r"/article\d*\.xml(\.gz)?$",
        show_progress: bool = True,
    ) -> List[str]:
        """
        サイトマップインデックスから個別サイトマップを取得し、すべてのURLを抽出・正規化して返す。
        新しい記事から優先的にクロールするため、サイトマップおよびサイトマップ内のURLを逆順（最新順）で走査する。
        """
        logger.info(
            f"サイトマップインデックスを取得中: {self.config.sitemap_index_url}"
        )
        sitemap_urls = self.sitemap_crawler.fetch_sitemap_urls(
            self.config.sitemap_index_url, pattern=sitemap_pattern
        )

        # 新しい記事を含む最新のサイトマップから順に走査するために逆順にする
        sitemap_urls.reverse()

        if max_sitemaps is not None and max_sitemaps > 0:
            sitemap_urls = sitemap_urls[:max_sitemaps]
            logger.info(f"サイトマップ数を最新 {max_sitemaps} 件に制限しました。")

        all_urls: List[str] = []
        seen = set()

        for s_url in tqdm(
            sitemap_urls, desc="サイトマップ走査", disable=not show_progress
        ):
            try:
                items = self.sitemap_crawler.fetch_urls_from_sitemap(s_url)
                # サイトマップ内の新しい記事（末尾側）から走査するために逆順にする
                for item in reversed(items):
                    norm = normalize_url(item.loc)
                    if norm and norm not in seen:
                        seen.add(norm)
                        all_urls.append(norm)
            except Exception as exc:
                logger.warning(
                    f"サイトマップの取得・パースに失敗しました ({s_url}): {exc}"
                )

        logger.info(
            f"全サイトマップから合計 {len(all_urls)} 件のユニークURLを収集しました。"
        )
        return all_urls

    def run(
        self,
        expire_days: float = 30.0,
        limit: Optional[int] = None,
        max_sitemaps: Optional[int] = None,
        sitemap_pattern: str = r"/article\d*\.xml(\.gz)?$",
        dry_run: bool = False,
        success_only_for_expire: bool = False,
        show_progress: bool = True,
    ) -> Dict[str, int]:
        """
        定期クロールを実行する。

        :param expire_days: 期限 L (日数)。直近の取得日時がこれより古い場合、または未取得の場合に再取得する
        :param limit: 今回取得する最大記事数
        :param max_sitemaps: 取得対象とするサイトマップの最大数 (テスト・デバッグ用)
        :param sitemap_pattern: 対象とするサイトマップURLの正規表現 (将来のbook拡張等)
        :param dry_run: 実際のアクセスとDB挿入を行わず、対象件数の見積もりのみ行う
        :param success_only_for_expire: Trueの場合、失敗レコードは最終取得日時に含めず、成功日時のみを基準に期限判定する
        :param show_progress: プログレスバーを表示するかどうか
        """
        now = datetime.now(timezone.utc)
        threshold_time = now - timedelta(days=expire_days)
        logger.info(
            f"クロール条件: 期限 L = {expire_days} 日 (基準日時: {threshold_time.isoformat()})"
        )

        # 1. サイトマップ走査
        urls = self.fetch_all_urls_from_sitemaps(
            max_sitemaps=max_sitemaps,
            sitemap_pattern=sitemap_pattern,
            show_progress=show_progress,
        )

        # 2. DBから最新取得日時のマップを取得
        latest_crawled_map = self.db.get_latest_crawled_map(
            success_only=success_only_for_expire
        )
        logger.info(f"DB内の既存URLハッシュ数: {len(latest_crawled_map)} 件")

        # 3. 期限判定によるフィルタリング
        target_urls: List[str] = []
        skipped_count = 0

        for u in urls:
            u_hash = hash_text(u, self.config.hash_salt)
            latest_time = latest_crawled_map.get(u_hash)

            if latest_time is None:
                # DBに未登録のURL -> クロール対象
                target_urls.append(u)
            elif latest_time < threshold_time:
                # 最終取得日時が L より前 -> 再取得対象
                target_urls.append(u)
            else:
                # 期限内のためスキップ
                skipped_count += 1

        logger.info(
            f"対象URL判定結果: 対象={len(target_urls)} 件 (未取得 or 期限切れ), スキップ={skipped_count} 件 (期限内)"
        )

        if limit is not None and limit > 0:
            target_urls = target_urls[:limit]
            logger.info(
                f"取得上限数 (--limit) により、先頭 {limit} 件に絞り込みました。"
            )

        stats = {
            "total_found": len(urls),
            "skipped": skipped_count,
            "targets": len(target_urls),
            "crawled_success": 0,
            "crawled_failed": 0,
        }

        if dry_run:
            logger.info("Dry-run モードのため、クロールを実行せずに終了します。")
            return stats

        # 4. クロール実行
        logger.info(f"記事クロールを開始します (対象: {len(target_urls)} 件)")

        with tqdm(
            total=len(target_urls), desc="記事データ取得", disable=not show_progress
        ) as pbar:
            for url in target_urls:
                norm_url = normalize_url(url)
                u_hash = hash_text(norm_url, self.config.hash_salt)

                http_status = None
                try:
                    # リクエスト送信
                    response = self.client.get(norm_url)
                    http_status = response.status_code
                    html_text = response.text

                    # パース & ハッシュ化
                    article_data = parse_article_data(
                        html=html_text,
                        url=norm_url,
                        salt=self.config.hash_salt,
                        crawled_at=datetime.now(timezone.utc).isoformat(),
                    )

                    # DB挿入 (推移として追記)
                    self.db.insert_article_snapshot(
                        data=article_data,
                        status="success",
                        http_status=http_status,
                    )
                    stats["crawled_success"] += 1

                except requests.HTTPError as http_err:
                    status_code = getattr(http_err.response, "status_code", None)
                    error_msg = f"HTTP Error: {http_err}"
                    logger.warning(f"記事取得失敗 ({norm_url}): {error_msg}")
                    self.db.insert_failed_snapshot(
                        url_hash=u_hash,
                        error_message=error_msg,
                        http_status=status_code,
                    )
                    stats["crawled_failed"] += 1

                except ArticleParseError as parse_err:
                    error_msg = f"Parse Error: {parse_err}"
                    logger.warning(f"記事パース失敗 ({norm_url}): {error_msg}")
                    self.db.insert_failed_snapshot(
                        url_hash=u_hash,
                        error_message=error_msg,
                        http_status=http_status or 200,
                    )
                    stats["crawled_failed"] += 1

                except Exception as exc:
                    error_msg = f"Unexpected Error: {exc}"
                    logger.warning(f"記事取得・処理中エラー ({norm_url}): {error_msg}")
                    self.db.insert_failed_snapshot(
                        url_hash=u_hash,
                        error_message=error_msg,
                        http_status=http_status,
                    )
                    stats["crawled_failed"] += 1

                finally:
                    pbar.set_postfix(
                        {
                            "成功": stats["crawled_success"],
                            "失敗": stats["crawled_failed"],
                        }
                    )
                    pbar.update(1)

        logger.info(
            f"クロール完了: 成功={stats['crawled_success']} 件, 失敗={stats['crawled_failed']} 件"
        )
        return stats
