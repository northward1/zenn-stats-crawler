#!/usr/bin/env python3
"""Data loader for Observable Framework: aggregates Zenn stats from SQLite."""

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def gini(values: list[int]) -> float | None:
    n = len(values)
    if n == 0:
        return None
    s = sum(values)
    if s == 0:
        return 0.0
    sorted_vals = sorted(values)
    weighted = sum((2 * i - n + 1) * x for i, x in enumerate(sorted_vals))
    return round(weighted / (n * s), 4)


def freq_to_list(counter: Counter[int]) -> list[list[int]]:
    """Return [[likes, article_count], ...] sorted by likes ascending."""
    return [[k, counter[k]] for k in sorted(counter)]


def resolve_db_path() -> Path:
    env_path = os.environ.get("ZENN_STATS_DB")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parents[3] / "data" / "zenn_stats.db"


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

    monthly_count = defaultdict(int)
    daily_count = defaultdict(int)
    monthly_authors = defaultdict(set)
    monthly_auth_sum = defaultdict(int)
    monthly_total_sum = defaultdict(int)

    auth_freq = defaultdict(Counter)
    total_freq = defaultdict(Counter)
    all_auth_freq: Counter[int] = Counter()
    all_total_freq: Counter[int] = Counter()

    monthly_type_count = defaultdict(lambda: defaultdict(int))
    monthly_type_auth = defaultdict(lambda: defaultdict(int))
    monthly_type_total = defaultdict(lambda: defaultdict(int))

    pub_auth_vals = defaultdict(lambda: defaultdict(list))
    pub_total_vals = defaultdict(lambda: defaultdict(list))

    topic_stats = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))

    query = """
        SELECT
            published_at,
            article_type,
            user_name_hash,
            COALESCE(authenticated_liked_count, 0),
            COALESCE(liked_count, 0),
            topics,
            publication_plan,
            publication_name_hash
        FROM articles
        WHERE status = 'success' AND published_at IS NOT NULL
    """

    total_articles = 0
    for (
        published_at,
        article_type,
        user_hash,
        auth_likes,
        total_likes,
        topics_raw,
        pub_plan,
        pub_hash,
    ) in cur.execute(query):
        if len(published_at) < 7:
            continue
        month = published_at[:7]
        if month[4] != "-" or month < "2020-09":
            # Skip malformed dates and backdated imports prior to Zenn's launch (2020-09)
            continue

        total_articles += 1
        if len(published_at) >= 10 and published_at[7] == "-":
            day = published_at[:10]
            daily_count[day] += 1
        auth_likes = max(0, int(auth_likes))
        total_likes = max(0, int(total_likes))

        monthly_count[month] += 1
        if user_hash:
            monthly_authors[month].add(user_hash)
        monthly_auth_sum[month] += auth_likes
        monthly_total_sum[month] += total_likes

        auth_freq[month][auth_likes] += 1
        total_freq[month][total_likes] += 1
        all_auth_freq[auth_likes] += 1
        all_total_freq[total_likes] += 1

        atype = article_type if article_type in ("tech", "idea") else "other"
        monthly_type_count[month][atype] += 1
        monthly_type_auth[month][atype] += auth_likes
        monthly_type_total[month][atype] += total_likes

        pub_group = "無所属" if pub_hash is None else (pub_plan or "other")
        pub_auth_vals[month][pub_group].append(auth_likes)
        pub_total_vals[month][pub_group].append(total_likes)

        if topics_raw:
            try:
                topics = json.loads(topics_raw)
                if isinstance(topics, list):
                    for t in topics:
                        if isinstance(t, str) and t:
                            entry = topic_stats[month][t]
                            entry[0] += 1
                            entry[1] += auth_likes
                            entry[2] += total_likes
            except json.JSONDecodeError:
                pass

    conn.close()

    daily = []
    max_date_str = max(daily_count.keys()) if daily_count else None
    if max_date_str:
        max_d = date.fromisoformat(max_date_str)
        start_d = max_d - timedelta(days=399)
        for i in range(400):
            d_str = (start_d + timedelta(days=i)).isoformat()
            daily.append({"date": d_str, "articles": daily_count[d_str]})

    months = sorted(monthly_count.keys())

    monthly = []
    tech_idea = []
    publications = []
    topic_ranks_count = []
    topic_ranks_auth = []
    topic_ranks_total = []

    for m in months:
        cnt = monthly_count[m]
        a_sum = monthly_auth_sum[m]
        t_sum = monthly_total_sum[m]
        monthly.append(
            {
                "month": m,
                "articles": cnt,
                "authors": len(monthly_authors[m]),
                "auth_likes_sum": a_sum,
                "auth_likes_avg": round(a_sum / cnt, 2) if cnt else 0,
                "total_likes_sum": t_sum,
                "total_likes_avg": round(t_sum / cnt, 2) if cnt else 0,
            }
        )

        for atype in ("tech", "idea"):
            c_t = monthly_type_count[m][atype]
            a_t = monthly_type_auth[m][atype]
            tot_t = monthly_type_total[m][atype]
            tech_idea.append(
                {
                    "month": m,
                    "type": atype,
                    "articles": c_t,
                    "articles_pct": round(c_t / cnt * 100, 2) if cnt else 0,
                    "auth_likes": a_t,
                    "auth_likes_pct": round(a_t / a_sum * 100, 2) if a_sum else 0,
                    "total_likes": tot_t,
                    "total_likes_pct": round(tot_t / t_sum * 100, 2) if t_sum else 0,
                }
            )

        for pg, a_vals in sorted(pub_auth_vals[m].items()):
            t_vals = pub_total_vals[m][pg]
            n_pg = len(a_vals)
            a_s = sum(a_vals)
            t_s = sum(t_vals)
            a_zero = sum(1 for v in a_vals if v == 0)
            t_zero = sum(1 for v in t_vals if v == 0)
            publications.append(
                {
                    "month": m,
                    "group": pg,
                    "articles": n_pg,
                    "auth_likes_sum": a_s,
                    "auth_likes_avg": round(a_s / n_pg, 2) if n_pg else 0,
                    "auth_zero_pct": round(a_zero / n_pg * 100, 2) if n_pg else 0,
                    "auth_gini": gini(a_vals),
                    "total_likes_sum": t_s,
                    "total_likes_avg": round(t_s / n_pg, 2) if n_pg else 0,
                    "total_zero_pct": round(t_zero / n_pg * 100, 2) if n_pg else 0,
                    "total_gini": gini(t_vals),
                }
            )

        t_items = list(topic_stats[m].items())
        for rank, (topic, vals) in enumerate(
            sorted(t_items, key=lambda kv: (-kv[1][0], kv[0]))[:12], start=1
        ):
            topic_ranks_count.append(
                {"month": m, "topic": topic, "rank": rank, "value": vals[0]}
            )
        for rank, (topic, vals) in enumerate(
            sorted(t_items, key=lambda kv: (-kv[1][1], kv[0]))[:12], start=1
        ):
            topic_ranks_auth.append(
                {"month": m, "topic": topic, "rank": rank, "value": vals[1]}
            )
        for rank, (topic, vals) in enumerate(
            sorted(t_items, key=lambda kv: (-kv[1][2], kv[0]))[:12], start=1
        ):
            topic_ranks_total.append(
                {"month": m, "topic": topic, "rank": rank, "value": vals[2]}
            )

    like_freq = {
        "auth": {"ALL": freq_to_list(all_auth_freq)},
        "total": {"ALL": freq_to_list(all_total_freq)},
    }
    for m in months:
        like_freq["auth"][m] = freq_to_list(auth_freq[m])
        like_freq["total"][m] = freq_to_list(total_freq[m])

    output = {
        "meta": {
            "total_articles": total_articles,
            "latest_crawled_at": latest_crawled_at,
            "min_month": months[0] if months else None,
            "max_month": months[-1] if months else None,
            "max_date": max_date_str,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "months": months,
        "monthly": monthly,
        "daily": daily,
        "tech_idea": tech_idea,
        "publications": publications,
        "topics": {
            "count": topic_ranks_count,
            "auth": topic_ranks_auth,
            "total": topic_ranks_total,
        },
        "like_freq": like_freq,
    }

    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
