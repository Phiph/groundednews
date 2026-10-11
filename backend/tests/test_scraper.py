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


def respond(status=200, content=b"", exc=None):
    """A stand-in for httpx.get: returns a canned response, or raises `exc`."""
    def fake_get(url, **kwargs):
        if exc:
            raise exc
        return httpx.Response(status, content=content, request=httpx.Request("GET", url))
    return fake_get


class TestFetchFeed:
    def test_parses_items(self, monkeypatch):
        feed = rss_feed(
            item("Senate passes budget", link="https://news.example/budget"),
            item("Why the budget fails", category="Opinion"),
            item("BBC News app", link="https://bbc.co.uk/news/app"),  # junk: skipped
        )
        monkeypatch.setattr(scraper.httpx, "get", respond(content=feed.encode()))
        articles = fetch_feed("https://outlet.example/feed")
        assert [a["title"] for a in articles] == ["Senate passes budget", "Why the budget fails"]
        first = articles[0]
        assert first["url"] == "https://news.example/budget"
        assert first["summary"] == "Summary of Senate passes budget"
        assert first["published_at"] == datetime(2026, 10, 5, 10, 30)
        assert [a["is_opinion"] for a in articles] == [False, True]

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(scraper.httpx, "get", respond(exc=httpx.ReadTimeout("slow")))
        with pytest.raises(RuntimeError, match=r"^Timed out after 15s$"):
            fetch_feed("https://outlet.example/feed")

    def test_http_error_status(self, monkeypatch):
        monkeypatch.setattr(scraper.httpx, "get", respond(status=404))
        with pytest.raises(RuntimeError, match=r"^HTTP 404$"):
            fetch_feed("https://outlet.example/feed")

    def test_connection_failure(self, monkeypatch):
        monkeypatch.setattr(scraper.httpx, "get", respond(exc=httpx.ConnectError("name not resolved")))
        with pytest.raises(RuntimeError, match=r"^Connection failed: name not resolved$"):
            fetch_feed("https://outlet.example/feed")

    def test_not_a_feed(self, monkeypatch):
        monkeypatch.setattr(scraper.httpx, "get", respond(content=b"<html><body>Moved</p></div>"))
        with pytest.raises(RuntimeError, match=r"^Not a valid feed: "):
            fetch_feed("https://outlet.example/feed")


def test_fetch_feeds_reports_errors_per_feed_in_order(monkeypatch):
    feeds = {
        "https://ok.example/feed": respond(content=rss_feed(item("Story")).encode()),
        "https://slow.example/feed": respond(exc=httpx.ConnectTimeout("slow")),
        "https://gone.example/feed": respond(status=404),
        "https://html.example/feed": respond(content=b"<html><body>nope</p>"),
    }
    monkeypatch.setattr(scraper.httpx, "get", lambda url, **kw: feeds[url](url, **kw))
    results = fetch_feeds(list(feeds))
    assert [len(articles) for articles, _ in results] == [1, 0, 0, 0]
    errors = [error for _, error in results]
    assert errors[:3] == ["", "Timed out after 15s", "HTTP 404"]
    assert errors[3].startswith("Not a valid feed: ")
