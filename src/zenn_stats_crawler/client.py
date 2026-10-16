import gzip
import logging
import random
import time
from typing import Optional
import requests

from zenn_stats_crawler.config import Config

logger = logging.getLogger(__name__)


class RateLimitedClient:
    """
    リクエスト間隔を厳密に制御するHTTPクライアント
    サーバー負荷軽減のため、ランダム待機と指数バックオフリトライを備える
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.from_env()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.get_user_agent(),
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_time: float = 0.0

    def _wait_for_rate_limit(self) -> None:
        """直前のリクエストから指定秒数経過するまで待機する。"""
        elapsed = time.time() - self._last_request_time
        target_interval = random.uniform(
            self.config.request_interval_min, self.config.request_interval_max
        )
        if elapsed < target_interval:
            wait_time = target_interval - elapsed
            logger.debug(f"レート制限遵守のため {wait_time:.2f} 秒待機中...")
            time.sleep(wait_time)

    def get(self, url: str) -> requests.Response:
        """
        レート制限とリトライを適用してGETリクエストを送信する。
        """
        retries = 0
        backoff = 3.0

        while True:
            self._wait_for_rate_limit()
            try:
                self._last_request_time = time.time()
                logger.info(f"リクエスト送信: {url}")
                response = self.session.get(url, timeout=self.config.timeout)

                # 429 Too Many Requests や 5xx サーバーエラーの場合はリトライ
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()

                response.raise_for_status()
                return response

            except requests.HTTPError as http_exc:
                status_code = getattr(http_exc.response, "status_code", None)
                # 429以外の4xx (404 Not Found 等) は恒久的なエラーのためリトライせず即座に送出
                if status_code and 400 <= status_code < 500 and status_code != 429:
                    logger.warning(f"クライアントエラー検知 ({status_code}): リトライを中断します")
                    raise

                retries += 1
                if retries > self.config.max_retries:
                    logger.error(
                        f"{url} の取得に失敗しました (リトライ上限 {self.config.max_retries} 回到達): {http_exc}"
                    )
                    raise

                wait_retry = backoff * (2 ** (retries - 1))
                logger.warning(
                    f"リクエストエラー発生 ({http_exc})。{wait_retry:.1f} 秒後にリトライします ({retries}/{self.config.max_retries})..."
                )
                time.sleep(wait_retry)

            except (requests.RequestException, Exception) as exc:
                retries += 1
                if retries > self.config.max_retries:
                    logger.error(
                        f"{url} の取得に失敗しました (リトライ上限 {self.config.max_retries} 回到達): {exc}"
                    )
                    raise

                wait_retry = backoff * (2 ** (retries - 1))
                logger.warning(
                    f"リクエストエラー発生 ({exc})。{wait_retry:.1f} 秒後にリトライします ({retries}/{self.config.max_retries})..."
                )
                time.sleep(wait_retry)

    def fetch_bytes(self, url: str) -> bytes:
        """
        URLからバイト列を取得し、gzip圧縮されている場合は解凍して返す。
        """
        response = self.get(url)
        content = response.content

        # gzipマジックナンバー (1f 8b) の判定
        if content.startswith(b"\x1f\x8b"):
            logger.debug(f"gzip圧縮コンテンツを検知、解凍します: {url}")
            return gzip.decompress(content)

        return content

    def fetch_text(self, url: str) -> str:
        """
        URLからテキストを取得する。
        """
        raw_bytes = self.fetch_bytes(url)
        return raw_bytes.decode("utf-8")

