---
title: Zenn統計ダッシュボード
toc: true
---

# Zenn統計ダッシュボード

<style>
  :root {
    --observablehq-max-width: 1400px;
  }
  p {
    max-width: none;
  }
</style>

このページにあるグラフは、[northward1/zenn-stats-crawler](https://github.com/northward1/zenn-stats-crawler)で収集したデータを使用しています。  
データの詳細については、上記のリポジトリを確認してください。

```js
const data = await FileAttachment("data/stats.json").json();
const months = data.months;
const parseMonth = (m) => new Date(`${m}-01T00:00:00Z`);
const parseDate = (d) => new Date(`${d}T00:00:00Z`);
const fmtMonth = (m) => (m ? m.replace("-", "/") : "-");
const fmtJst = (iso) =>
  iso
    ? new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })
    : "-";
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>集計対象記事数 (2020-09〜)</h2>
    <span class="big">${data.meta.total_articles.toLocaleString("ja-JP")}</span>
  </div>
  <div class="card">
    <h2>対象期間</h2>
    <span class="big">${fmtMonth(data.meta.min_month)} 〜 ${fmtMonth(data.meta.max_month)}</span>
  </div>
  <div class="card">
    <h2>最終クロール日時 (JST)</h2>
    <span class="big">${fmtJst(data.meta.latest_crawled_at)}</span>
  </div>
</div>

```js
const isAuth = likeMode === "auth";
const likeLabel = isAuth ? "ユーザーLike数" : "合計Like数";

const monthlyData = data.monthly.map((d) => ({
  ...d,
  date: parseMonth(d.month),
  year: d.month.slice(0, 4),
  monthNum: Number(d.month.slice(5, 7)),
  likes_sum: isAuth ? d.auth_likes_sum : d.total_likes_sum,
  likes_avg: isAuth ? d.auth_likes_avg : d.total_likes_avg,
}));
```

---

## 1. 基本的な内容

```js
const overviewMode = view(
  Inputs.radio(["timeline", "yearly"], {
    label: "表示形式",
    value: "timeline",
    format: (d) =>
      d === "timeline" ? "時系列推移" : "年別比較 (1〜12月)",
  })
);
```

```js
function renderOverviewChart(field, yLabel, color, marginLeft = 55) {
  if (overviewMode === "timeline") {
    return Plot.plot({
      height: 280,
      marginLeft,
      x: { label: null, type: "utc" },
      y: { label: yLabel, grid: true },
      marks: [
        Plot.areaY(monthlyData, {
          x: "date",
          y: field,
          fill: color,
          fillOpacity: 0.2,
        }),
        Plot.lineY(monthlyData, {
          x: { value: "date", label: "月" },
          y: field,
          stroke: color,
          strokeWidth: 2,
          tip: { format: { x: "%Y/%m" } },
        }),
        Plot.ruleY([0]),
      ],
    });
  }
  return Plot.plot({
    height: 280,
    marginLeft,
    x: {
      label: "月",
      domain: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
      tickFormat: (d) => `${d}月`,
    },
    y: { label: yLabel, grid: true },
    color: { type: "ordinal", legend: true, scheme: "tableau10" },
    marks: [
      Plot.lineY(monthlyData, {
        x: "monthNum",
        y: field,
        stroke: { value: "year", label: "年" },
        strokeWidth: 2,
        marker: "dot",
        tip: { format: { x: (d) => `${d}月` } },
      }),
      Plot.ruleY([0]),
    ],
  });
}
```

<div class="grid grid-cols-2">
  <div class="card">
    <h3>投稿件数</h3>
    ${renderOverviewChart("articles", "記事数", "#3ea8ff", 55)}
  </div>

  <div class="card">
    <h3>著者数</h3>
    ${renderOverviewChart("authors", "ユニーク著者数", "#10b981", 55)}
  </div>

  <div class="card">
    <h3>合計${likeLabel}</h3>
    ${renderOverviewChart("likes_sum", likeLabel, "#f59e0b", 65)}
  </div>

  <div class="card">
    <h3>平均${likeLabel}</h3>
    ${renderOverviewChart("likes_avg", `平均${likeLabel}`, "#8b5cf6", 50)}
  </div>
</div>

```js
const recentDaysWindow = view(
  Inputs.radio(["14", "30", "90", "180", "365"], {
    label: "直近N日の表示期間",
    value: "90",
    format: (d) => `直近 ${d} 日`,
  })
);
```

```js
const dailyWithMa = (data.daily || []).map((d, i, arr) => {
  const start = Math.max(0, i - 6);
  const windowSlice = arr.slice(start, i + 1);
  const ma7 =
    windowSlice.reduce((sum, item) => sum + item.articles, 0) /
    windowSlice.length;
  return {
    ...d,
    dateObj: parseDate(d.date),
    ma7: Math.round(ma7 * 10) / 10,
  };
});

const recentDailyData = dailyWithMa.slice(-Number(recentDaysWindow));
```

<div class="grid grid-cols-1">
  <div class="card">
    <h3>直近 ${recentDaysWindow} 日間の投稿件数推移（日別・7日移動平均）</h3>
    ${Plot.plot({
      width: 1200,
      height: 300,
      marginLeft: 55,
      x: { label: null, type: "utc" },
      y: { label: "記事数", grid: true },
      color: {
        domain: ["日別投稿件数", "7日移動平均"],
        range: ["#3ea8ff", "#f97316"],
        legend: true,
      },
      marks: [
        Plot.areaY(recentDailyData, {
          x: "dateObj",
          y: "articles",
          fill: "#3ea8ff",
          fillOpacity: 0.18,
        }),
        Plot.lineY(recentDailyData, {
          x: "dateObj",
          y: "articles",
          stroke: () => "日別投稿件数",
          strokeWidth: 1.5,
          strokeOpacity: 0.75,
        }),
        Plot.lineY(recentDailyData, {
          x: "dateObj",
          y: "ma7",
          stroke: () => "7日移動平均",
          strokeWidth: 2.5,
        }),
        Plot.dot(recentDailyData, {
          x: "dateObj",
          y: "articles",
          r: 2.5,
          fill: "#3ea8ff",
          tip: true,
          title: (d) =>
            `${d.date.replaceAll("-", "/")}\n日別記事数: ${d.articles.toLocaleString("ja-JP")} 件\n7日移動平均: ${d.ma7.toFixed(1)} 件`,
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>
</div>

---

## 2. Like数分布

```js
const paretoMonthOptions = ["ALL", ...[...months].reverse()];
const paretoMonth = view(
  Inputs.select(paretoMonthOptions, {
    label: "対象月",
    value: "ALL",
    format: (d) => (d === "ALL" ? "全期間 (2020-09〜)" : d),
  })
);

const maxLikesX = view(
  Inputs.range([10, 200], {
    label: "分布グラフのLike数上限",
    value: 50,
    step: 10,
  })
);
```

```js
const rawFreq = data.like_freq[likeMode][paretoMonth] || [];
const freqMap = new Map(rawFreq);
const totalArticlesInMonth =
  rawFreq.reduce((s, [, c]) => s + c, 0) || 1;
const totalLikesInMonth =
  rawFreq.reduce((s, [k, c]) => s + k * c, 0) || 1;

// 1) Like数 (0 〜 maxLikesX) ごとの記事件数割合（折れ線）
const distLineRows = [];
for (let k = 0; k <= maxLikesX; k++) {
  const cnt = freqMap.get(k) || 0;
  distLineRows.push({
    likes: k,
    articles: cnt,
    pct: (cnt / totalArticlesInMonth) * 100,
  });
}

// 2) パレート曲線：Like数が多い順に並べたときの「記事の累積割合 (%) vs 獲得Like数の累積割合 (%)」
const descFreq = [...rawFreq].sort((a, b) => b[0] - a[0]);
let cumArticles = 0;
let cumLikes = 0;
const paretoCurveRows = [{ articlePct: 0, likePct: 0, likes: null }];
for (const [k, cnt] of descFreq) {
  cumArticles += cnt;
  cumLikes += k * cnt;
  paretoCurveRows.push({
    articlePct: (cumArticles / totalArticlesInMonth) * 100,
    likePct: (cumLikes / totalLikesInMonth) * 100,
    likes: k,
  });
}

const periodLabel = paretoMonth === "ALL" ? "全期間" : paretoMonth;
```

<div class="grid grid-cols-2">
  <div class="card">
    <h3>${periodLabel} の Like数別 記事件数割合 (%)</h3>
    ${Plot.plot({
      height: 320,
      marginLeft: 50,
      x: { label: `${likeLabel}（0〜${maxLikesX}）` },
      y: { label: "記事件数割合 (%)", grid: true },
      marks: [
        Plot.areaY(distLineRows, {
          x: "likes",
          y: "pct",
          fill: "#3ea8ff",
          fillOpacity: 0.18,
        }),
        Plot.lineY(distLineRows, {
          x: "likes",
          y: "pct",
          stroke: "#3ea8ff",
          strokeWidth: 2,
          tip: true,
          title: (d) =>
            `${d.likes} Like\n割合: ${d.pct.toFixed(2)}%\n記事数: ${d.articles.toLocaleString("ja-JP")}`,
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>

  <div class="card">
    <h3>${periodLabel} のパレート曲線（多い順の累積割合）</h3>
    ${Plot.plot({
      height: 320,
      marginLeft: 50,
      x: { label: "記事の累積割合（多い順 %）", domain: [0, 100], grid: true },
      y: { label: `${likeLabel}の累積割合 (%)`, domain: [0, 100], grid: true },
      marks: [
        Plot.line(
          [
            { articlePct: 0, likePct: 0 },
            { articlePct: 100, likePct: 100 },
          ],
          {
            x: "articlePct",
            y: "likePct",
            stroke: "#94a3b8",
            strokeDasharray: "4,4",
          }
        ),
        Plot.ruleY([80], { stroke: "#cbd5e1", strokeDasharray: "2,2" }),
        Plot.lineY(paretoCurveRows, {
          x: "articlePct",
          y: "likePct",
          stroke: "#ef4444",
          strokeWidth: 2.5,
          tip: true,
          title: (d) =>
            d.likes === null
              ? "0%"
              : `${d.likes} Like以上\n上位記事割合: ${d.articlePct.toFixed(1)}%\n獲得${likeLabel}累積: ${d.likePct.toFixed(1)}%`,
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>
</div>

---

## 3. 人気トピック

```js
const topicWindow = view(
  Inputs.radio(["all", "36", "24", "12"], {
    label: "表示期間",
    value: "36",
    format: (d) => (d === "all" ? "全期間 (2020-09〜)" : `直近 ${d} ヶ月`),
  })
);
```

```js
function buildBumpData(rows) {
  const filteredMonths =
    topicWindow === "all" ? months : months.slice(-Number(topicWindow));
  const monthSet = new Set(filteredMonths);
  const sub = rows
    .filter((d) => monthSet.has(d.month))
    .map((d) => ({ ...d, date: parseMonth(d.month) }));

  const top10Topics = new Set(
    sub.filter((d) => d.rank <= 10).map((d) => d.topic)
  );
  return {
    rows: sub.filter((d) => top10Topics.has(d.topic)),
    dates: filteredMonths.map(parseMonth),
  };
}

const topicCountBump = buildBumpData(data.topics.count);
const topicLikesBump = buildBumpData(data.topics[likeMode]);

function renderBumpChart(bump, valueLabel) {
  if (bump.rows.length === 0) return html`<p>データがありません</p>`;
  const lastDate = bump.dates[bump.dates.length - 1];
  const lastRows = bump.rows.filter(
    (d) => d.date.getTime() === lastDate?.getTime() && d.rank <= 10
  );
  return Plot.plot({
    width: 1200,
    height: 420,
    marginLeft: 45,
    marginRight: 115,
    x: { label: null, type: "utc" },
    y: {
      label: "順位",
      domain: [10.5, 0.5],
      ticks: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      grid: true,
    },
    color: { legend: false },
    marks: [
      Plot.line(bump.rows, {
        x: "date",
        y: "rank",
        z: "topic",
        stroke: "topic",
        strokeWidth: 2,
        clip: true,
      }),
      Plot.dot(bump.rows, {
        x: "date",
        y: "rank",
        fill: "topic",
        r: 3,
        clip: true,
        tip: true,
        title: (d) =>
          `${fmtMonth(d.month)} | #${d.rank} ${d.topic}\n${valueLabel}: ${d.value.toLocaleString("ja-JP")}`,
      }),
      Plot.text(lastRows, {
        x: "date",
        y: "rank",
        text: (d) => `${d.rank}. ${d.topic}`,
        dx: 8,
        textAnchor: "start",
        fill: "topic",
        fontSize: 11,
        fontWeight: 600,
      }),
    ],
  });
}
```

<div class="grid grid-cols-1">
  <div class="card">
    <h3>投稿トピック件数の順位推移（上位10位）</h3>
    ${renderBumpChart(topicCountBump, "記事数")}
  </div>
  <div class="card">
    <h3>投稿トピック${likeLabel}の順位推移（上位10位）</h3>
    ${renderBumpChart(topicLikesBump, likeLabel)}
  </div>
</div>

---

## 4. TechとIdeaの比較

```js
const techIdeaCompare = data.tech_idea.flatMap((d) => {
  const date = parseMonth(d.month);
  const likesPct = isAuth ? d.auth_likes_pct : d.total_likes_pct;
  return [
    {
      month: d.month,
      date,
      type: d.type,
      series: "記事数割合 (%)",
      pct: d.articles_pct,
    },
    {
      month: d.month,
      date,
      type: d.type,
      series: `${likeLabel}割合 (%)`,
      pct: likesPct,
    },
  ];
});

function renderTechIdeaCompare(targetType) {
  const rows = techIdeaCompare.filter((d) => d.type === targetType);
  return Plot.plot({
    height: 300,
    marginLeft: 45,
    x: { label: null, type: "utc" },
    y: { label: "割合 (%)", domain: [0, 100], grid: true },
    color: {
      domain: ["記事数割合 (%)", `${likeLabel}割合 (%)`],
      range: ["#3ea8ff", "#ef4444"],
      legend: true,
    },
    marks: [
      Plot.lineY(rows, {
        x: { value: "date", label: "月" },
        y: "pct",
        stroke: "series",
        strokeWidth: 2,
        tip: { format: { x: "%Y/%m" } },
      }),
      Plot.ruleY([0]),
    ],
  });
}
```

<div class="grid grid-cols-2">
  <div class="card">
    <h3>Tech：記事数割合 vs ${likeLabel}割合</h3>
    ${renderTechIdeaCompare("tech")}
  </div>

  <div class="card">
    <h3>Idea：記事数割合 vs ${likeLabel}割合</h3>
    ${renderTechIdeaCompare("idea")}
  </div>
</div>

---

## 5. Publicationの比較

```js
const minPubArticles = view(
  Inputs.range([1, 100], {
    label: "表示する月の最小記事数",
    value: 10,
    step: 1,
  })
);
```

```js
const pubFiltered = data.publications
  .filter((d) => d.articles >= minPubArticles)
  .map((d) => ({
    ...d,
    date: parseMonth(d.month),
    likes_sum: isAuth ? d.auth_likes_sum : d.total_likes_sum,
    likes_avg: isAuth ? d.auth_likes_avg : d.total_likes_avg,
    zero_pct: isAuth ? d.auth_zero_pct : d.total_zero_pct,
    gini: isAuth ? d.auth_gini : d.total_gini,
  }));

const pubColor = {
  domain: ["無所属", "free", "pro", "connect"],
  range: ["#64748b", "#3ea8ff", "#10b981", "#a855f7"],
  legend: true,
};
```

<div class="grid grid-cols-2">
  <div class="card">
    <h3>合計${likeLabel}</h3>
    ${Plot.plot({
      height: 300,
      marginLeft: 65,
      x: { label: null, type: "utc" },
      y: { label: `合計${likeLabel}`, grid: true },
      color: pubColor,
      marks: [
        Plot.lineY(pubFiltered, {
          x: { value: "date", label: "月" },
          y: "likes_sum",
          stroke: "group",
          strokeWidth: 2,
          tip: { format: { x: "%Y/%m" } },
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>

  <div class="card">
    <h3>平均${likeLabel}</h3>
    ${Plot.plot({
      height: 300,
      marginLeft: 50,
      x: { label: null, type: "utc" },
      y: { label: `平均${likeLabel}`, grid: true },
      color: pubColor,
      marks: [
        Plot.lineY(pubFiltered, {
          x: { value: "date", label: "月" },
          y: "likes_avg",
          stroke: "group",
          strokeWidth: 2,
          tip: { format: { x: "%Y/%m" } },
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>

  <div class="card">
    <h3>0 Like 記事の割合 (%)</h3>
    ${Plot.plot({
      height: 300,
      marginLeft: 50,
      x: { label: null, type: "utc" },
      y: { label: "0 Like 割合 (%)", domain: [0, 100], grid: true },
      color: pubColor,
      marks: [
        Plot.lineY(pubFiltered, {
          x: { value: "date", label: "月" },
          y: "zero_pct",
          stroke: "group",
          strokeWidth: 2,
          tip: { format: { x: "%Y/%m" } },
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>

  <div class="card">
    <h3>${likeLabel} ジニ係数</h3>
    ${Plot.plot({
      height: 300,
      marginLeft: 50,
      x: { label: null, type: "utc" },
      y: { label: "ジニ係数 (0〜1)", domain: [0, 1], grid: true },
      color: pubColor,
      marks: [
        Plot.lineY(pubFiltered, {
          x: { value: "date", label: "月" },
          y: "gini",
          stroke: "group",
          strokeWidth: 2,
          tip: { format: { x: "%Y/%m" } },
        }),
        Plot.ruleY([0]),
      ],
    })}
  </div>
</div>

---

## 表示設定

```js
const likeMode = view(
  Inputs.radio(["auth", "total"], {
    label: "Like 指標",
    value: "auth",
    format: (d) =>
      d === "auth" ? "ユーザーLikeのみ" : "合計Like数",
  })
);
```
