import html
import re
import feedparser
import httpx
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

# Feed items that aren't news stories: promos, app/stream links, podcasts, show rundowns
JUNK_URL_PATTERNS = [
    r"/outkick-betting/",
    r"bbc\.co\.uk/sounds/",
    r"bbc\.co\.uk/iplayer/",
]
JUNK_TITLE_PATTERNS = [
    r"\b(promo|bonus) code\b",
    r"^(LIVE:\s*)?ABC News Live$",
    r"^BBC News app$",
    r"CBS Mornings Deals",
    r"^\d+/\d+: CBS (Saturday|Sunday) Morning",
    r'^This week on "Sunday Morning"',
]


def is_junk(title: str, url: str) -> bool:
    return any(re.search(p, url, re.I) for p in JUNK_URL_PATTERNS) or any(
        re.search(p, title, re.I) for p in JUNK_TITLE_PATTERNS
    )


# Opinion, editorials, columns and reviews, as opposed to straight reporting
OPINION_URL_PATTERNS = [
    r"/opinions?/",
    r"/commentary/",
    r"/editorials?/",
    r"/columns?/",
    r"/columnists?/",
    r"/The-Home-Forum/",                    # CSM essays
    r"npr\.org/\d{4}/.*/opinion-",
    r"nationalreview\.com/(\d{4}|corner)/",  # NR's straight news lives under /news/
]
OPINION_TITLE_PATTERN = r"^(opinion|editorial|commentary|review|analysis)\b"
# Fox/Daily Caller-style columnist bylines, e.g. "ELI STEELE: ..." (case-sensitive)
BYLINE_PATTERN = r"^(?!(LIVE|WATCH|BREAKING|UPDATE|EXCLUSIVE|REPORT|FIRST ON)\b)([A-Z'\-]{2,}( [A-Z'\-]+)+|[A-Z'\-]{4,}): "


def is_opinion(title: str, url: str, categories: list[str] = ()) -> bool:
    return bool(
        any(re.search(p, url, re.I) for p in OPINION_URL_PATTERNS)
        or re.search(OPINION_TITLE_PATTERN, title, re.I)
        or re.search(BYLINE_PATTERN, title)
        or any(re.search(r"\bopinion\b", c or "", re.I) for c in categories)
    )


def parse_date(entry) -> Optional[datetime]:
    """Publish time as naive UTC, matching scraped_at. feedparser normalises *_parsed
    fields to UTC and handles both RFC 822 (RSS) and ISO 8601 (Atom) dates."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            # Clamp feeds that post-date items into the future
            return min(datetime(*parsed[:6]), datetime.utcnow())
    return None


def clean_text(raw: str) -> str:
    """Strip HTML tags, decode entities (&#039; &amp; &nbsp;) and collapse whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", "", raw))
    return re.sub(r"\s+", " ", text).strip()


def _upsize(url: str) -> str:
    """Request larger renditions from CDNs whose feeds only carry small thumbnails."""
    url = re.sub(r"(ichef\.bbci\.co\.uk/ace/standard/)\d+/", r"\g<1>800/", url)
    url = re.sub(r"(i\.guim\.co\.uk/.*[?&]width=)\d+", r"\g<1>700", url)
    return url


def extract_image(entry) -> str:
    """Best image URL from an RSS entry (media tags, enclosures, or inline <img>)."""
    candidates = []
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            if m.get("url") and m.get("medium", "image") == "image":
                candidates.append((int(m.get("width") or 0), m["url"]))
    if candidates:
        return _upsize(max(candidates)[1])
    for enc in entry.get("enclosures") or []:
        href = enc.get("href") or enc.get("url")
        if href and enc.get("type", "").startswith("image/"):
            return href
    raw = entry.get("summary", "") + "".join(c.get("value", "") for c in entry.get("content", []))
    m = re.search(r'<img[^>]+src="([^"]+)"', raw)
    return m.group(1) if m else ""


def fetch_og_image(url: str) -> str:
    """Fallback: read the og:image meta tag from the article page."""
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (GroundedNews)"})
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', r.text
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', r.text
        )
        return m.group(1).replace("&amp;", "&") if m else ""
    except Exception:
        return ""


def fetch_og_images(urls: list[str]) -> list[str]:
    with ThreadPoolExecutor(max_workers=12) as pool:
        return list(pool.map(fetch_og_image, urls))


FEED_TIMEOUT = 15  # seconds; one slow feed must not stall the whole run
USER_AGENT = "Mozilla/5.0 (compatible; GroundedNews/1.0)"


def fetch_feed(feed_url: str, max_articles: int = 50) -> list[dict]:
    """Download and parse one feed. Raises with a readable message on failure."""
    try:
        r = httpx.get(feed_url, timeout=FEED_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
    except httpx.TimeoutException:
        raise RuntimeError(f"Timed out after {FEED_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"Connection failed: {e}")

    feed = feedparser.parse(r.content)
    if not feed.entries and feed.bozo:
        raise RuntimeError(f"Not a valid feed: {feed.bozo_exception}")

    articles = []
    for entry in feed.entries[:max_articles]:
        url = entry.get("link", "")
        title = clean_text(entry.get("title", ""))
        if not url or not title or is_junk(title, url):
            continue
        summary = clean_text(entry.get("summary", entry.get("description", "")))[:500]
        articles.append({
            "title": title,
            "url": url,
            "summary": summary,
            "published_at": parse_date(entry),
            "image_url": extract_image(entry),
            "is_opinion": is_opinion(title, url, [t.get("term", "") for t in entry.get("tags") or []]),
        })
    return articles


def fetch_feeds(feed_urls: list[str], max_articles: int = 50) -> list[tuple[list[dict], str]]:
    """Fetch feeds in parallel. Returns (articles, error) per feed, in order; error is "" on success."""
    def one(url: str) -> tuple[list[dict], str]:
        try:
            return fetch_feed(url, max_articles), ""
        except Exception as e:
            return [], str(e)[:300]

    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(one, feed_urls))


def scrape_feed(feed_url: str, max_articles: int = 50) -> list[dict]:
    """Single-feed fetch that logs and swallows errors (used by the legacy API pipeline)."""
    articles, error = fetch_feeds([feed_url], max_articles)[0]
    if error:
        print(f"Error scraping {feed_url}: {error}")
    return articles
