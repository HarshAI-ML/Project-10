import requests
import hashlib
import xml.etree.ElementTree as ET
import logging
import time
from pipeline.models import BronzeNewsArticle

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/markets/etmarkets.cms",
    "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# Build keyword map from StockMaster names at import time
def _build_keyword_map():
    try:
        from portfolio.models import StockMaster
        kw_map = {}
        for s in StockMaster.objects.filter(is_active=True).values('name', 'ticker'):
            words = s['name'].lower().replace('ltd.', '').replace('inc.', '').replace('corp.', '').split()
            keywords = [w for w in words if len(w) > 3][:3]
            if keywords:
                kw_map[s['name']] = keywords
        return kw_map
    except Exception:
        return {}


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _tag_companies(text: str, kw_map: dict) -> str:
    text_lower = text.lower()
    tags = [name for name, kws in kw_map.items() if any(kw in text_lower for kw in kws)]
    return ", ".join(tags[:5]) if tags else "sector"


def fetch_and_store_news() -> dict:
    """
    Fetch all RSS feeds, deduplicate, store new articles in BronzeNewsArticle.
    Returns summary dict.
    """
    kw_map = _build_keyword_map()
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall(".//item")

            for item in items:
                title = item.findtext("title", "").strip()
                url = item.findtext("link", "").strip()
                if not url or not title:
                    continue
                articles.append({
                    "article_id": _make_id(url),
                    "title": title,
                    "url": url,
                    "description": item.findtext("description", "").strip(),
                    "published_at": item.findtext("pubDate", "").strip(),
                    "company_tags": _tag_companies(title, kw_map),
                    "source": "economic_times",
                    "source_quality": 0.8,
                })

            logger.info(f"RSS: {len(items)} items from {feed_url.split('/')[4]}")
            time.sleep(1)

        except Exception as e:
            logger.error(f"RSS failed {feed_url}: {e}")

    # Deduplicate by article_id
    seen = set()
    unique = []
    for a in articles:
        if a['article_id'] not in seen:
            seen.add(a['article_id'])
            unique.append(a)

    # Skip already stored articles
    existing = set(
        BronzeNewsArticle.objects
        .filter(article_id__in=[a['article_id'] for a in unique])
        .values_list('article_id', flat=True)
    )
    new_articles = [a for a in unique if a['article_id'] not in existing]

    # Bulk insert
    if new_articles:
        BronzeNewsArticle.objects.bulk_create([
            BronzeNewsArticle(**a) for a in new_articles
        ], batch_size=100, ignore_conflicts=True)

    logger.info(f"News: {len(new_articles)} new / {len(unique)-len(new_articles)} existed / {len(unique)} total fetched")
    return {
        'fetched': len(unique),
        'new': len(new_articles),
        'skipped': len(unique) - len(new_articles),
    }


class NewsFetcher:
    """Wrapper class for backward compatibility."""

    def fetch_news(self):
        return fetch_and_store_news()
