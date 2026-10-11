"""fetch_new_articles: how conditional fetches feed into a source's health and validators."""
import pytest

import fetch_articles
from models import Source
from scraper import FeedResult

ITEM = {"title": "Story", "url": "https://news.example/story", "summary": "", "published_at": None,
        "image_url": "https://img.example/a.jpg", "is_opinion": False}


@pytest.fixture
def feed_returns(monkeypatch):
    """Make every outlet's fetch return `result`. Returns the (url, etag, last_modified)
    requests made from then on."""
    def install(result: FeedResult):
        sent = []

        def fake_fetch_feeds(feeds, max_articles=50):
            sent.extend(feeds)
            return [result for _ in feeds]
        monkeypatch.setattr(fetch_articles, "fetch_feeds", fake_fetch_feeds)
        return sent
    return install


def fetch(db, source: Source) -> Source:
    fetch_articles.fetch_new_articles(db)
    db.refresh(source)
    return source


def test_validators_from_a_good_fetch_are_stored_and_sent_next_time(make, db, feed_returns):
    source = make.source()
    feed_returns(FeedResult(articles=[ITEM], etag='"v1"', last_modified="Sun, 11 Oct 2026 01:00:00 GMT"))
    source = fetch(db, source)
    assert (source.etag, source.last_modified) == ('"v1"', "Sun, 11 Oct 2026 01:00:00 GMT")

    sent = feed_returns(FeedResult(not_modified=True, etag='"v1"'))
    fetch(db, source)
    assert sent == [(source.feed_url, '"v1"', "Sun, 11 Oct 2026 01:00:00 GMT")]


def test_not_modified_is_a_healthy_fetch_that_keeps_the_item_count(make, db, feed_returns):
    source = make.source(failure_streak=1, last_error="HTTP 500", article_count=12)
    feed_returns(FeedResult(not_modified=True, etag='"v1"'))
    source = fetch(db, source)
    assert source.last_error == "" and source.failure_streak == 0
    assert source.last_success is not None
    assert source.article_count == 12


def test_failed_fetch_keeps_the_previous_validators(make, db, feed_returns):
    source = make.source(etag='"v1"', last_modified="Sun, 11 Oct 2026 01:00:00 GMT")
    feed_returns(FeedResult(error="HTTP 500"))
    source = fetch(db, source)
    assert source.failure_streak == 1
    assert source.etag == '"v1"'


def test_empty_feed_is_a_failure_and_its_validators_arent_kept(make, db, feed_returns):
    source = make.source(etag='"v1"')
    feed_returns(FeedResult(etag='"empty"'))
    source = fetch(db, source)
    assert source.last_error == "Feed returned no items"
    assert source.etag == '"v1"'


def test_changing_the_feed_url_clears_validators(make, db, client):
    source = make.source(etag='"v1"', last_modified="Sun, 11 Oct 2026 01:00:00 GMT")
    assert client.patch(f"/api/sources/{source.id}", json={"bias_label": "left"}).status_code == 200
    db.refresh(source)
    assert source.etag == '"v1"'
    assert client.patch(f"/api/sources/{source.id}", json={"feed_url": "https://new.example/rss"}).status_code == 200
    db.refresh(source)
    assert (source.etag, source.last_modified) == ("", "")


def test_patch_ignores_fields_the_admin_page_cant_set(make, db, client):
    source = make.source(failure_streak=3)
    r = client.patch(f"/api/sources/{source.id}", json={"failure_streak": 0, "id": 999, "etag": "x"})
    assert r.status_code == 200
    db.refresh(source)
    assert (source.id, source.failure_streak, source.etag) == (r.json()["id"], 3, "")
