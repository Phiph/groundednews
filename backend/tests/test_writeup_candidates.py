"""What the routine is asked to write each run."""
import json

import writeups
from writeup_candidates import MAX_STORIES, MAX_THREADS, candidates


def both_sides(make):
    return make.source("Left", "left"), make.source("Right", "right")


def test_empty_database_has_nothing_to_write(db):
    assert candidates(db) == {"briefing": None, "threads": [], "stories": []}


def test_briefing_is_offered_every_run_until_written_in_a_session(make, db):
    make.story(make.source())
    day = writeups.briefing_date(db)
    assert candidates(db)["briefing"] == {"subject": day, "reason": "new"}
    writeups.save(db, "briefing", day, "Day", "Text", "routine")
    assert candidates(db)["briefing"] == {"subject": day, "reason": "refresh"}
    writeups.save(db, "briefing", day, "Day", "Mine", "session")
    assert candidates(db)["briefing"] is None


def test_stories_need_two_sides_and_are_capped(make, db):
    left, right = both_sides(make)
    for i in range(MAX_STORIES + 2):
        make.story(left, right, headline=f"Both {i}")
    make.story(left, make.source("Left 2", "left"), headline="One side")
    got = candidates(db)["stories"]
    assert len(got) == MAX_STORIES
    assert all(s["headline"].startswith("Both") and s["reason"] == "new" for s in got)


def test_story_with_a_fresh_writeup_waits_until_it_goes_stale(make, db):
    left, right = both_sides(make)
    story = make.story(left, right)
    writeups.save(db, "story", str(story.id), "T", "Text", "routine")
    assert candidates(db)["stories"] == []
    make.article(right, cluster=story)
    make.refresh(story)
    assert [(s["cluster_id"], s["reason"]) for s in candidates(db)["stories"]] == [(story.id, "stale")]


def test_session_story_writeups_are_never_offered(make, db):
    left, right = both_sides(make)
    story = make.story(left, right)
    writeups.save(db, "story", str(story.id), "T", "Mine", "session")
    make.article(right, cluster=story)
    make.refresh(story)
    assert candidates(db)["stories"] == []


def test_threads_need_two_stories_and_are_capped(make, db):
    src = make.source()
    for tag in ["A", "B", "C", "D"]:
        make.story(src, tags=json.dumps([tag]))
        make.story(src, tags=json.dumps([tag]))
    make.story(src, tags='["Solo"]')
    got = candidates(db)["threads"]
    assert len(got) == MAX_THREADS
    assert "Solo" not in {t["tag"] for t in got}
    assert all(t["stories"] == 2 and t["reason"] == "new" for t in got)


def test_thread_with_a_fresh_writeup_is_skipped(make, db):
    src = make.source()
    make.story(src, tags='["Iran war"]')
    make.story(src, tags='["Iran war"]')
    writeups.save(db, "thread", "Iran war", "T", "Text", "routine")
    assert candidates(db)["threads"] == []
