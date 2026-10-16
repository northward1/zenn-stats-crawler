import argparse
import logging
import sys
from pathlib import Path

from zenn_stats_crawler.config import Config
from zenn_stats_crawler.crawler import StatsCrawler
from zenn_stats_crawler.db import Database


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Zenn periodic stats crawler with anonymization and SQLite persistence"
    )
    parser.add_argument(
        "-L",
        "--expire-days",
        type=float,
        default=30.0,
        help="Expiration threshold in days (default: 30.0). Articles crawled earlier than this will be re-crawled.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/zenn_stats.db"),
        help="Path to SQLite database file (default: data/zenn_stats.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of articles to crawl in this run (optional)",
    )
    parser.add_argument(
        "--max-sitemaps",
        type=int,
        default=None,
        help="Maximum number of sitemaps to fetch (optional, for testing)",
    )
    parser.add_argument(
        "--include-books",
        action="store_true",
        help="Include book sitemaps (books*.xml.gz) as well as articles",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check target article counts without sending crawl requests or writing to DB",
    )
    parser.add_argument(
        "--success-only-expire",
        action="store_true",
        help="Only count successful crawls when checking expiration (re-crawl previously failed URLs immediately)",
    )
    parser.add_argument(
        "--mail",
        type=str,
        default=None,
        help="Contact email address for User-Agent header (overrides MAIL_ADDRESS env var)",
    )
    parser.add_argument(
        "--salt",
        type=str,
        default=None,
        help="Salt string for SHA-256 anonymization (overrides HASH_SALT env var)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress bar and summary output (ideal for cron or CI)",
    )
    parser.add_argument(
        "--progress",
        dest="show_progress",
        action="store_true",
        default=None,
        help="Force show progress bar (e.g. combined with --log-level ERROR)",
    )
    parser.add_argument(
        "--no-progress",
        dest="show_progress",
        action="store_false",
        help="Hide progress bar",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    config = Config.from_env(
        db_path=args.db_path,
        mail=args.mail,
        salt=args.salt,
    )

    sitemap_pattern = (
        r"/(article|books?)\d*\.xml(\.gz)?$"
        if args.include_books
        else r"/article\d*\.xml(\.gz)?$"
    )

    db = Database(config.db_path)
    crawler = StatsCrawler(config=config, db=db)

    # プログレスバーの表示制御
    if args.show_progress is not None:
        show_progress = args.show_progress
    elif args.quiet or args.log_level in ["ERROR", "CRITICAL"]:
        show_progress = False
    else:
        show_progress = True

    try:
        stats = crawler.run(
            expire_days=args.expire_days,
            limit=args.limit,
            max_sitemaps=args.max_sitemaps,
            sitemap_pattern=sitemap_pattern,
            dry_run=args.dry_run,
            success_only_for_expire=args.success_only_expire,
            show_progress=show_progress,
        )
        if not args.quiet:
            print("\n=== クロール結果サマリー ===")
            print(f"サイトマップ内URL総数 : {stats['total_found']}")
            print(f"スキップ数 (期限内)   : {stats['skipped']}")
            print(f"対象URL数             : {stats['targets']}")
            if not args.dry_run:
                print(f"成功数                : {stats['crawled_success']}")
                print(f"失敗数                : {stats['crawled_failed']}")
    except KeyboardInterrupt:
        print("\nユーザーにより中断されました。")
        sys.exit(130)
    finally:
        db.close()


if __name__ == "__main__":
    main()
