---
title: クロール状況
toc: true
---

# クロール状況

<style>
  :root {
    --observablehq-max-width: 1400px;
  }
  p {
    max-width: none;
  }
</style>

[northward1/zenn-stats-crawler](https://github.com/northward1/zenn-stats-crawler)で収集しているデータの取得日時や直近のクロール対象範囲を確認するためのページです。

```js
const data = await FileAttachment("data/crawl_status.json").json();
const fmtJst = (iso) =>
  iso
    ? new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })
    : "-";
const parseMonth = (m) => new Date(`${m}-01T00:00:00Z`);
const within30Pct =
  data.meta.total_articles > 0
    ? ((data.meta.within_30d_count / data.meta.total_articles) * 100).toFixed(1)
    : "0.0";
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>最終クロール日時 (JST)</h2>
    <span class="big">${fmtJst(data.meta.latest_crawled_at)}</span>
  </div>
  <div class="card">
    <h2>ユニーク記事数 / 総履歴数</h2>
    <span class="big">${data.meta.total_articles.toLocaleString("ja-JP")}</span>
    <span class="muted">スナップショット計 ${data.meta.total_snapshots.toLocaleString("ja-JP")} 件</span>
  </div>
  <div class="card">
    <h2>30日以内更新率</h2>
    <span class="big">${within30Pct}%</span>
    <span class="muted">${data.meta.within_30d_count.toLocaleString("ja-JP")} 件が30日以内</span>
  </div>
  <div class="card">
    <h2>最大経過日数</h2>
    <span class="big">${data.meta.max_age_days} 日</span>
    <span class="muted">基準日: ${data.meta.ref_date_jst} (JST)</span>
  </div>
</div>

---

## 1. 最後のクロールから経過した日数

各記事の最新クロール日時が、最終クロール日時から何日前かを集計しています。

```js
const freshnessView = view(
  Inputs.radio(["heatmap", "range"], {
    label: "表示形式",
    value: "heatmap",
    format: (d) =>
      d === "heatmap" ? "ヒートマップ" : "範囲チャート (最小〜最大・四分位)",
  })
);
```

```js
const heatmapRows = data.freshness.monthly_heatmap.map((d) => ({
  ...d,
  pubDate: parseMonth(d.pub),
}));

const summaryRows = data.freshness.monthly_summary.map((d) => ({
  ...d,
  pubDate: parseMonth(d.pub),
}));
```

```js
(() => {
  if (freshnessView === "heatmap") {
    return Plot.plot({
      height: 420,
      marginLeft: 55,
      marginBottom: 40,
      x: { label: "投稿月", type: "utc" },
      y: {
        label: "最新クロールからの経過日数 (日)",
        grid: true,
        domain: [0, Math.max(35, data.meta.max_age_days + 1)],
      },
      color: {
        type: "sqrt",
        scheme: "YlGnBu",
        legend: true,
        label: "記事数",
      },
      marks: [
        Plot.rect(heatmapRows, {
          x: "pubDate",
          interval: "month",
          y1: "age_day",
          y2: (d) => d.age_day + 1,
          fill: "count",
          tip: {
            format: {
              x: "%Y/%m",
              y1: (d) => `${d} 日前`,
              y2: false,
            },
          },
        }),
        Plot.ruleY([30], {
          stroke: "#ef4444",
          strokeWidth: 1.5,
          strokeDasharray: "4,4",
        }),
      ],
    });
  }

  return Plot.plot({
    height: 420,
    marginLeft: 55,
    marginBottom: 40,
    x: { label: "投稿月", type: "utc" },
    y: {
      label: "最新クロールからの経過日数 (日)",
      grid: true,
      domain: [0, Math.max(35, data.meta.max_age_days + 1)],
    },
    marks: [
      Plot.link(summaryRows, {
        x1: "pubDate",
        x2: "pubDate",
        y1: "min_age",
        y2: "max_age",
        stroke: "#94a3b8",
        strokeWidth: 1.5,
      }),
      Plot.link(summaryRows, {
        x1: "pubDate",
        x2: "pubDate",
        y1: "p25_age",
        y2: "p75_age",
        stroke: "#3b82f6",
        strokeWidth: 6,
        strokeOpacity: 0.75,
      }),
      Plot.dot(summaryRows, {
        x: "pubDate",
        y: "median_age",
        fill: "#1d4ed8",
        r: 3,
        channels: {
          記事数: "count",
          "30日以内率(%)": "within_30d_pct",
          最新クロール日: "latest_crawl_day",
          最古クロール日: "oldest_crawl_day",
          最小経過日: "min_age",
          最大経過日: "max_age",
        },
        tip: {
          format: {
            x: "%Y/%m",
            y: (d) => `中央値 ${d} 日`,
          },
        },
      }),
      Plot.ruleY([30], {
        stroke: "#ef4444",
        strokeWidth: 1.5,
        strokeDasharray: "4,4",
      }),
    ],
  });
})()
```

---

## 2. 直近数日のクロール対象「投稿日」分布

直近のクロール実行日ごとに、どの時期に投稿された記事を何件取得したかを示します。

```js
const recentWindowDays = view(
  Inputs.radio([1, 3, 7, 14], {
    label: "表示する直近期間",
    value: 7,
    format: (d) => `直近 ${d} 日`,
  })
);
```

```js
const allCrawlDays = data.recent_crawls.days;
const targetCrawlDays = new Set(allCrawlDays.slice(-recentWindowDays));

const recentDistRows = data.recent_crawls.by_month
  .filter((d) => targetCrawlDays.has(d.crawl_day))
  .map((d) => ({
    ...d,
    pubDate: parseMonth(d.pub),
  }));
```

```js
Plot.plot({
  height: 360,
  marginLeft: 60,
  marginBottom: 40,
  x: { label: "投稿月", type: "utc" },
  y: { label: "クロール件数 (成功)", grid: true },
  color: {
    type: "ordinal",
    scheme: "tableau10",
    legend: true,
    label: "クロール日 (JST)",
  },
  marks: [
    Plot.rectY(
      recentDistRows,
      Plot.stackY({
        x: "pubDate",
        interval: "month",
        y: "count",
        fill: "crawl_day",
        tip: {
          format: {
            x: "%Y/%m",
          },
        },
      })
    ),
    Plot.ruleY([0]),
  ],
})
```
