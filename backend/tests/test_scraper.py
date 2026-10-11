import time
from datetime import datetime, timedelta

import feedparser
import httpx
import pytest

import scraper
from scraper import clean_text, fetch_feed, fetch_feeds, is_opinion, parse_date
from timeutil import utcnow

NEWS_URL = "https://news.example/2026/10/05/story"


class TestIsOpinion:
    @pytest.mark.parametrize("url", [
        "https://www.foxnews.com/opinion/why-it-matters",
        "https://thehill.com/opinion/campaign/5512345-the-race/",
        "https://www.washingtonexaminer.com/opinion/columnists/3301234/the-week/",
        "https://www.csmonitor.com/Commentary/2026/1005/a-view",
    ])
    def test_opinion_sections_in_the_url(self, url):
        assert is_opinion("A headline", url)

    @pytest.mark.parametrize("url", [
        "https://www.nationalreview.com/2026/10/the-case-against-the-bill/",
        "https://www.nationalreview.com/corner/a-quick-thought/",
    ])
    def test_national_review_columns_outside_news(self, url):
        assert is_opinion("A headline", url)

    def test_npr_opinion_slug(self):
        assert is_opinion("A headline", "https://www.npr.org/2026/10/05/nx-s1-55/opinion-the-week")

    @pytest.mark.parametrize("title", [
        "Opinion: The Senate got this wrong",
        "OPINION | The Senate got this wrong",
        "Editorial: Fix the roads",
        "Analysis: What the jobs report means",
        "Review: A thrilling new production",
    ])
    def test_opinion_labels_at_the_start_of_the_title(self, title):
        assert is_opinion(title, NEWS_URL)

    @pytest.mark.parametrize("title", [
        "ELI STEELE: The lesson we keep missing",
        "MARK O'DONNELL: A word on the budget",
        "HANSON: Why the polls are wrong",
    ])
    def test_all_caps_columnist_bylines(self, title):
        assert is_opinion(title, NEWS_URL)

    @pytest.mark.parametrize("categories", [["Opinion"], ["Politics", "Opinion & Commentary"]])
    def test_feed_categories(self, categories):
        assert is_opinion("A headline", NEWS_URL, categories)

    @pytest.mark.parametrize("title", [
        "FIRST ON FOX: Senator unveils bill",
        "UAE: Talks to resume next week",
        "U.S.: Inflation cools in September",
        "LIVE: Updates from the summit",
        "BREAKING: Earthquake strikes",
        "WATCH: The moment the bridge fell",
        "EXCLUSIVE: Inside the deal",
        "Opinions split over the new law",
        "Reviewers praise the new phone",
        "Senate passes budget after all-night session",
    ])
    def test_news_titles_that_once_misfired_are_not_opinion(self, title):
        assert not is_opinion(title, NEWS_URL)

    @pytest.mark.parametrize("url", [
        "https://www.nationalreview.com/news/house-passes-spending-bill/",
        "https://news.example/politics/opinion-polls-tighten",
    ])
    def test_news_urls_are_not_opinion(self, url):
        assert not is_opinion("A headline", url)

    def test_unrelated_categories_are_not_opinion(self):
        assert not is_opinion("A headline", NEWS_URL, ["Politics", "", None])


@pytest.mark.parametrize("raw, clean", [
    ("Trump&#039;s plan", "Trump's plan"),
    ("Salt &amp; pepper", "Salt & pepper"),
    ("<p>Hello <b>world</b></p>", "Hello world"),
    ("  lots\n\n of\tspace&nbsp;here  ", "lots of space here"),
    ("<a href=\"x\">&lt;tag&gt;</a>", "<tag>"),
    ("", ""),
])
def test_clean_text(raw, clean):
    assert clean_text(raw) == clean


def struct(dt: datetime) -> time.struct_time:
    return dt.utctimetuple()


class TestParseDate:
    def test_uses_published_time(self):
        when = datetime(2026, 10, 5, 14, 30)
        assert parse_date({"published_parsed": struct(when)}) == when

    def test_falls_back_to_updated_time(self):
        when = datetime(2026, 10, 5, 9, 0)
        assert parse_date({"updated_parsed": struct(when)}) == when

    def test_missing_date_is_none(self):
        assert parse_date({}) is None
        assert parse_date({"published_parsed": None}) is None

    def test_future_dates_are_clamped_to_now(self):
        before = utcnow()
        parsed = parse_date({"published_parsed": struct(utcnow() + timedelta(days=2))})
        assert before <= parsed <= utcnow()

    def test_feed_timezones_end_up_as_naive_utc(self):
        feed = feedparser.parse(rss_feed(item("A story", pub="Mon, 05 Oct 2026 10:30:00 -0400")))
        assert parse_date(feed.entries[0]) == datetime(2026, 10, 5, 14, 30)


def item(title, link=None, pub="Mon, 05 Oct 2026 10:30:00 GMT", category=None):
    link = link or f"https://news.example/{abs(hash(title))}"
    cat = f"<category>{category}</category>" if category else ""
    return f"<item><title>{title}</title><link>{link}</link><pubDate>{pub}</pubDate>{cat}" \
           f"<description>&lt;p&gt;Summary of {title}&lt;/p&gt;</description></item>"


def rss_feed(*items):
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>{"".join(items)}</channel></rss>'


def respond(status=200, content=b"", exc=None, headers=None):
    """A canned reply for one URL: a response, or raises `exc`."""
    def reply(request: httpx.Request) -> httpx.Response:
        if exc:
            raise exc
        return httpx.Response(status, content=content, headers=headers)
    return reply


@pytest.fixture
def serve(monkeypatch):
    """Route the scraper's HTTP client to canned replies: serve(reply) for every URL, or
    serve({url: reply}). Returns the list of requests made, to inspect what was sent."""
    requests: list[httpx.Request] = []

    def install(replies):
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            reply = replies[str(request.url)] if isinstance(replies, dict) else replies
            return reply(request)
        monkeypatch.setattr(scraper, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        return requests
    return install


def fetch_one(url="https://outlet.example/feed", etag="", last_modified=""):
    """fetch_feed through the scraper's own client, as fetch_feeds calls it."""
    with scraper._client() as client:
        return fetch_feed(url, client, 50, etag, last_modified)


class TestFetchFeed:
    def test_parses_items(self, serve):
        feed = rss_feed(
            item("Senate passes budget", link="https://news.example/budget"),
            item("Why the budget fails", category="Opinion"),
            item("BBC News app", link="https://bbc.co.uk/news/app"),  # junk: skipped
        )
        serve(respond(content=feed.encode()))
        articles = fetch_one().articles
        assert [a["title"] for a in articles] == ["Senate passes budget", "Why the budget fails"]
        first = articles[0]
        assert first["url"] == "https://news.example/budget"
        assert first["summary"] == "Summary of Senate passes budget"
        assert first["published_at"] == datetime(2026, 10, 5, 10, 30)
        assert [a["is_opinion"] for a in articles] == [False, True]

    def test_timeout(self, serve):
        serve(respond(exc=httpx.ReadTimeout("slow")))
        with pytest.raises(RuntimeError, match=r"^Timed out after 15s$"):
            fetch_one()

    def test_http_error_status(self, serve):
        serve(respond(status=404))
        with pytest.raises(RuntimeError, match=r"^HTTP 404$"):
            fetch_one()

    def test_connection_failure(self, serve):
        serve(respond(exc=httpx.ConnectError("name not resolved")))
        with pytest.raises(RuntimeError, match=r"^Connection failed: name not resolved$"):
            fetch_one()

    def test_not_a_feed(self, serve):
        serve(respond(content=b"<html><body>Moved</p></div>"))
        with pytest.raises(RuntimeError, match=r"^Not a valid feed: "):
            fetch_one()


class TestConditionalFetch:
    VALIDATORS = {"ETag": '"v1"', "Last-Modified": "Sun, 11 Oct 2026 01:00:00 GMT"}

    def test_first_fetch_sends_no_validators_and_returns_the_servers(self, serve):
        requests = serve(respond(content=rss_feed(item("Story")).encode(), headers=self.VALIDATORS))
        result = fetch_one()
        assert "If-None-Match" not in requests[0].headers
        assert "If-Modified-Since" not in requests[0].headers
        assert (result.etag, result.last_modified) == ('"v1"', "Sun, 11 Oct 2026 01:00:00 GMT")
        assert not result.not_modified

    def test_validators_are_sent_back(self, serve):
        requests = serve(respond(status=304))
        fetch_one(etag='"v1"', last_modified="Sun, 11 Oct 2026 01:00:00 GMT")
        assert requests[0].headers["If-None-Match"] == '"v1"'
        assert requests[0].headers["If-Modified-Since"] == "Sun, 11 Oct 2026 01:00:00 GMT"

    def test_304_is_not_modified_rather_than_an_error(self, serve):
        serve(respond(status=304))
        result = fetch_one(etag='"v1"')
        assert result.not_modified and result.articles == [] and result.error == ""
        assert result.etag == '"v1"'  # kept when the 304 doesn't send a new one

    def test_304_can_refresh_the_validators(self, serve):
        serve(respond(status=304, headers={"ETag": '"v2"'}))
        assert fetch_one(etag='"v1"').etag == '"v2"'


def test_fetch_feeds_reports_errors_per_feed_in_order(serve):
    serve({
        "https://ok.example/feed": respond(content=rss_feed(item("Story")).encode()),
        "https://slow.example/feed": respond(exc=httpx.ConnectTimeout("slow")),
        "https://gone.example/feed": respond(status=404),
        "https://html.example/feed": respond(content=b"<html><body>nope</p>"),
        "https://same.example/feed": respond(status=304),
    })
    urls = ["https://ok.example/feed", "https://slow.example/feed", "https://gone.example/feed",
            "https://html.example/feed", "https://same.example/feed"]
    results = fetch_feeds([(url, '"v1"', "") for url in urls])
    assert [len(r.articles) for r in results] == [1, 0, 0, 0, 0]
    errors = [r.error for r in results]
    assert errors[:3] == ["", "Timed out after 15s", "HTTP 404"]
    assert errors[3].startswith("Not a valid feed: ")
    assert errors[4] == "" and results[4].not_modified
