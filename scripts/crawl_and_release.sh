#!/usr/bin/env bash
set -euo pipefail

# スクリプト自身のディレクトリからリポジトリルートを特定
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# cron 実行時にも uv, gh, python 等が見つかるように PATH を明示
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# .env ファイルが存在すれば読み込む
if [ -f "$PROJECT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

echo "=========================================================="
echo " [$(date '+%Y-%m-%d %H:%M:%S')] クロールバッチ開始"
echo "=========================================================="

DB_FILE="data/zenn_stats.db"
GZ_FILE="data/zenn_stats.db.gz"
RELEASE_TAG="latest"

# クローラーを最大 6 時間実行
# -q: プログレスバー出力を抑制
set +e
timeout 6h uv run zenn-stats-crawler -q
EXIT_CODE=$?
set -e

# exit code: 0 = 正常完了, 124 = timeout (6時間経過)
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] クロールが全件完了しました。"
elif [ $EXIT_CODE -eq 124 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 制限時間（6時間）に達したためクロールを切り上げました。"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] エラー: クローラーが異常終了しました (exit code: $EXIT_CODE)"
    exit $EXIT_CODE
fi

if [ ! -f "$DB_FILE" ]; then
    echo "エラー: データベースファイル $DB_FILE が見つかりません。"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] データベースを gzip 圧縮中 ($DB_FILE -> $GZ_FILE)..."
gzip -c "$DB_FILE" > "$GZ_FILE.tmp"
mv "$GZ_FILE.tmp" "$GZ_FILE"

FILE_SIZE=$(du -h "$GZ_FILE" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 圧縮完了 (サイズ: $FILE_SIZE)"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] GitHub Releases ($RELEASE_TAG) へアップロード中..."

UPDATED_AT="$(date '+%Y-%m-%d %H:%M:%S %Z')"
RELEASE_NOTES="Auto-updated daily snapshot.
- Last updated: ${UPDATED_AT}
- File size: ${FILE_SIZE}"

if gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
    gh release edit "$RELEASE_TAG" --notes "$RELEASE_NOTES"
    gh release upload "$RELEASE_TAG" "$GZ_FILE" --clobber
else
    gh release create "$RELEASE_TAG" "$GZ_FILE" \
      --title "Latest Zenn Stats Data" \
      --notes "$RELEASE_NOTES"
fi

echo "=========================================================="
echo " [$(date '+%Y-%m-%d %H:%M:%S')] すべての処理が正常に完了しました。"
echo "=========================================================="

