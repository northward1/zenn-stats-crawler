# zenn-stats-crawler

[Zenn](https://zenn.dev/) の記事統計データ（いいね数、ブックマーク数、トピック等）を定期的に収集し、推移として単一の SQLite データベースに蓄積するクローラーです。

プライバシーや利用規約、倫理的な配慮のため、URLや記事タイトル、ユーザー名、Publication名をソルト付き SHA-256 でハッシュ化して保存しています。

## データベースのダウンロード

最新の収集済み SQLite データベースは、GitHub Releases から直接ダウンロード可能です。

* **[最新版データベース (zenn_stats.db.gz)](https://github.com/northward1/zenn-stats-crawler/releases/latest/download/zenn_stats.db.gz)**

```bash
# ダウンロードと解凍
curl -LO https://github.com/northward1/zenn-stats-crawler/releases/latest/download/zenn_stats.db.gz
gzip -d zenn_stats.db.gz
```

## セットアップ

### 必須環境
* Python >= 3.12
* [uv](https://docs.astral.sh/uv/)

### 依存関係のインストール
```bash
uv sync
```

## 使い方

### 環境変数の設定
ハッシュ化ソルトおよび連絡先メールアドレスを設定します（引数でも指定可能）。

```bash
export MAIL_ADDRESS="your_email@example.com"
export HASH_SALT="your_secure_random_salt"
```

### コマンドの実行

```bash
# 基本実行 (期限: 30日, DB: data/zenn_stats.db)
uv run zenn-stats-crawler

# 期限を14日間に指定
uv run zenn-stats-crawler -L 14

# 実行前にクロール対象件数のみを確認 (アクセス・書き込みなし)
uv run zenn-stats-crawler --dry-run

# テスト用に最初の5件のみクロール
uv run zenn-stats-crawler --limit 5

# サイトマップ取得数を先頭2つに制限してテスト実行
uv run zenn-stats-crawler --max-sitemaps 2 --limit 10
```

---

## オプション一覧

| オプション              | デフォルト値         | 説明                                                             |
| :---------------------- | :------------------- | :--------------------------------------------------------------- |
| `-L`, `--expire-days`   | `30.0`               | 再取得の期限（日数）。直近取得日時がこれより古い記事を再クロール |
| `--db-path`             | `data/zenn_stats.db` | 保存先 SQLite データベースファイルのパス                         |
| `--limit`               | なし (全件)          | 今回の実行でクロールする最大記事数                               |
| `--dry-run`             | `False`              | 記事アクセスやDB書き込みを行わずに対象件数の確認のみ行う         |
| `--success-only-expire` | `False`              | 過去に失敗した記事を期限判定から除外し、直ちに再試行する         |
| `--mail`                | なし                 | User-Agent 用連絡先メールアドレス（`$MAIL_ADDRESS` を上書き）    |
| `--salt`                | なし                 | ハッシュ化用ソルト（`$HASH_SALT` を上書き）                      |
| `-q`, `--quiet`         | `False`              | プログレスバーとサマリー出力を抑制（cronやCI向け）               |
| `--progress`            | なし                 | ログレベルに関わらずプログレスバーを強制表示                      |
| `--no-progress`         | なし                 | プログレスバーを非表示                                            |
| `--log-level`           | `INFO`               | ログレベル (`DEBUG`, `INFO`, `WARNING`, `ERROR`)                 |

---

## データベーススキーマ (`articles`)

| カラム名                    | 型                  | 説明                                                      |
| :-------------------------- | :------------------ | :-------------------------------------------------------- |
| `id`                        | INTEGER PRIMARY KEY | 自動採番 ID                                               |
| `url_hash`                  | TEXT NOT NULL       | 記事URLのソルト付き SHA-256 ハッシュ                      |
| `article_type`              | TEXT                | 記事タイプ (`tech`, `idea` 等)                            |
| `title_hash`                | TEXT                | タイトルのハッシュ                                        |
| `user_name_hash`            | TEXT                | 著者ユーザー名のハッシュ                                  |
| `published_at`              | TEXT                | 記事の公開日時 (ISO 8601)                                 |
| `comments_count`            | INTEGER             | コメント数                                                |
| `liked_count`               | INTEGER             | いいね数                                                  |
| `authenticated_liked_count` | INTEGER             | ログインユーザーのいいね数                                |
| `anonymous_liked_count`     | INTEGER             | 匿名ユーザーのいいね数                                    |
| `bookmarked_count`          | INTEGER             | ブックマーク数                                            |
| `topics`                    | TEXT                | トピック名配列の JSON 文字列 (例: `["python", "sqlite"]`) |
| `publication_plan`          | TEXT                | 企業・Organizationプラン名                                |
| `publication_name_hash`     | TEXT                | Publication名のハッシュ                                   |
| `crawled_at`                | TEXT NOT NULL       | クロール実行日時 (ISO 8601 UTC)                           |
| `status`                    | TEXT NOT NULL       | `'success'` または `'failed'`                             |
| `http_status`               | INTEGER             | レスポンスステータスコード (200, 404, 500 等)             |
| `error_message`             | TEXT                | エラー時の詳細メッセージ                                  |

---

## テストの実行

```bash
uv run pytest
```
