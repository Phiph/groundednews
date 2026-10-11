"""The helpers the scheduled Claude session relies on: merge targets, framing candidates, backups."""
import sqlite3
from datetime import date, timedelta

import pytest

import backup_db
from fetch_articles import recent_clusters
from framing_candidates import candidates
from save_clusters import save_clusters
from timeutil import utcnow


class TestRecentClusters:
    def offered(self, db):
        return {c["headline"] for c in recent_clusters(db)}

    def test_stories_with_recent_articles_are_offered(self, make, db):
        src = make.source()
        make.story(src, headline="Fresh")
        make.story(src, headline="Stale", hours_ago=72)
        assert self.offered(db) == {"Fresh"}

    def test_latest_story_for_a_quiet_tag_is_offered_even_when_old(self, make, db):
        src = make.source()
        make.story(src, headline="Trial day 3", tags='["Smith trial"]', hours_ago=24 * 4)
        make.story(src, headline="Trial day 1", tags='["Smith trial"]', hours_ago=24 * 6)
        assert self.offered(db) == {"Trial day 3"}

    def test_old_story_isnt_offered_for_a_tag_a_recent_story_covers(self, make, db):
        src = make.source()
        make.story(src, headline="War today", tags='["Iran war"]')
        make.story(src, headline="War last week", tags='["Iran war"]', hours_ago=24 * 5)
        assert self.offered(db) == {"War today"}

    def test_old_story_with_one_uncovered_tag_is_offered(self, make, db):
        src = make.source()
        make.story(src, headline="War today", tags='["Iran war"]')
        make.story(src, headline="Oil shock", tags='["Iran war", "Oil prices"]', hours_ago=24 * 5)
        assert self.offered(db) == {"War today", "Oil shock"}

    def test_untagged_and_very_old_tagged_stories_are_not_offered(self, make, db):
        src = make.source()
        make.story(src, headline="Untagged", hours_ago=24 * 4)
        make.story(src, headline="Ancient", tags='["Old saga"]', hours_ago=24 * 20)
        assert self.offered(db) == set()

    def test_result_shape(self, make, db):
        story = make.story(make.source(), headline="Fresh", category="World", tags='["Iran war"]')
        assert recent_clusters(db) == [{
            "cluster_id": story.id, "headline": "Fresh", "category": "World", "tags": ["Iran war"],
            "last_updated": story.last_updated.strftime("%Y-%m-%d"),
        }]


class TestFramingCandidates:
    @pytest.fixture
    def outlets(self, make):
        return make.source("Left", "center-left"), make.source("Center", "center"), make.source("Right", "right")

    def candidate_ids(self, db):
        db.expire_all()
        return [c["cluster_id"] for c in candidates(db)]

    def test_stories_covered_by_two_sides_without_framing(self, make, db, outlets):
        left, center, right = outlets
        two_sides = make.story(left, right)
        make.story(left, make.source("Left 2", "left"))  # two outlets, one side
        make.story(center)  # one outlet
        assert self.candidate_ids(db) == [two_sides.id]

    def test_articles_are_grouped_by_side(self, make, db, outlets):
        left, center, right = outlets
        make.story(left, center, headline="Budget")
        [story] = candidates(db)
        assert story["headline"] == "Budget"
        assert story["current_framing"] == {}
        assert {side: len(items) for side, items in story["articles_by_side"].items()} == {
            "left": 1, "center": 1, "right": 0}

    def test_fresh_framing_is_skipped_until_a_newer_article_arrives(self, make, db, outlets):
        left, center, right = outlets
        story = make.story(left, right, hours_ago=2)
        save_clusters(0, [{"cluster_id": story.id, "framing": {"left": "a", "right": "b"}}])
        assert self.candidate_ids(db) == []

        # Backdate the framing so the follow-up below is clearly newer, without sleeping
        db.refresh(story)
        story.framing_updated = utcnow() - timedelta(hours=1)
        make._save(story)
        assert self.candidate_ids(db) == []

        make.article(center, cluster=story, scraped_at=utcnow())
        make.refresh(story)
        [again] = candidates(db)
        assert again["cluster_id"] == story.id
        assert again["current_framing"] == {"left": "a", "right": "b"}


class TestBackup:
    @pytest.fixture
    def backup_dir(self, tmp_path, monkeypatch):
        target = tmp_path / "backups"
        monkeypatch.setattr(backup_db, "BACKUP_DIR", target)
        return target

    def test_creates_a_dated_copy_that_passes_integrity_check(self, make, backup_dir):
        make.source("Kept in the backup")
        made = backup_db.backup()
        assert made == backup_dir / f"groundednews-{date.today().isoformat()}.db"
        with sqlite3.connect(made) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert conn.execute("SELECT name FROM source").fetchall() == [("Kept in the backup",)]
        assert not list(backup_dir.glob("*.partial"))

    def test_second_call_the_same_day_is_a_no_op(self, backup_dir):
        first = backup_db.backup()
        stamp = first.stat().st_mtime_ns
        assert backup_db.backup() is None
        assert first.stat().st_mtime_ns == stamp

    def test_force_replaces_todays_copy(self, backup_dir):
        backup_db.backup()
        assert backup_db.backup(force=True) is not None

    def test_keeps_only_the_newest_seven(self, backup_dir):
        backup_dir.mkdir()
        for day in range(1, 10):
            (backup_dir / f"groundednews-2026-01-{day:02d}.db").write_bytes(b"")
        (backup_dir / "notes.txt").write_text("not a backup")

        made = backup_db.backup()

        kept = sorted(p.name for p in backup_dir.glob("groundednews-*.db"))
        assert len(kept) == 7
        assert kept[-1] == made.name
        assert kept[0] == "groundednews-2026-01-04.db"
        assert (backup_dir / "notes.txt").exists()

    def test_never_writes_to_the_project_backups_folder(self, backup_dir):
        assert backup_db.BACKUP_DIR != backup_db.PROJECT_ROOT / "backups"
