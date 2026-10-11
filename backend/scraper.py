import html
import re
import feedparser
import httpx
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from timeutil import utcnow

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
            return min(datetime(*parsed[:6]), utcnow())
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


def fetch_og_image(url: str, client: httpx.Client) -> str:
    """Fallback: read the og:image meta tag from the article page."""
    try:
        r = client.get(url, timeout=8)
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', r.text
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']', r.text
        )
        return html.unescape(m.group(1)) if m else ""
    except Exception:
        return ""


FEED_TIMEOUT = 15  # seconds; one slow feed must not stall the whole run
USER_AGENT = "Mozilla/5.0 (compatible; GroundedNews/1.0)"


def _client() -> httpx.Client:
    """One connection pool per batch: most pages come from a handful of outlet hosts,
    so keep-alive saves a TLS handshake per request. httpx.Client is thread-safe."""
    return httpx.Client(
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
    )


def fetch_og_images(urls: list[str]) -> list[str]:
    with _client() as client, ThreadPoolExecutor(max_workers=12) as pool:
        return list(pool.map(lambda url: fetch_og_image(url, client), urls))


@dataclass
class FeedResult:
    articles: list[dict] = field(default_factory=list)
    error: str = ""             # "" on success
    not_modified: bool = False  # 304: nothing changed since the validators below were issued
    # Validators to send next time (If-None-Match / If-Modified-Since); "" if the server gave none
    etag: str = ""
    last_modified: str = ""


def fetch_feed(feed_url: str, client: httpx.Client, max_articles: int = 50,
               etag: str = "", last_modified: str = "") -> FeedResult:
    """Download and parse one feed, conditionally if we hold validators from the last fetch.
    Raises with a readable message on failure."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        r = client.get(feed_url, timeout=FEED_TIMEOUT, headers=headers)
        if r.status_code != 304:  # raise_for_status() counts 304 as an error
            r.raise_for_status()
    except httpx.TimeoutException:
        raise RuntimeError(f"Timed out after {FEED_TIMEOUT}s")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP {e.response.status_code}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"Connection failed: {e}")

    # A 304 may refresh the validators; otherwise the ones we sent still hold
    new_etag = r.headers.get("ETag", "")
    new_modified = r.headers.get("Last-Modified", "")
    if r.status_code == 304:
        return FeedResult(not_modified=True, etag=new_etag or etag, last_modified=new_modified or last_modified)

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
    return FeedResult(articles=articles, etag=new_etag, last_modified=new_modified)


def fetch_feeds(feeds: list[tuple[str, str, str]], max_articles: int = 50) -> list[FeedResult]:
    """Fetch feeds in parallel. `feeds` holds (url, etag, last_modified) per feed, with ""
    for validators we don't have. Returns one FeedResult per feed, in order."""
    with _client() as client:
        def one(feed: tuple[str, str, str]) -> FeedResult:
            url, etag, last_modified = feed
            try:
                return fetch_feed(url, client, max_articles, etag, last_modified)
            except Exception as e:
                return FeedResult(error=str(e)[:300])

        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(one, feeds))
