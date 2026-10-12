"""Write-ups: subject checks, the overwrite rule, staleness, and cleanup when a story goes."""
from datetime import timedelta

import pytest
from sqlmodel import select

import writeups
from models import Article
from save_clusters import save_clusters
from timeutil import utcnow
from writeups import WriteupError


def save(db, kind, subject, author="routine", body="Body text", title="Title"):
    return writeups.save(db, kind, subject, title, body, author)


class TestSubjects:
    def test_story_needs_an_existing_cluster(self, make, db):
        story = make.story(make.source())
        assert save(db, "story", str(story.id)).subject == str(story.id)
        with pytest.raises(WriteupError, match="not found"):
            save(db, "story", "99999")
        with pytest.raises(WriteupError, match="not found"):
            save(db, "story", "abc")

    def test_thread_needs_a_tag_in_use(self, make, db):
        make.story(make.source(), tags='["Iran war"]')
        assert save(db, "thread", "Iran war").subject == "Iran war"
        with pytest.raises(WriteupError, match="tagged"):
            save(db, "thread", "Iran")  # a prefix of a real tag is not that tag

    def test_briefing_needs_a_valid_date_not_in_the_future(self, db):
        today = utcnow().date()
        assert save(db, "briefing", today.isoformat()).subject == today.isoformat()
        with pytest.raises(WriteupError, match="date"):
            save(db, "briefing", "yesterday")
        with pytest.raises(WriteupError, match="future"):
            save(db, "briefing", (today + timedelta(days=2)).isoformat())

    def test_empty_body_is_rejected(self, make, db):
        story = make.story(make.source())
        with pytest.raises(WriteupError, match="empty"):
            save(db, "story", str(story.id), body="   ")


class TestOverwriteRule:
    def test_routine_cannot_overwrite_a_session_writeup(self, make, db):
        story = make.story(make.source())
        save(db, "story", str(story.id), author="session", body="Mine")
        with pytest.raises(WriteupError, match="interactive session"):
            save(db, "story", str(story.id), author="routine", body="Routine's")
        assert writeups.get(db, "story", str(story.id)).body == "Mine"

    def test_session_overwrites_the_routine_and_takes_authorship(self, make, db):
        story = make.story(make.source())
        save(db, "story", str(story.id), author="routine", body="Draft")
        save(db, "story", str(story.id), author="session", body="Edited")
        rows = db.exec(select(writeups.Writeup)).all()
        assert [(w.author, w.body) for w in rows] == [("session", "Edited")]

    def test_routine_refreshes_its_own(self, make, db):
        story = make.story(make.source())
        save(db, "story", str(story.id), body="First")
        assert save(db, "story", str(story.id), body="Second").body == "Second"

    def test_delete(self, make, db):
        story = make.story(make.source())
        save(db, "story", str(story.id))
        assert writeups.delete(db, "story", str(story.id)) is True
        assert writeups.delete(db, "story", str(story.id)) is False
        assert writeups.get(db, "story", str(story.id)) is None


class TestStaleness:
    def test_story_goes_stale_when_it_gains_articles(self, make, db):
        a, b = make.source(), make.source()
        story = make.story(a)
        w = save(db, "story", str(story.id))
        assert writeups.public(db, w)["stale"] is False
        make.article(b, cluster=story)
        make.refresh(story)
        assert (writeups.public(db, w)["stale"], writeups.public(db, w)["new_articles"]) == (True, 1)
        assert save(db, "story", str(story.id)).basis_count == 2

    def test_thread_counts_articles_across_its_stories(self, make, db):
        a, b = make.source(), make.source()
        make.story(a, tags='["Iran war"]')
        w = save(db, "thread", "Iran war")
        assert w.basis_count == 1
        make.story(a, b, tags='["Iran war", "Oil prices"]')
        assert writeups.public(db, w)["new_articles"] == 2

    def test_briefing_counts_the_24_hours_to_the_newest_story(self, make, db):
        src = make.source()
        make.story(src, hours_ago=1)
        make.story(src, hours_ago=30)  # outside the window
        w = save(db, "briefing", writeups.briefing_date(db))
        assert w.basis_count == 1
        make.story(src, hours_ago=0.5)
        assert writeups.public(db, w)["new_articles"] == 1

    def test_public_shape(self, make, db):
        story = make.story(make.source())
        w = save(db, "story", str(story.id), title="T", body="B")
        assert set(writeups.public(db, w)) == {
            "kind", "subject", "title", "body", "author", "updated_at", "stale", "new_articles"}
        assert writeups.writeup_for(db, "story", "424242") is None


def test_a_story_emptied_by_save_clusters_loses_its_writeup(make, db):
    src = make.source()
    old, new = make.story(src), make.story(src)
    old_id = str(old.id)  # read before the row is deleted; the session can't reload it after
    save(db, "story", old_id)
    moved = db.exec(select(Article.id).where(Article.cluster_id == old.id)).one()
    save_clusters(0, [{"cluster_id": new.id, "article_ids": [moved]}])
    db.expire_all()
    assert writeups.get(db, "story", old_id) is None


def test_save_clusters_returns_its_counts(make, db):
    src = make.source()
    article = make.article(src)
    counts = save_clusters(0, [{"headline": "H", "article_ids": [article.id]}])
    assert counts["clusters_created"] == 1
