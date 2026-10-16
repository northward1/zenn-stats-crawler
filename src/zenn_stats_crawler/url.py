from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """
    URLを正規化（カノニカル化）する。
    - 前後の空白を除去
    - スキームとホスト名を小文字化
    - クエリパラメータ（?locale=en など）を除去
    - フラグメント（#...）を除去
    - ルート以外の末尾スラッシュを除去
    """
    if not url:
        return ""

    url = url.strip()
    parsed = urlsplit(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path

    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, "", ""))

