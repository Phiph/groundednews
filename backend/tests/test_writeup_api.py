"""Write-ups as the site reads them: on story detail, on the briefing, and per thread."""
import json
from urllib.parse import quote

import pytest

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
