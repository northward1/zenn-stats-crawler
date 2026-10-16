import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def hash_text(text: Optional[str], salt: Optional[str] = None) -> Optional[str]:
    """
    指定されたテキストとソルトを用いてSHA-256ハッシュ値を算出する。
    テキストがNoneの場合はNoneを返す。
    """
    if text is None:
        return None

    if salt is None:
        salt = os.getenv("HASH_SALT", "")
        if not salt:
            logger.warning(
                "環境変数 HASH_SALT が設定されていません。適切なソルトなしでハッシュ化が行われます。"
            )

    combined = f"{salt}:{text}".encode("utf-8")
    return hashlib.sha256(combined).hexdigest()

