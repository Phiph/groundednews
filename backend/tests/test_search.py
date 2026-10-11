"""The story_fts index is kept in sync by SQLite triggers, whichever script writes."""
import pytest
from sqlalchemy import text
from models import Cluster
from save_clusters import save_clusters


def indexed(db, cluster_id):
    """The story_fts row for a story: (headline, titles), or None."""
    row = db.execute(text("SELECT headline, titles FROM story_fts WHERE rowid = :id"), {"id": cluster_id}).first()
    return tuple(row) if row else None


def matches(db, query):
    return {r[0] for r in db.execute(text("SELECT rowid FROM story_fts WHERE story_fts MATCH :q"), {"q": query})}


class TestIndexTriggers:
    def test_new_story_is_indexed(self, make, db):
        story = make.story(headline="Senate passes budget")
        assert indexed(db, story.id) == ("Senate passes budget", None)

    def test_articles_titles_are_indexed_with_their_story(self, make, db):
        story = make.story(headline="Senate passes budget")
        make.article(make.source(), "Lawmakers approve spending bill", cluster=story)
        assert matches(db, "spending") == {story.id}

    def test_renamed_headline_is_reindexed(self, make, db):
        story = make.story(make.source(), headline="Quake hits coast")
        story.headline = "Earthquake death toll rises"
        make._save(story)
        assert matches(db, "toll") == {story.id}
        assert matches(db, "coast") == set()

    def test_retitled_article_is_reindexed(self, make, db):
        story = make.story(headline="Budget")
        article = make.article(make.source(), "Old wording", cluster=story)
        article.title = "New wording"
        make._save(article)
        assert matches(db, "new") == {story.id}
        assert matches(db, "old") == set()

    def test_moved_article_leaves_its_old_story(self, make, db):
        src = make.source()
        first, second = make.story(headline="First"), make.story(headline="Second")
        make.article(src, "Unrelated filler", cluster=first)
        moving = make.article(src, "Wildfire spreads north", cluster=first)
        save_clusters(0, [{"cluster_id": second.id, "article_ids": [moving.id]}])
        assert matches(db, "wildfire") == {second.id}

    def test_deleted_story_is_removed(self, make, db):
        src = make.source()
        keep = make.story(src, headline="Keep me")
        doomed = make.story(headline="Doomed story")
        moving = make.article(src, "Lone article", cluster=doomed)
        doomed_id = doomed.id
        save_clusters(0, [{"cluster_id": keep.id, "article_ids": [moving.id]}])  # empties and deletes `doomed`
        db.expire_all()
        assert db.get(Cluster, doomed_id) is None
        assert indexed(db, doomed_id) is None
        assert matches(db, "lone") == {keep.id}

    def test_unclustered_articles_are_not_indexed(self, make, db):
        make.article(make.source(), "Floating article")
        assert matches(db, "floating") == set()


class TestSearchEndpoint:
    @pytest.fixture
    def budget(self, make):
        story = make.story(headline="Senate passes budget")
        make.article(make.source("BBC"), "Lawmakers approve spending bill", cluster=story, hours_ago=3)
        make.story(make.source(), headline="Wildfire spreads north")
        return make.refresh(story)

    def search(self, client, q, **params):
        r = client.get("/api/search", params={"q": q, **params})
        assert r.status_code == 200, r.text
        return r.json()

    def test_finds_a_story_by_an_outlets_article_title(self, client, budget):
        body = self.search(client, "spending")
        assert body["total"] == 1
        assert [s["id"] for s in body["results"]] == [budget.id]
        assert body["results"][0]["sources"][0]["source_name"] == "BBC"

    def test_words_are_prefixes_and_all_must_match(self, client, budget):
        assert self.search(client, "budg sen")["total"] == 1
        assert self.search(client, "budget wildfire")["total"] == 0

    @pytest.mark.parametrize("q", [
        'budget AND', 'NEAR(budget', 'budget OR wildfire', '-budget', '"budget', "budget's", "budget*", "senate: budget!",
    ])
    def test_punctuation_and_operator_words_are_taken_literally(self, client, budget, q):
        body = self.search(client, q)
        assert set(body) == {"total", "results"}
        # Each word is a required literal, so only stories containing them all match
        assert [s["id"] for s in body["results"]] in ([budget.id], [])

    def test_operator_words_dont_act_as_operators(self, client, budget):
        # As an operator, OR would match both stories; as a literal word it matches neither
        assert self.search(client, "budget OR wildfire")["total"] == 0

    @pytest.mark.parametrize("q", ["", "!!!", "  ", "\"*()"])
    def test_queries_without_words_return_nothing(self, client, budget, q):
        assert self.search(client, q) == {"total": 0, "results": []}

    def test_latest_sort_and_paging(self, client, make, budget):
        newer = make.story(make.source(), headline="Budget talks resume", hours_ago=0.1)
        body = self.search(client, "budget", sort="latest", limit=1)
        assert body["total"] == 2
        assert [s["id"] for s in body["results"]] == [newer.id]
