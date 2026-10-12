"""The MCP server's tools, called through a real MCP client (in memory, and once over stdio)."""
import json
import logging
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
from sqlmodel import select

import database
import fetch_articles
import mcp_server
import writeups
from models import Article, Cluster
from scraper import FeedResult

REPO = Path(__file__).resolve().parents[2]


class ToolFailed(Exception):
    pass


def call(name, **args):
    """Call a tool in memory; return its JSON result, or raise ToolFailed with its message."""
    async def go():
        async with Client(mcp_server.server) as client:
            return await client.call_tool(name, args)
    result = anyio.run(go)
    text = result.content[0].text if result.content else ""
    if result.is_error:
        raise ToolFailed(text)
    return json.loads(text)


def test_pipeline_tools_are_listed():
    async def go():
        async with Client(mcp_server.server) as client:
            return {t.name for t in (await client.list_tools()).tools}
    assert {"fetch_articles", "get_pending_articles", "save_clusters", "get_framing_candidates",
            "save_framing", "get_writeup_candidates"} <= anyio.run(go)


class TestFetch:
    def test_returns_counts_and_merge_targets_not_articles(self, make, monkeypatch):
        make.source()
        item = {"title": "Story", "url": "https://news.example/new", "summary": "", "published_at": None,
                "image_url": "https://img.example/a.jpg", "is_opinion": False}
        monkeypatch.setattr(fetch_articles, "fetch_feeds",
                            lambda feeds, max_articles=50: [FeedResult(articles=[item]) for _ in feeds])
        got = call("fetch_articles")
        assert (got["status"], got["articles_scraped_new"], got["articles_pending"]) == ("fetched", 1, 1)
        assert "new_articles" not in got and {"run_id", "recent_clusters", "active_tags"} <= set(got)


class TestPending:
    def test_pages_through_unclustered_articles(self, make):
        src = make.source()
        made = [make.article(src).id for _ in range(5)]
        first = call("get_pending_articles", offset=0, limit=2)
        rest = call("get_pending_articles", offset=2, limit=50)
        assert first["total"] == rest["total"] == 5
        assert [a["id"] for a in first["articles"] + rest["articles"]] == made

    def test_limit_is_bounded(self):
        with pytest.raises(ToolFailed):
            call("get_pending_articles", limit=500)


class TestSaveClusters:
    def test_saves_new_and_follow_up_stories(self, make, db):
        src = make.source()
        existing = make.story(src)
        a, b = make.article(src), make.article(src)
        got = call("save_clusters", clusters=[
            {"headline": "New", "summary": "S", "category": "World", "article_ids": [a.id]},
            {"cluster_id": existing.id, "article_ids": [b.id]},
        ])
        assert (got["clusters_created"], got["clusters_updated"], got["still_pending"]) == (1, 1, 0)

    @pytest.mark.parametrize("entries, message", [
        ([{"headline": "X", "category": "World", "article_ids": [999]}], "unknown article"),
        ([{"cluster_id": 999, "article_ids": ["A"]}], "unknown cluster"),
        ([{"category": "World", "article_ids": ["A"]}], "headline"),
        ([{"headline": "X", "category": "World", "article_ids": ["A"]},
          {"headline": "Y", "category": "World", "article_ids": ["A"]}], "in entries"),
        ([{"headline": "X", "category": "World", "article_ids": ["A"], "opinion_ids": [999]}], "opinion_ids"),
        ([{"headline": "X", "category": "Gossip", "article_ids": ["A"]}], "category"),
    ])
    def test_a_bad_batch_writes_nothing(self, make, db, entries, message):
        a = make.article(make.source())
        for entry in entries:  # "A" stands for the real article's id
            entry["article_ids"] = [a.id if i == "A" else i for i in entry["article_ids"]]
        with pytest.raises(ToolFailed, match=message):
            call("save_clusters", clusters=entries)
        assert db.exec(select(Cluster)).all() == []


class TestFraming:
    def test_saves_notes(self, make, db):
        story = make.story(make.source("L", "left"), make.source("R", "right"))
        got = call("save_framing", notes=[{"cluster_id": story.id, "framing": {"left": "Led with X."}}])
        assert got["framings_written"] == 1
        db.refresh(story)
        assert json.loads(story.framing) == {"left": "Led with X."}

    def test_unknown_story_or_empty_note_is_rejected(self, make):
        story = make.story(make.source())
        with pytest.raises(ToolFailed, match="unknown cluster"):
            call("save_framing", notes=[{"cluster_id": 999, "framing": {"left": "x"}}])
        with pytest.raises(ToolFailed, match="note"):
            call("save_framing", notes=[{"cluster_id": story.id, "framing": {"left": "  "}}])

    def test_candidates(self, make):
        make.story(make.source("L", "left"), make.source("R", "right"))
        assert len(call("get_framing_candidates")["stories"]) == 1


def test_writeup_candidates_include_the_limits(make):
    make.story(make.source())
    got = call("get_writeup_candidates")
    assert got["limits"] == {"briefing": 1, "threads": 3, "stories": 5}
    assert got["briefing"]["reason"] == "new"


def test_stray_prints_never_reach_the_stdio_wire(make, caplog):
    """save_clusters() prints its counts; over real stdio that must go to stderr, not the wire."""
    article = make.article(make.source())
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.engine.url.database}"}
    params = StdioServerParameters(command=sys.executable, args=[str(REPO / "backend" / "mcp_server.py")],
                                   env=env, cwd=str(REPO))

    async def go():
        async with Client(params) as client:
            return await client.call_tool("save_clusters", {"clusters": [
                {"headline": "H", "category": "World", "article_ids": [article.id]}]})
    with caplog.at_level(logging.DEBUG):
        result = anyio.run(go)
    assert not result.is_error, result.content[0].text
    assert not [r for r in caplog.records if "Failed to parse" in r.getMessage()]


class TestRead:
    def test_list_stories_is_brief(self, make):
        make.story(make.source("BBC", "center-left"), headline="Flood", tags='["Floods"]')
        (story,) = call("list_stories", sort="latest")["stories"]
        assert story["headline"] == "Flood" and story["outlets"] == ["BBC"]
        assert "sources" not in story

    def test_get_story_has_summaries_and_writeup_but_no_urls(self, make, db):
        story = make.story(make.source())
        writeups.save(db, "story", str(story.id), "T", "Body", "session")
        got = call("get_story", cluster_id=story.id)
        assert got["writeup"]["body"] == "Body"
        assert "summary" in got["sources"][0] and "url" not in got["sources"][0]

    def test_unknown_story(self):
        with pytest.raises(ToolFailed, match="not found"):
            call("get_story", cluster_id=999)

    def test_search(self, make):
        make.story(make.source(), headline="Hurricane makes landfall")
        assert call("search_stories", q="hurricane")["total"] == 1

    def test_thread_is_oldest_first_with_its_writeup(self, make, db):
        src = make.source()
        make.story(src, headline="Day 1", tags='["Smith trial"]', hours_ago=30)
        make.story(src, headline="Day 2", tags='["Smith trial"]', hours_ago=2)
        writeups.save(db, "thread", "Smith trial", "T", "So far", "routine")
        got = call("get_thread", tag="Smith trial")
        assert [s["headline"] for s in got["stories"]] == ["Day 1", "Day 2"]
        assert got["writeup"]["body"] == "So far"

    def test_unknown_thread(self):
        with pytest.raises(ToolFailed, match="tagged"):
            call("get_thread", tag="Nope")

    def test_get_day_on_an_empty_database(self):
        got = call("get_day")
        assert got["stories"] == [] and got["writeup"] is None

    def test_get_day_names_its_subject(self, make, db):
        make.story(make.source(), make.source())
        assert call("get_day")["subject"] == writeups.briefing_date(db)


class TestWriteupTools:
    def test_save_defaults_to_session_and_round_trips(self, make):
        story = make.story(make.source())
        saved = call("save_writeup", kind="story", subject=str(story.id), title="T", body="**B**")
        assert saved["author"] == "session"
        assert call("get_writeup", kind="story", subject=str(story.id))["body"] == "**B**"
        assert call("delete_writeup", kind="story", subject=str(story.id)) == {"deleted": True}
        with pytest.raises(ToolFailed, match="no story write-up"):
            call("get_writeup", kind="story", subject=str(story.id))

    def test_routine_is_refused_over_a_session_writeup(self, make):
        story = make.story(make.source())
        call("save_writeup", kind="story", subject=str(story.id), title="T", body="Mine")
        with pytest.raises(ToolFailed, match="interactive session"):
            call("save_writeup", kind="story", subject=str(story.id), title="T", body="R", author="routine")

    def test_bad_kind_is_rejected(self):
        with pytest.raises(ToolFailed):
            call("save_writeup", kind="essay", subject="x", title="T", body="B")
