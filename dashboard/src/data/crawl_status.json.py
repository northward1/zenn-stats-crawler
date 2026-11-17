#!/usr/bin/env python3
"""Data loader for Observable Framework: crawl freshness and recent crawl coverage."""

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def resolve_db_path() -> Path:
    env_path = os.environ.get("ZENN_STATS_DB")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[3] / "data" / "zenn_stats.db"


def parse_iso_utc(dt_str: str) -> datetime:
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def percentile(sorted_vals: list[int], q: float) -> float:
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    pos = (n - 1) * q
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return round(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac, 1)


def summarize_period(
    ages_by_period: dict[str, list[int]],
    crawl_days_by_period: dict[str, list[str]],
) -> list[dict]:
    rows = []
    for pub in sorted(ages_by_period):
        ages = sorted(ages_by_period[pub])
        cdays = crawl_days_by_period[pub]
        n = len(ages)
        within_30 = sum(1 for a in ages if a <= 30)
        rows.append(
            {
                "pub": pub,
                "count": n,
                "min_age": ages[0],
                "p25_age": percentile(ages, 0.25),
                "median_age": percentile(ages, 0.50),
                "p75_age": percentile(ages, 0.75),
                "max_age": ages[-1],
                "within_30d_pct": round(within_30 / n * 100, 1) if n else 0.0,
                "oldest_crawl_day": min(cdays),
                "latest_crawl_day": max(cdays),
            }
        )
    return rows


def build_heatmap(counts: dict[tuple[str, int], int]) -> list[dict]:
    return [
        {"pub": pub, "age_day": age_day, "count": cnt}
        for (pub, age_day), cnt in sorted(counts.items())
    ]


def main() -> None:
    db_path = resolve_db_path()
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    latest_crawled_at = cur.execute(
        "SELECT MAX(crawled_at) FROM articles WHERE status = 'success'"
    ).fetchone()[0]
    total_snapshots = cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    if not latest_crawled_at:
        json.dump(
            {
                "meta": {
                    "latest_crawled_at": None,
                    "ref_date_jst": None,
                    "total_articles": 0,
                    "total_snapshots": total_snapshots,
                    "within_30d_count": 0,
                    "max_age_days": 0,
                },
                "freshness": {
                    "monthly_heatmap": [],
                    "monthly_summary": [],
                },
                "recent_crawls": {"days": [], "by_month": []},
            },
            sys.stdout,
            ensure_ascii=False,
        )
        return

    ref_dt = parse_iso_utc(latest_crawled_at)
    ref_date_jst = ref_dt.astimezone(JST).date().isoformat()

    # 1. Latest crawl freshness per unique article
    latest_query = """
        WITH latest_articles AS (
            SELECT
                published_at,
                crawled_at,
                ROW_NUMBER() OVER (
                    PARTITION BY url_hash
                    ORDER BY crawled_at DESC, id DESC
                ) AS rn
            FROM articles
            WHERE status = 'success' AND published_at IS NOT NULL
        )
        SELECT published_at, crawled_at
        FROM latest_articles
        WHERE rn = 1
    """

    monthly_heatmap: Counter[tuple[str, int]] = Counter()
    monthly_ages: dict[str, list[int]] = defaultdict(list)
    monthly_cdays: dict[str, list[str]] = defaultdict(list)

    total_articles = 0
    within_30d_count = 0
    max_age_days = 0

    for published_at, crawled_at in cur.execute(latest_query):
        if len(published_at) < 7 or published_at[4] != "-":
            continue
        pub_month = published_at[:7]
        if pub_month < "2020-09":
            continue

        crawled_dt = parse_iso_utc(crawled_at)
        age_days = max(0, int((ref_dt - crawled_dt).total_seconds() // 86400))
        crawl_day_jst = crawled_dt.astimezone(JST).date().isoformat()

        total_articles += 1
        if age_days <= 30:
            within_30d_count += 1
        if age_days > max_age_days:
            max_age_days = age_days

        monthly_heatmap[(pub_month, age_days)] += 1
        monthly_ages[pub_month].append(age_days)
        monthly_cdays[pub_month].append(crawl_day_jst)

    # 2. Recent crawl runs (last 14 days relative to ref_dt in JST, with UTC buffer)
    recent_cutoff_utc = (
        datetime.combine(
            ref_dt.astimezone(JST).date() - timedelta(days=14),
            datetime.min.time(),
            tzinfo=JST,
        )
        .astimezone(timezone.utc)
        .isoformat()
    )

    recent_query = """
        SELECT crawled_at, published_at
        FROM articles
        WHERE status = 'success' AND published_at IS NOT NULL AND crawled_at >= ?
    """

    recent_days: set[str] = set()
    recent_by_month: Counter[tuple[str, str]] = Counter()
    cutoff_jst_date = (ref_dt.astimezone(JST).date() - timedelta(days=13)).isoformat()

    for crawled_at, published_at in cur.execute(recent_query, (recent_cutoff_utc,)):
        crawled_dt = parse_iso_utc(crawled_at)
        crawl_day_jst = crawled_dt.astimezone(JST).date().isoformat()
        if crawl_day_jst < cutoff_jst_date:
            continue

        if len(published_at) < 7 or published_at[4] != "-":
            continue
        pub_month = published_at[:7]
        if pub_month < "2020-09":
            continue

        recent_days.add(crawl_day_jst)
        recent_by_month[(crawl_day_jst, pub_month)] += 1

    conn.close()

    output = {
        "meta": {
            "latest_crawled_at": latest_crawled_at,
            "ref_date_jst": ref_date_jst,
            "total_articles": total_articles,
            "total_snapshots": total_snapshots,
            "within_30d_count": within_30d_count,
            "max_age_days": max_age_days,
        },
        "freshness": {
            "monthly_heatmap": build_heatmap(monthly_heatmap),
            "monthly_summary": summarize_period(monthly_ages, monthly_cdays),
        },
        "recent_crawls": {
            "days": sorted(recent_days),
            "by_month": [
                {"crawl_day": cday, "pub": pub, "count": cnt}
                for (cday, pub), cnt in sorted(recent_by_month.items())
            ],
        },
    }

    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
