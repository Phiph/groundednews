import json
from datetime import timedelta

import pytest
from sqlmodel import select

from models import Article, Cluster
from save_clusters import save_clusters
from timeutil import utcnow


@pytest.fixture
def save(db, capsys):
    """Run save_clusters (no scrape run) and return its printed counts. The test's own
    session is expired afterwards so it sees what the script committed."""
    def run(entries):
        capsys.readouterr()
        save_clusters(0, entries)
        db.expire_all()
        return json.loads(capsys.readouterr().out)
    return run


def story_of(db, article):
    db.refresh(article)
    return db.get(Cluster, article.cluster_id)


def test_creates_a_story_from_articles(make, db, save):
    bbc, fox = make.source("BBC", "center-left"), make.source("Fox", "right")
    a1 = make.article(bbc, "Budget passes", hours_ago=5)
    a2 = make.article(fox, "Senate approves budget", hours_ago=2)

    result = save([{"headline": "Senate passes budget", "summary": "It passed.", "category": "Politics",
                    "tags": ["Budget fight"], "article_ids": [a1.id, a2.id]}])

    assert result["clusters_created"] == 1
    story = story_of(db, a1)
    assert story.id == story_of(db, a2).id
    assert (story.headline, story.summary, story.category) == ("Senate passes budget", "It passed.", "Politics")
    assert json.loads(story.tags) == ["Budget fight"]
    assert (story.article_count, story.source_count) == (2, 2)


def test_headline_defaults_to_the_first_articles_title(make, db, save):
    a = make.article(make.source(), "Quake hits coast")
    save([{"article_ids": [a.id]}])
    assert story_of(db, a).headline == "Quake hits coast"


def test_unknown_article_ids_are_ignored(make, db, save):
    a = make.article(make.source())
    assert save([{"headline": "Only ghosts", "article_ids": [9999]}])["clusters_created"] == 0
    save([{"headline": "Real", "article_ids": [a.id, 9999]}])
    assert story_of(db, a).article_count == 1


def test_follow_up_articles_merge_into_an_existing_story(make, db, save):
    bbc, fox, npr = make.source("BBC", "center-left"), make.source("Fox", "right"), make.source("NPR")
    story = make.story(bbc, fox, headline="Senate passes budget", tags='["Budget fight"]')
    follow_up = make.article(npr, "President signs budget")

    result = save([{"cluster_id": story.id, "article_ids": [follow_up.id], "tags": ["Budget fight", "White House"]}])

    assert result == {"clusters_created": 0, "clusters_updated": 1, "clusters_removed": 0, "framings_written": 0}
    db.refresh(story)
    assert story_of(db, follow_up).id == story.id
    assert (story.article_count, story.source_count) == (3, 3)
    assert story.headline == "Senate passes budget"  # untouched when not given
    assert json.loads(story.tags) == ["Budget fight", "White House"]  # added, not duplicated


def test_a_missing_cluster_id_creates_a_new_story(make, db, save):
    a = make.article(make.source())
    result = save([{"cluster_id": 4242, "headline": "Fresh", "article_ids": [a.id]}])
    assert result["clusters_created"] == 1
    assert story_of(db, a).headline == "Fresh"


def test_moving_the_last_article_out_deletes_the_emptied_story(make, db, save):
    bbc, fox = make.source(), make.source()
    keep = make.story(bbc, headline="Keep")
    lonely = make.story(fox, headline="Lonely")
    moved = db.exec(select(Article).where(Article.cluster_id == lonely.id)).one()

    lonely_id = lonely.id

    result = save([{"cluster_id": keep.id, "article_ids": [moved.id]}])

    assert result["clusters_removed"] == 1
    assert db.get(Cluster, lonely_id) is None
    db.refresh(keep)
    assert (keep.article_count, keep.source_count) == (2, 2)


def test_moving_some_articles_out_refreshes_the_old_storys_counts_and_dates(make, db, save):
    bbc, fox, npr = make.source(), make.source(), make.source()
    old = make.story(headline="Old")
    stays = make.article(bbc, cluster=old, hours_ago=10)
    leaves = make.article(fox, cluster=old, hours_ago=2)
    make.refresh(old)
    target = make.story(npr, headline="Target")

    save([{"cluster_id": target.id, "article_ids": [leaves.id]}])

    db.refresh(old)
    assert (old.article_count, old.source_count) == (1, 1)
    assert old.last_updated == stays.published_at
    db.refresh(target)
    assert (target.article_count, target.source_count) == (2, 2)


def test_opinion_ids_mark_articles_as_opinion(make, db, save):
    news, column = make.article(make.source()), make.article(make.source())
    save([{"headline": "Debate", "article_ids": [news.id, column.id], "opinion_ids": [column.id]}])
    db.refresh(news), db.refresh(column)
    assert (news.is_opinion, column.is_opinion) == (False, True)


def test_dates_follow_publication_falling_back_to_when_scraped(make, db, save):
    source = make.source()
    published = make.article(source, hours_ago=30)
    undated = make.article(source, hours_ago=None, scraped_at=utcnow() - timedelta(hours=3))
    save([{"headline": "Timeline", "article_ids": [published.id, undated.id]}])
    story = story_of(db, published)
    assert story.first_seen == published.published_at
    assert story.last_updated == undated.scraped_at


class TestFraming:
    FRAMING = {"left": " Stresses cuts. ", "right": "Stresses deficit.", "center": "", "spin": "ignored"}

    def test_framing_only_entry_sets_framing_and_its_timestamp(self, make, db, save):
        story = make.story(make.source(), make.source(), headline="Budget")
        before = utcnow()
        result = save([{"cluster_id": story.id, "framing": self.FRAMING}])
        assert result == {"clusters_created": 0, "clusters_updated": 0, "clusters_removed": 0, "framings_written": 1}
        db.refresh(story)
        # Trimmed, and only the three sides that have text
        assert json.loads(story.framing) == {"left": "Stresses cuts.", "right": "Stresses deficit."}
        assert before <= story.framing_updated <= utcnow()
        assert story.article_count == 2  # articles untouched

    def test_framing_for_a_missing_story_is_skipped(self, save):
        assert save([{"cluster_id": 4242, "framing": self.FRAMING}])["framings_written"] == 0
