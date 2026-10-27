#!/usr/bin/env bash
"""
最新記事をクロールし、完全新着タイムラインを作成して Zenn Scrap に投稿するスクリプト
"""

import argparse
from datetime import datetime, timezone, timedelta
import logging
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from zenn_stats_crawler.client import RateLimitedClient
from zenn_stats_crawler.config import Config
from zenn_stats_crawler.timeline import (
    crawl_recent_timeline_items,
    create_scrap,
    format_timeline_markdown,
    post_to_scrap,
    split_markdown_for_scrap,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# JST (UTC+9) タイムゾーン
JST = timezone(timedelta(hours=9))


def main():
    parser = argparse.ArgumentParser(description="Zenn 完全新着タイムライン自動生成・投稿ツール")
    parser.add_argument(
        "--scrap",
        type=str,
        default=os.getenv("ZENN_TIMELINE_SCRAP_SLUG") or os.getenv("ZENN_SCRAP_SLUG"),
        help="投稿先の既存ScrapのslugまたはURL (環境変数 ZENN_TIMELINE_SCRAP_SLUG でも指定可能)",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="新しい限定公開Scrapを作成してタイムラインを初期投稿する",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Zenn 最新記事タイムライン (定点観測)",
        help="新規Scrap作成時のタイトル (デフォルト: 'Zenn 最新記事タイムライン (定点観測)')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="クロールする最新記事数 (デフォルト: 100)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Markdown出力先ファイルパス (任意)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrapへの投稿を行わず、生成結果の出力のみを行う",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="プログレスバーを非表示にする",
    )

    args = parser.parse_args()

    config = Config.from_env()
    client = RateLimitedClient(config)

    # 1. 最新記事のクロール
    logger.info(f"最新記事のクロールを開始します (最大 {args.limit} 件)...")
    items = crawl_recent_timeline_items(
        client=client,
        config=config,
        limit=args.limit,
        show_progress=not args.quiet,
    )

    if not items:
        logger.warning("クロール結果が0件でした。終了します。")
        return

    now_jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")
    header_title = f"### 📅 {now_jst} 観測分 (最新 {len(items)} 件)"

    # 2. Markdownファイルの保存 (指定時)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        full_md = format_timeline_markdown(items, header_title=header_title)
        out_path.write_text(full_md, encoding="utf-8")
        logger.info(f"Markdownレポートを保存しました: {out_path}")

    # 3. dry-run の場合は出力して終了
    if args.dry_run:
        full_md = format_timeline_markdown(items, header_title=header_title)
        if not args.output:
            print("\n" + full_md)
        logger.info("dry-run モードのため、Scrapへの投稿はスキップしました。")
        return

    # 4. 新規Scrapの作成 (--create)
    if args.create:
        logger.info(f"新規限定公開Scrapを作成中: タイトル='{args.title}'")
        chunks = split_markdown_for_scrap(items, base_title=header_title)
        initial_content = chunks[0]
        
        scrap_url = create_scrap(
            title=args.title,
            markdown_content=initial_content,
            unlisted=True,
            disallow_others_post=True,
            topics=["zenn"],
        )
        logger.info(f"✅ 限定公開Scrapを作成しました: {scrap_url}")
        
        # 2分割された場合の後半コメントを投稿
        if len(chunks) > 1:
            slug = scrap_url.rstrip("/").split("/")[-1]
            logger.info("分割された後半テーブルを追記コメントとして投稿中...")
            comment_url = post_to_scrap(slug, chunks[1])
            logger.info(f"✅ 後半コメントを投稿しました: {comment_url}")

        print(f"\n[Scrap URL]: {scrap_url}")
        print("次回以降はこのScrapに追記するために環境変数または引数で以下を指定してください:")
        print(f"export ZENN_TIMELINE_SCRAP_SLUG=\"{scrap_url.rstrip('/').split('/')[-1]}\"")
        return

    # 5. 既存Scrapへの追記投稿 (--scrap または環境変数)
    if args.scrap:
        logger.info(f"既存Scrap ({args.scrap}) へ新着タイムラインをコメント投稿中...")
        chunks = split_markdown_for_scrap(items, base_title=header_title)
        
        for idx, chunk in enumerate(chunks, 1):
            comment_url = post_to_scrap(args.scrap, chunk)
            logger.info(f"✅ コメント投稿成功 ({idx}/{len(chunks)}): {comment_url}")
        return

    # 6. Scrap指定もcreateも無い場合はstdoutに表示
    full_md = format_timeline_markdown(items, header_title=header_title)
    if not args.output:
        print("\n" + full_md)
    logger.info("Scrapの指定 (--scrap / --create) がないため投稿は行われませんでした。")


if __name__ == "__main__":
    main()
