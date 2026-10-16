import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Set

from zenn_stats_crawler.client import RateLimitedClient
from zenn_stats_crawler.url import normalize_url

logger = logging.getLogger(__name__)


@dataclass
class SitemapUrlInfo:
    loc: str
    lastmod: Optional[str] = None
    changefreq: Optional[str] = None


def get_local_tag_name(tag: str) -> str:
    """XML要素名から名前空間接頭辞を除去してローカル名を取得する"""
    return tag.split("}")[-1] if "}" in tag else tag


def parse_sitemap_index(
    xml_bytes: bytes,
    pattern: str = r"/article\d*\.xml(\.gz)?$",
) -> List[str]:
    r"""
    サイトマップインデックスXMLをパースし、指定された正規表現に一致するサイトマップURL一覧を抽出する。
    デフォルトは記事 (article*.xml.gz または article*.xml) を対象とする。
    本などの場合は pattern=r"/(article|books?)\d*\.xml(\.gz)?$" などの指定も可能。
    """
    root = ET.fromstring(xml_bytes)
    sitemap_urls: List[str] = []
    regex = re.compile(pattern)

    for elem in root.iter():
        if get_local_tag_name(elem.tag) == "sitemap":
            loc_val = None
            for child in elem:
                if get_local_tag_name(child.tag) == "loc" and child.text:
                    loc_val = child.text.strip()
                    break

            if loc_val and regex.search(loc_val):
                sitemap_urls.append(loc_val)

    logger.info(f"サイトマップインデックスから {len(sitemap_urls)} 件のサイトマップを検出しました。")
    return sitemap_urls


def parse_content_sitemap(xml_bytes: bytes) -> List[SitemapUrlInfo]:
    """
    個別サイトマップXMLをパースし、各ページのURL情報を抽出する
    """
    root = ET.fromstring(xml_bytes)
    items: List[SitemapUrlInfo] = []
    seen_urls: Set[str] = set()

    for elem in root.iter():
        if get_local_tag_name(elem.tag) == "url":
            loc = None
            lastmod = None
            changefreq = None

            for child in elem:
                tag = get_local_tag_name(child.tag)
                if tag == "loc" and child.text:
                    loc = normalize_url(child.text.strip())
                elif tag == "lastmod" and child.text:
                    lastmod = child.text.strip()
                elif tag == "changefreq" and child.text:
                    changefreq = child.text.strip()

            if loc and loc not in seen_urls:
                seen_urls.add(loc)
                items.append(
                    SitemapUrlInfo(loc=loc, lastmod=lastmod, changefreq=changefreq)
                )

    logger.info(f"サイトマップから {len(items)} 件のURLを抽出しました。")
    return items


class SitemapCrawler:
    """
    サイトマップを取得し、URL一覧を収集・管理するクラス
    """

    def __init__(self, client: Optional[RateLimitedClient] = None):
        self.client = client or RateLimitedClient()

    def fetch_sitemap_urls(
        self,
        index_url: str = "https://zenn.dev/sitemaps/_index.xml",
        pattern: str = r"/article\d*\.xml(\.gz)?$",
    ) -> List[str]:
        """サイトマップインデックスを取得し、該当するサイトマップURL一覧を返す"""
        content = self.client.fetch_bytes(index_url)
        return parse_sitemap_index(content, pattern=pattern)

    def fetch_urls_from_sitemap(self, sitemap_url: str) -> List[SitemapUrlInfo]:
        """単一のサイトマップURL (gzまたはxml) を取得してパースし、URL一覧を返す"""
        content = self.client.fetch_bytes(sitemap_url)
        return parse_content_sitemap(content)
