from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import main
from database import DEFAULT_SOURCES
from models import Cluster
from timeutil import utcnow


def ids(stories):
    return sorted(s["id"] for s in stories)


def get(client, url, **params):
    r = client.get(url, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_startup_seeds_the_default_outlets_into_an_empty_database():
    with TestClient(main.app) as c:
        names = [s["name"] for s in get(c, "/api/sources")]
    assert len(names) == len(DEFAULT_SOURCES) == 17
    assert "BBC News" in names


class TestClusterFilters:
    @pytest.fixture
    def stories(self, make):
        left, right = make.source("Left", "left"), make.source("Right", "right")
        news = make.story(left, right, headline="News")
        opinion = make.story(right, headline="Opinion only", opinion=True)
        # News and opinion on one story: it has straight reporting, so it's news
        mixed = make.story(left, headline="Mixed")
        make.article(right, cluster=mixed, is_opinion=True)
        make.refresh(mixed)
        # Fetched but not clustered yet: cluster_id is NULL
        make.article(left, "Unclustered")
        return {"news": news, "opinion": opinion, "mixed": mixed, "left": left, "right": right}

    def test_opinion_only(self, client, stories):
        assert ids(get(client, "/api/clusters", opinion="only")) == [stories["opinion"].id]

    def test_opinion_excluded(self, client, stories):
        assert ids(get(client, "/api/clusters", opinion="exclude")) == sorted([stories["news"].id, stories["mixed"].id])

    def test_no_opinion_filter(self, client, stories):
        assert len(get(client, "/api/clusters")) == 3

    def test_source_filter(self, client, stories):
        assert ids(get(client, "/api/clusters", source_id=stories["left"].id)) == sorted(
            [stories["news"].id, stories["mixed"].id])
        assert ids(get(client, "/api/clusters", source_id=stories["right"].id)) == sorted(
            [stories["news"].id, stories["opinion"].id, stories["mixed"].id])

    def test_filters_work_with_top_sort(self, client, stories):
        assert ids(get(client, "/api/clusters", opinion="only", sort="top")) == [stories["opinion"].id]


def test_sources_summary_counts_every_opinion_piece(client, make):
    columnist, quiet = make.source("Columnist", "right"), make.source("Quiet")
    for _ in range(3):
        make.article(columnist, is_opinion=True)
    make.article(columnist)
    make.story(columnist)

    rows = {s["name"]: s for s in get(client, "/api/sources/summary")["sources"]}

    assert rows["Columnist"]["articles"] == 5
    assert rows["Columnist"]["opinion"] == 3
    assert rows["Columnist"]["stories"] == 1  # unclustered articles aren't stories
    assert (rows["Quiet"]["articles"], rows["Quiet"]["opinion"], rows["Quiet"]["latest_article"]) == (0, 0, None)


def test_source_profile_missed_lists_only_stories_the_outlet_skipped(client, make):
    a, b, c, d, e = (make.source(f"Outlet {x}") for x in "ABCDE")
    with_a = make.story(a, b, c, d, headline="A covered this")
    without_a = make.story(b, c, d, e, headline="A skipped this")
    make.story(b, c, e, headline="Too few outlets to count as missed")
    make.article(a, "Unclustered from A")

    profile = get(client, f"/api/sources/{a.id}")

    assert [s["id"] for s in profile["missed"]] == [without_a.id]
    assert profile["stories"] == 1
    assert profile["articles"] == 2
    assert [s["id"] for s in get(client, f"/api/sources/{e.id}")["missed"]] == [with_a.id]


def test_source_profile_404(client):
    assert client.get("/api/sources/999").status_code == 404


class TestBriefing:
    def test_empty_database(self, client):
        assert get(client, "/api/briefing") == {
            "window_start": None, "window_end": None, "stories": [],
            "blindspots": {"left": [], "right": []}, "tags": [],
            "totals": {"stories": 0, "articles": 0, "outlets": 0},
        }

    def test_shape_and_story_selection(self, client, make):
        l1, l2, l3 = (make.source(f"L{i}", "left") for i in range(3))
        right = make.source("R", "right")
        wide = make.story(l1, right, headline="Covered across the spectrum", tags='["Budget fight"]')
        blindspot = make.story(l1, l2, l3, headline="Left-only story")
        opinion = make.story(l1, right, headline="Dueling columns", opinion=True)
        single = make.story(l2, headline="One outlet")
        stale = make.story(l1, right, headline="Two days old", hours_ago=50)

        body = get(client, "/api/briefing")

        assert set(body) == {"window_start", "window_end", "stories", "blindspots", "tags", "totals"}
        story_ids = [s["id"] for s in body["stories"]]
        assert wide.id in story_ids and blindspot.id in story_ids
        assert opinion.id not in story_ids  # opinion-only
        assert single.id not in story_ids  # needs two outlets
        assert stale.id not in story_ids  # outside the 24h window
        assert [s["id"] for s in body["blindspots"]["right"]] == [blindspot.id]
        assert body["blindspots"]["left"] == []
        assert body["tags"] == [{"tag": "Budget fight", "count": 1}]
        assert set(body["totals"]) == {"stories", "articles", "outlets"}
        assert body["stories"][0]["sources"][0].keys() >= {"source_name", "bias_label", "title", "url"}


def test_quality_reports_daily_multi_source_share(client, db):
    now = utcnow()
    day1 = (now - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
    day2 = day1 + timedelta(days=1)
    for first_seen, sources in [(day1, 2), (day1, 3), (day1, 1), (day2, 1), (now - timedelta(days=40), 5)]:
        db.add(Cluster(headline="x", source_count=sources, first_seen=first_seen))
    db.commit()

    assert get(client, "/api/stats/quality", days=14) == [
        {"date": day1.date().isoformat(), "stories": 3, "multi_source": 2, "share": 0.667},
        {"date": day2.date().isoformat(), "stories": 1, "multi_source": 0, "share": 0.0},
    ]
    assert get(client, "/api/stats/quality", days=1) == []
