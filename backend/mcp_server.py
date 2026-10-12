"""GroundedNews MCP server: the scheduled routine and interactive Claude sessions use these
tools to fetch and cluster articles, write framing notes, read stories, and save write-ups.

Runs over stdio; Claude Code starts it from .mcp.json at the repo root:
    venv/bin/python backend/mcp_server.py
It works on the database directly, so the API needn't be running.
"""
import contextlib
import functools
import os
import sys
import threading
from typing import Annotated, Literal, Optional

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

import main
import writeups
from backup_db import backup
from database import engine, init_db
from fetch_articles import active_tags, fetch_new_articles, pending_articles, recent_clusters
from framing_candidates import candidates as framing_candidates
from models import Article, Cluster
from save_clusters import save_clusters as save_cluster_entries
from writeup_candidates import MAX_STORIES, MAX_THREADS, candidates as writeup_candidates

server = MCPServer(
    "groundednews",
    instructions=(
        "GroundedNews news database. Routine: fetch_articles → get_pending_articles (page through) → "
        "save_clusters → get_framing_candidates → save_framing → get_writeup_candidates → read each "
        "subject (get_day / get_thread / get_story) → save_writeup with author='routine'. Interactive "
        "sessions read with list_stories, get_story, search_stories, get_thread, get_day and save "
        "write-ups with the default author='session'. Write-ups are Markdown, grounded only in the "
        "headlines and summaries the tools return."
    ),
)

# Tool calls run one at a time: they share one SQLite file, and stdout is swapped below
_lock = threading.Lock()


def tool(fn):
    """Register `fn` as a tool. stdout carries the MCP protocol, and the backend modules
    print (save_clusters prints its counts), so their output goes to stderr instead.
    ValueErrors (including Pydantic's and WriteupError) become tool errors."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _lock, contextlib.redirect_stdout(sys.stderr):
            try:
                return fn(*args, **kwargs)
            except ValueError as e:
                raise ToolError(str(e)) from e
    return server.tool()(wrapper)


def session() -> Session:
    return Session(engine, expire_on_commit=False)


# ── Pipeline ────────────────────────────────────────────────────────────────

Category = Literal["Politics", "World", "Business", "Tech", "Science", "Health", "Sports",
                   "Entertainment", "Environment"]


class StoryEntry(BaseModel):
    """A new story (no cluster_id; headline and category required), or articles joining an
    existing story (cluster_id from recent_clusters; other fields optional)."""
    cluster_id: Optional[int] = Field(None, description="Existing story to add to; omit for a new story")
    headline: Optional[str] = Field(None, description="Neutral, factual headline")
    summary: Optional[str] = Field(None, description="1-2 sentence neutral summary")
    category: Optional[Category] = None
    tags: list[str] = Field(default_factory=list, description="0-3 ongoing-story tags; reuse active_tags")
    article_ids: list[int] = Field(min_length=1)
    opinion_ids: list[int] = Field(default_factory=list,
                                   description="Articles here that are opinion but not flagged is_opinion")

    @model_validator(mode="after")
    def _complete(self):
        if self.cluster_id is None and not (self.headline or "").strip():
            raise ValueError("a new story needs a headline")
        if self.cluster_id is None and not self.category:
            raise ValueError("a new story needs a category")
        stray = sorted(set(self.opinion_ids) - set(self.article_ids))
        if stray:
            raise ValueError(f"opinion_ids {stray} aren't in this entry's article_ids")
        return self


class FramingNote(BaseModel):
    cluster_id: int
    framing: dict[Literal["left", "center", "right"], str] = Field(
        description="1-2 sentences per side that covered the story, on how its outlets covered it")

    @model_validator(mode="after")
    def _has_a_note(self):
        if not any(note.strip() for note in self.framing.values()):
            raise ValueError(f"story {self.cluster_id}: framing needs at least one non-empty note")
        return self


def _unknown(s: Session, column, ids: set[int]) -> list[int]:
    return sorted(ids - set(s.exec(select(column).where(column.in_(list(ids)))).all()))


@tool
def fetch_articles() -> dict:
    """Fetch every enabled RSS feed and store new articles (the first run each day also backs up
    the database). Returns the run id, counts, recent_clusters (stories new articles may join) and
    active_tags — not the articles themselves: page through get_pending_articles for those."""
    backup()
    with session() as s:
        run = fetch_new_articles(s)
        return {
            "run_id": run.id, "status": run.status, "error": run.error,
            "articles_fetched": run.articles_fetched, "articles_scraped_new": run.articles_new,
            # New plus recent unclustered leftovers: what needs clustering
            "articles_pending": len(pending_articles(s)),
            "recent_clusters": recent_clusters(s), "active_tags": active_tags(s),
        }


@tool
def get_pending_articles(offset: Annotated[int, Field(ge=0)] = 0,
                         limit: Annotated[int, Field(ge=1, le=100)] = 50) -> dict:
    """Articles waiting to be clustered (new and recent unclustered), oldest id first, a page at a time."""
    with session() as s:
        pending = pending_articles(s)
    return {"total": len(pending), "offset": offset, "articles": pending[offset:offset + limit]}


@tool
def save_clusters(clusters: list[StoryEntry], run_id: int = 0) -> dict:
    """Save clustered articles: new stories and follow-ups joining existing ones. The whole batch
    is checked first (unknown articles or stories, an article in two entries) and nothing is
    saved if any check fails. Pass the run_id from fetch_articles to close the run."""
    placed: dict[int, int] = {}
    for i, entry in enumerate(clusters):
        for aid in entry.article_ids:
            if aid in placed:
                raise ValueError(f"article {aid} is in entries {placed[aid]} and {i}; each goes in one story")
            placed[aid] = i
    with session() as s:
        if missing := _unknown(s, Article.id, set(placed)):
            raise ValueError(f"unknown article ids: {missing}")
        if unknown := _unknown(s, Cluster.id, {e.cluster_id for e in clusters if e.cluster_id is not None}):
            raise ValueError(f"unknown cluster ids: {unknown}")
        # The writer deletes a story left with no articles, so it can't also take follow-ups
        for cid in {e.cluster_id for e in clusters if e.cluster_id is not None}:
            current = set(s.exec(select(Article.id).where(Article.cluster_id == cid)).all())
            if current and all(aid in placed and clusters[placed[aid]].cluster_id != cid for aid in current):
                raise ValueError(f"story {cid} would be emptied by this batch (all its articles move to "
                                 "other entries) and can't also take follow-ups")
    counts = save_cluster_entries(run_id, [e.model_dump(exclude_none=True) for e in clusters])
    with session() as s:
        return {**counts, "still_pending": len(pending_articles(s))}


@tool
def get_framing_candidates(limit: Annotated[int, Field(ge=1, le=30)] = 12) -> dict:
    """Stories covered by 2+ sides that need a "how each side framed it" note (none yet, or coverage
    grew since), most important first, with their articles grouped by side."""
    with session() as s:
        return {"stories": framing_candidates(s, limit)}


@tool
def save_framing(notes: list[FramingNote]) -> dict:
    """Save "how each side framed it" notes. Omit sides with no articles."""
    with session() as s:
        if unknown := _unknown(s, Cluster.id, {n.cluster_id for n in notes}):
            raise ValueError(f"unknown cluster ids: {unknown}")
    counts = save_cluster_entries(0, [n.model_dump() for n in notes])
    return {"framings_written": counts["framings_written"]}


@tool
def get_writeup_candidates() -> dict:
    """What the routine should write this run: today's briefing, up to 3 threads and up to 5
    stories with no write-up or a stale one. Write-ups from interactive sessions are never
    included. Read each subject with get_day / get_thread / get_story before writing."""
    with session() as s:
        return {**writeup_candidates(s), "limits": {"briefing": 1, "threads": MAX_THREADS, "stories": MAX_STORIES}}


# ── Reading ─────────────────────────────────────────────────────────────────
# These call the API's own endpoint functions so the MCP and the site see the same stories,
# then trim each story so results stay small: no URLs or images, outlets by name.

_ARTICLE_FIELDS = ("source_name", "bias_label", "title", "summary", "is_opinion", "published_at")


def _brief(story: dict) -> dict:
    keep = ("id", "headline", "summary", "category", "tags", "article_count", "source_count",
            "last_updated", "bias", "is_opinion")
    return {**{k: story[k] for k in keep},
            "outlets": sorted({src["source_name"] for src in story["sources"]})}


def _full(story: dict) -> dict:
    return {**{k: v for k, v in story.items() if k not in ("sources", "image_url")},
            "sources": [{k: src[k] for k in _ARTICLE_FIELDS if k in src} for src in story["sources"]]}


def _stories(s: Session, **filters) -> list[dict]:
    params = dict(category=None, tag=None, blindspot=None, sort="top", min_sources=1, opinion=None,
                  source_id=None, limit=20, offset=0)
    return main.list_clusters(**{**params, **filters}, session=s)


@tool
def list_stories(sort: Literal["top", "latest"] = "top", category: Optional[Category] = None,
                 tag: Optional[str] = None, opinion: Optional[Literal["exclude", "only"]] = None,
                 limit: Annotated[int, Field(ge=1, le=50)] = 20) -> dict:
    """Stories as the site lists them: "top" ranks the last 72h by coverage across the spectrum."""
    with session() as s:
        return {"stories": [_brief(r) for r in _stories(s, sort=sort, category=category, tag=tag,
                                                         opinion=opinion, limit=limit)]}


@tool
def get_story(cluster_id: int) -> dict:
    """One story: every article (outlet, side, title, summary), its framing notes and its write-up."""
    with session() as s:
        try:
            return _full(main.get_cluster(cluster_id, session=s))
        except HTTPException:
            raise ValueError(f"story {cluster_id} not found") from None


@tool
def search_stories(q: str, limit: Annotated[int, Field(ge=1, le=50)] = 20) -> dict:
    """Full-text search over headlines, summaries, tags and outlet titles; best match first."""
    with session() as s:
        found = main.search(q=q, sort="relevance", limit=limit, offset=0, session=s)
    return {"total": found["total"], "results": [_brief(r) for r in found["results"]]}


@tool
def get_thread(tag: str, limit: Annotated[int, Field(ge=1, le=100)] = 30) -> dict:
    """An ongoing thread: the tag's latest stories, oldest first, and its write-up."""
    with session() as s:
        stories = _stories(s, tag=tag, sort="latest", limit=limit)
        if not stories:
            raise ValueError(f"no story is tagged {tag!r}")
        return {"tag": tag, "stories": [_brief(r) for r in reversed(stories)],
                "writeup": writeups.writeup_for(s, "thread", tag)}


@tool
def get_day() -> dict:
    """The current briefing: the 24 hours to the newest story — top stories, each side's
    blindspots, busiest tags — and its write-up. `subject` is the date to save it under."""
    with session() as s:
        day = main.briefing(session=s)
        return {
            "subject": writeups.briefing_date(s),
            **{k: day[k] for k in ("window_start", "window_end", "totals", "tags", "writeup")},
            "stories": [_full(r) for r in day["stories"]],
            "blindspots": {side: [_brief(r) for r in rows] for side, rows in day["blindspots"].items()},
        }


# ── Write-ups ───────────────────────────────────────────────────────────────

@tool
def save_writeup(kind: writeups.Kind, subject: str, title: str, body: str,
                 author: writeups.Author = "session") -> dict:
    """Create or replace a write-up (Markdown body). subject: the cluster id for a story, the
    tag for a thread, the date from get_day for a briefing. The routine must pass
    author="routine"; it can't replace a write-up from an interactive session."""
    with session() as s:
        return writeups.public(s, writeups.save(s, kind, subject, title, body, author))


@tool
def get_writeup(kind: writeups.Kind, subject: str) -> dict:
    """A write-up with its staleness (new_articles since it was written)."""
    with session() as s:
        found = writeups.writeup_for(s, kind, subject)
    if not found:
        raise ValueError(f"no {kind} write-up for {subject!r}")
    return found


@tool
def delete_writeup(kind: writeups.Kind, subject: str) -> dict:
    """Remove a write-up; the site then shows nothing in its place."""
    with session() as s:
        return {"deleted": writeups.delete(s, kind, subject)}


if __name__ == "__main__":
    init_db()
    server.run()
