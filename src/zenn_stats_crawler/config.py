import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    mail_address: Optional[str] = None
    hash_salt: Optional[str] = None
    request_interval_min: float = 1.5
    request_interval_max: float = 2.5
    timeout: float = 30.0
    max_retries: int = 3
    sitemap_index_url: str = "https://zenn.dev/sitemaps/_index.xml"
    db_path: Path = Path("data/zenn_stats.db")

    @classmethod
    def from_env(cls, db_path: Optional[Path] = None, mail: Optional[str] = None, salt: Optional[str] = None) -> "Config":
        mail_addr = mail or os.getenv("MAIL_ADDRESS")
        hash_salt = salt or os.getenv("HASH_SALT")
        db_p = db_path or Path(os.getenv("DB_PATH", "data/zenn_stats.db"))

        return cls(
            mail_address=mail_addr,
            hash_salt=hash_salt,
            request_interval_min=float(os.getenv("REQUEST_INTERVAL_MIN", "1.5")),
            request_interval_max=float(os.getenv("REQUEST_INTERVAL_MAX", "2.5")),
            timeout=float(os.getenv("HTTP_TIMEOUT", "30.0")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            sitemap_index_url=os.getenv("SITEMAP_INDEX_URL", "https://zenn.dev/sitemaps/_index.xml"),
            db_path=db_p,
        )

    def get_user_agent(self) -> str:
        if self.mail_address:
            return f"zenn-stats-crawler/0.1.0 (+mailto:{self.mail_address})"
        return "zenn-stats-crawler/0.1.0 (+https://github.com/northward1/zenn-stats-crawler; mail-address-not-set)"

