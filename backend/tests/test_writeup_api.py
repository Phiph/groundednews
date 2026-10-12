"""Write-ups as the site reads them: on story detail, on the briefing, and per thread."""
import json
from datetime import date, timedelta
from urllib.parse import quote

import pytest

import writeup_candidates
import writeups


def test_story_detail_includes_its_writeup(client, make, db):
    story = make.story(make.source())
    assert client.get(f"/api/clusters/{story.id}").json()["writeup"] is None
    writeups.save(db, "story", str(story.id), "T", "**Body**", "routine")
    w = client.get(f"/api/clusters/{story.id}").json()["writeup"]
    assert (w["body"], w["author"], w["stale"], w["new_articles"]) == ("**Body**", "routine", False, 0)


def test_briefing_includes_the_days_writeup(client, make, db):
    make.story(make.source())
    assert client.get("/api/briefing").json()["writeup"] is None
    writeups.save(db, "briefing", writeups.briefing_date(db), "The day", "Text", "routine")
    assert client.get("/api/briefing").json()["writeup"]["title"] == "The day"


def test_empty_database_briefing_has_no_writeup(client):
    r = client.get("/api/briefing")
    assert r.status_code == 200
    assert r.json()["writeup"] is None


@pytest.mark.parametrize("tag", ["Iran war", "Israel–Gaza", "AI/ML"])
def test_thread_writeup_by_tag(client, make, db, tag):
    make.story(make.source(), tags=json.dumps([tag]))
    url = f"/api/threads/{quote(tag, safe='')}"
    assert client.get(url).status_code == 404
    writeups.save(db, "thread", tag, "Where things stand", "Text", "session")
    r = client.get(url)
    assert r.status_code == 200, r.text
    assert (r.json()["subject"], r.json()["author"]) == (tag, "session")


class TestBriefingRollover:
    """Just after UTC midnight the window still mostly belongs to the previous day."""

    def _yesterday(self, db):
        return (date.fromisoformat(writeups.briefing_date(db)) - timedelta(days=1)).isoformat()

    def test_falls_back_to_yesterdays_writeup_marked_stale(self, client, make, db):
        make.story(make.source())
        writeups.save(db, "briefing", self._yesterday(db), "Yesterday", "Text", "routine")
        w = client.get("/api/briefing").json()["writeup"]
        assert (w["title"], w["subject"], w["stale"]) == ("Yesterday", self._yesterday(db), True)

    def test_todays_writeup_wins(self, client, make, db):
        make.story(make.source())
        writeups.save(db, "briefing", self._yesterday(db), "Yesterday", "Text", "routine")
        writeups.save(db, "briefing", writeups.briefing_date(db), "Today", "Text", "routine")
        w = client.get("/api/briefing").json()["writeup"]
        assert (w["title"], w["stale"]) == ("Today", False)

    def test_a_two_day_old_writeup_is_not_shown(self, client, make, db):
        make.story(make.source())
        old = (date.fromisoformat(writeups.briefing_date(db)) - timedelta(days=2)).isoformat()
        writeups.save(db, "briefing", old, "Old", "Text", "routine")
        assert client.get("/api/briefing").json()["writeup"] is None

    def test_routine_is_still_offered_the_new_date(self, make, db):
        make.story(make.source())
        writeups.save(db, "briefing", self._yesterday(db), "Yesterday", "Text", "routine")
        got = writeup_candidates.candidates(db)["briefing"]
        assert got["subject"] == writeups.briefing_date(db)
