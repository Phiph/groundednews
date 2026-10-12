# GroundedNews MCP Server and Write-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stdio MCP server that the scheduled routine and interactive Claude sessions use to fetch, cluster, frame and read stories and to save three kinds of Markdown write-ups (story, daily briefing, thread), which the site then shows.

**Architecture:** `backend/mcp_server.py` (MCP SDK 2.x `MCPServer`) imports the existing backend modules and uses the shared SQLite engine directly; the FastAPI backend need not be running. A new `Writeup` table plus `backend/writeups.py` holds write-up rules (subject checks, the routine-never-overwrites-session rule, staleness). `backend/writeup_candidates.py` picks what the routine writes each run. The API adds write-ups to existing responses plus one new endpoint; the frontend renders them with a shared card.

**Tech Stack:** Python 3.13, FastAPI 0.143, SQLModel 0.0.48, `mcp` 2.3.0, pytest 8; Next.js 16, React 19, SWR, Tailwind v4, shadcn/ui, `react-markdown` 10.

**Spec:** `docs/superpowers/specs/2026-10-12-mcp-article-management-design.md`

## Global Constraints

- MCP SDK is `mcp==2.3.0`: import `from mcp.server.mcpserver import MCPServer` (there is no `mcp.server.fastmcp` in 2.x), tool errors via `from mcp.server.mcpserver.exceptions import ToolError`, test client `from mcp.client.client import Client`.
- Every new datetime model field is annotated `NaiveDatetime` (naive UTC, via `timeutil.utcnow()`).
- Every endpoint keeps a `response_model`; after changing `backend/schemas.py`, run `npm run gen:api` in `frontend/`.
- Write-up kinds are exactly `story` · `briefing` · `thread`; authors exactly `routine` · `session`. Subjects: cluster id as a string · UTC date `YYYY-MM-DD` · tag name.
- Per-run routine limits: 1 briefing (~200–350 words), up to 3 threads (~150–250 words), up to 5 stories (~150–300 words).
- The routine never overwrites a write-up whose `author` is `session`.
- The website never writes write-ups (no write endpoint, no editing UI).
- Existing scripts (`fetch_articles.py`, `save_clusters.py`, `framing_candidates.py`) keep their CLI behaviour and tests; `save_clusters.py` stays lenient (warn and skip).
- Images are hotlinked, never downloaded; no Anthropic API calls from the backend.
- Every MCP tool returns a `dict` (so each result is one JSON text block).
- Tests: `cd backend && ../venv/bin/python -m pytest -q`, always against the temp DB from `tests/conftest.py`.

## Review Focus

1. **Tags with `/` or non-ASCII punctuation** (`AI/ML`, `Israel–Gaza`) must resolve on `GET /api/threads/{tag}` — owned by Task 2 (parametrized test).
2. **A story emptied by `save_clusters`** (its articles moved to another story) must take its write-up with it, or a later cluster reusing the id would show a stranger's write-up — owned by Task 1 (cleanup test).
3. **Anything a backend module prints during a tool call** (e.g. `save_clusters()` prints its counts) must not reach the stdio wire — owned by Task 4 (real subprocess test asserting the client logged no parse failures).
4. **An empty database** (fresh install, before the first fetch) must not crash `get_writeup_candidates`, `get_day` or `/api/briefing` — owned by Tasks 2, 3 and 5.
5. **Markdown bodies containing raw HTML or `javascript:` links** must render as inert text/links — owned by Task 6 (seeded hostile body checked in the browser).

---

## Before you start (worktree setup)

The worktree has no venv, `node_modules` or database. Run once from the worktree root
(`/Users/phill/Documents/Projects/groundednews/.claude/worktrees/mcp-article-management-cbdac8`):

```bash
ln -s /Users/phill/Documents/Projects/groundednews/venv venv
```

```bash
cp /Users/phill/Documents/Projects/groundednews/backend/groundednews.db backend/groundednews.db
```

```bash
cd frontend && npm install
```

`venv/`, `backend/groundednews.db` and `node_modules/` are gitignored; never commit them. Check the baseline passes:

```bash
cd backend && ../venv/bin/python -m pytest -q
```

Expected: all tests pass (129 at last count).

---

### Task 1: Writeup model and rules

**Files:**
- Modify: `backend/models.py` (add `Writeup` after `Cluster`)
- Modify: `backend/database.py:4` (busy timeout)
- Create: `backend/writeups.py`
- Modify: `backend/save_clusters.py` (return counts; prune write-ups of deleted stories)
- Modify: `backend/tests/conftest.py` (`clean_db` empties `writeup`)
- Test: `backend/tests/test_writeups.py`

**Interfaces:**
- Consumes: `models.Cluster`, `timeutil.utcnow`
- Produces:
  - `models.Writeup` (table `writeup`; fields `id, kind, subject, title, body, author, basis_count, created_at, updated_at`)
  - `writeups.Kind = Literal["story", "briefing", "thread"]`, `writeups.Author = Literal["routine", "session"]`
  - `writeups.WriteupError(ValueError)`
  - `writeups.BRIEFING_WINDOW: timedelta` (24h)
  - `writeups.briefing_end(session, day: date | None = None) -> datetime | None`
  - `writeups.briefing_date(session) -> str` (ISO date of the newest story, or today if none)
  - `writeups.tag_filter(tag: str)` (SQL condition: cluster carries exactly this tag)
  - `writeups.current_count(session, kind, subject) -> int`
  - `writeups.check_subject(session, kind, subject) -> str` (normalised subject; raises `WriteupError`)
  - `writeups.get(session, kind, subject) -> Writeup | None`
  - `writeups.save(session, kind, subject, title, body, author) -> Writeup`
  - `writeups.delete(session, kind, subject) -> bool`
  - `writeups.public(session, w: Writeup) -> dict` with keys `kind, subject, title, body, author, updated_at, stale, new_articles`
  - `writeups.writeup_for(session, kind, subject) -> dict | None`
  - `save_clusters.save_clusters(run_id, data) -> dict` (now also returns the counts it prints)

- [ ] **Step 1: Make tests start from an empty `writeup` table**

In `backend/tests/conftest.py`, change the `clean_db` table list:

```python
        for table in ("article", "cluster", "scraperun", "source", "story_fts", "writeup"):
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_writeups.py`:

```python
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
    save(db, "story", str(old.id))
    moved = db.exec(select(Article.id).where(Article.cluster_id == old.id)).one()
    save_clusters(0, [{"cluster_id": new.id, "article_ids": [moved]}])
    db.expire_all()
    assert writeups.get(db, "story", str(old.id)) is None


def test_save_clusters_returns_its_counts(make, db):
    src = make.source()
    article = make.article(src)
    counts = save_clusters(0, [{"headline": "H", "article_ids": [article.id]}])
    assert counts["clusters_created"] == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_writeups.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'writeups'`.

- [ ] **Step 4: Add the model**

In `backend/models.py`, add `from sqlalchemy import UniqueConstraint` to the imports, and after the `Cluster` class:

```python
class Writeup(SQLModel, table=True):
    """A longer AI-written piece the site shows: a story write-up, a day's briefing or an
    ongoing thread's summary. Written through the MCP server (mcp_server.py); see writeups.py."""
    __table_args__ = (UniqueConstraint("kind", "subject"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)   # "story" | "briefing" | "thread"
    subject: str                    # cluster id, UTC date "YYYY-MM-DD", or tag name
    title: str = ""
    body: str = ""                  # Markdown
    author: str = "routine"         # "routine" (scheduled task) | "session" (interactive)
    # The subject's article count when written; more articles since means it's stale
    basis_count: int = 0
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)
```

`init_db()` creates the new table via `create_all`; no `_ADDED_COLUMNS` entry is needed.

- [ ] **Step 5: Add the SQLite busy timeout**

In `backend/database.py`, replace line 4:

```python
# The API and the MCP server can write at the same moment; wait for the lock instead of failing
engine = create_engine(
    DATABASE_URL, echo=False,
    connect_args={"timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)
```

- [ ] **Step 6: Write `backend/writeups.py`**

```python
"""Write-ups: longer AI-written pieces the site shows next to the generated data.

- story:    a story page's write-up; subject is the cluster id
- briefing: the written "day in brief" on /briefing; subject is the UTC date of the newest story
- thread:   "where things stand" for an ongoing tag; subject is the tag

The scheduled routine drafts them and interactive sessions write or rewrite them, both through
mcp_server.py. The routine never overwrites one written in a session.
"""
import json
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from sqlalchemy import func
from sqlmodel import Session, select

from models import Cluster, Writeup
from timeutil import utcnow

Kind = Literal["story", "briefing", "thread"]
Author = Literal["routine", "session"]
KINDS = ("story", "briefing", "thread")

BRIEFING_WINDOW = timedelta(hours=24)  # matches /api/briefing


class WriteupError(ValueError):
    """A bad subject or body, or a save that would overwrite the user's own write-up."""


def tag_filter(tag: str):
    """Clusters carrying exactly this tag (tags are stored as a JSON list)."""
    return Cluster.tags.contains(json.dumps(tag), autoescape=True)


def briefing_end(session: Session, day: Optional[date] = None) -> Optional[datetime]:
    """End of a briefing window: the newest story overall, or the newest updated on or before
    `day` (UTC). /api/briefing's window likewise ends at the newest story, not now."""
    q = select(Cluster.last_updated).order_by(Cluster.last_updated.desc())
    if day:
        q = q.where(Cluster.last_updated < datetime.combine(day + timedelta(days=1), datetime.min.time()))
    return session.exec(q).first()


def briefing_date(session: Session) -> str:
    """The subject of the current briefing: the UTC date its window ends on."""
    return (briefing_end(session) or utcnow()).date().isoformat()


def _article_sum(session: Session, *conditions) -> int:
    return session.exec(select(func.coalesce(func.sum(Cluster.article_count), 0)).where(*conditions)).one()


def current_count(session: Session, kind: str, subject: str) -> int:
    """How many articles the subject covers now; compared with basis_count for staleness."""
    if kind == "story":
        cluster = session.get(Cluster, int(subject)) if subject.isdigit() else None
        return cluster.article_count if cluster else 0
    if kind == "thread":
        return _article_sum(session, tag_filter(subject))
    end = briefing_end(session, date.fromisoformat(subject))
    if not end:
        return 0
    return _article_sum(session, Cluster.last_updated >= end - BRIEFING_WINDOW, Cluster.last_updated <= end)


def check_subject(session: Session, kind: str, subject: str) -> str:
    """The subject, normalised; raises WriteupError if it doesn't fit its kind."""
    subject = subject.strip()
    if kind == "story":
        if not subject.isdigit() or not session.get(Cluster, int(subject)):
            raise WriteupError(f"story {subject!r} not found: the subject must be an existing cluster id")
    elif kind == "thread":
        if not session.exec(select(Cluster.id).where(tag_filter(subject)).limit(1)).first():
            raise WriteupError(f"no story is tagged {subject!r}: the subject must be a tag in use")
    elif kind == "briefing":
        try:
            day = date.fromisoformat(subject)
        except ValueError:
            raise WriteupError(f"briefing subject {subject!r} must be a date like 2026-10-12") from None
        if day > utcnow().date():
            raise WriteupError(f"briefing date {subject} is in the future")
        subject = day.isoformat()
    else:
        raise WriteupError(f"unknown kind {kind!r}: use one of {', '.join(KINDS)}")
    return subject


def get(session: Session, kind: str, subject: str) -> Optional[Writeup]:
    return session.exec(select(Writeup).where(Writeup.kind == kind, Writeup.subject == subject.strip())).first()


def save(session: Session, kind: str, subject: str, title: str, body: str, author: str) -> Writeup:
    """Create or replace a write-up. The routine may not replace one written in a session."""
    subject = check_subject(session, kind, subject)
    if not body.strip():
        raise WriteupError("body is empty")
    writeup = get(session, kind, subject)
    if writeup and writeup.author == "session" and author == "routine":
        raise WriteupError(f"{kind} {subject!r} was written in an interactive session; the routine leaves it alone")
    writeup = writeup or Writeup(kind=kind, subject=subject)
    writeup.title, writeup.body, writeup.author = title.strip(), body.strip(), author
    writeup.basis_count = current_count(session, kind, subject)
    writeup.updated_at = utcnow()
    session.add(writeup)
    session.commit()
    session.refresh(writeup)
    return writeup


def delete(session: Session, kind: str, subject: str) -> bool:
    writeup = get(session, kind, subject)
    if not writeup:
        return False
    session.delete(writeup)
    session.commit()
    return True


def public(session: Session, writeup: Writeup) -> dict:
    """The write-up as the API and MCP tools return it, with staleness worked out now."""
    new = max(current_count(session, writeup.kind, writeup.subject) - writeup.basis_count, 0)
    return {
        "kind": writeup.kind, "subject": writeup.subject, "title": writeup.title, "body": writeup.body,
        "author": writeup.author, "updated_at": writeup.updated_at, "stale": new > 0, "new_articles": new,
    }


def writeup_for(session: Session, kind: str, subject: str) -> Optional[dict]:
    writeup = get(session, kind, subject)
    return public(session, writeup) if writeup else None
```

- [ ] **Step 7: Prune write-ups of deleted stories and return counts from `save_clusters`**

In `backend/save_clusters.py`, change the models import:

```python
from models import Article, Cluster, ScrapeRun, Writeup
```

In the "Articles moved out of another story" loop, replace the delete branch:

```python
                if old.article_count == 0:
                    session.delete(old)
                    # Its write-up goes too, so a later story can't inherit it with the id
                    for writeup in session.exec(
                        select(Writeup).where(Writeup.kind == "story", Writeup.subject == str(old_id))
                    ).all():
                        session.delete(writeup)
                    removed += 1
```

Replace the final `print(...)` of `save_clusters()`:

```python
    counts = {"clusters_created": created, "clusters_updated": updated,
              "clusters_removed": removed, "framings_written": framed}
    print(json.dumps(counts))
    return counts
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_writeups.py -q`
Expected: all pass.

Run: `cd backend && ../venv/bin/python -m pytest -q`
Expected: the whole suite passes (the existing `save` fixture still reads the printed JSON).

- [ ] **Step 9: Commit**

```bash
git add backend/models.py backend/database.py backend/writeups.py backend/save_clusters.py backend/tests/conftest.py backend/tests/test_writeups.py
git commit -m "Add Writeup model and write-up rules"
```

---

### Task 2: Write-ups in the API

**Files:**
- Modify: `backend/schemas.py` (add `Writeup`; optional `writeup` on `ClusterDetail` and `Briefing`)
- Modify: `backend/main.py` (`get_cluster`, `briefing`, new `get_thread_writeup`)
- Test: `backend/tests/test_writeup_api.py`

**Interfaces:**
- Consumes: `writeups.writeup_for`, `writeups.briefing_date` (Task 1)
- Produces:
  - `schemas.Writeup` (`kind, subject, title, body, author, updated_at, stale, new_articles`)
  - `GET /api/clusters/{id}` → `writeup: Writeup | null`
  - `GET /api/briefing` → `writeup: Writeup | null` (subject = date of `window_end`)
  - `GET /api/threads/{tag:path}` → `Writeup`, 404 when none
  - `main.list_clusters`, `main.get_cluster`, `main.search`, `main.briefing` stay callable as plain functions with `session=` (Tasks 3 and 5 call them directly)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_writeup_api.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_writeup_api.py -q`
Expected: FAIL — `KeyError: 'writeup'` and 404 on `/api/threads/...` after saving.

- [ ] **Step 3: Add the schema**

In `backend/schemas.py`, before `class Cluster(BaseModel)`:

```python
class Writeup(BaseModel):
    """A longer AI-written piece in Markdown: a story write-up, a day's briefing or a thread summary."""
    kind: Literal["story", "briefing", "thread"]
    subject: str = Field(description="Cluster id, UTC date (YYYY-MM-DD) or tag")
    title: str
    body: str = Field(description="Markdown")
    author: Literal["routine", "session"] = Field(
        description='"routine" = drafted by the scheduled task; "session" = written in an interactive session')
    updated_at: datetime
    stale: bool = Field(description="Coverage has grown since it was written")
    new_articles: int = Field(description="Articles added since it was written")
```

Add to `ClusterDetail`:

```python
class ClusterDetail(Cluster):
    sources: list[ClusterSourceDetail]
    writeup: Optional[Writeup] = None
```

Add to `Briefing`, after `totals`:

```python
    writeup: Optional[Writeup] = Field(default=None, description="The written briefing for window_end's date")
```

- [ ] **Step 4: Wire up `main.py`**

Add `import writeups` after `import schemas`.

Replace the return in `get_cluster`:

```python
    detail = _serialize(cluster, _articles_by_cluster(session, [cluster_id])[cluster_id], with_summaries=True)
    return {**detail, "writeup": writeups.writeup_for(session, "story", str(cluster_id))}
```

In `briefing`, add `"writeup": None` to the early-return dict, and to the final dict:

```python
        "writeup": writeups.writeup_for(session, "briefing", newest.date().isoformat()),
```

After the `/api/tags` endpoint:

```python
@app.get("/api/threads/{tag:path}", response_model=schemas.Writeup)
def get_thread_writeup(tag: str, session: Session = Depends(get_session)):
    """The "where things stand" summary for an ongoing tag. `:path` lets tags contain "/"."""
    writeup = writeups.writeup_for(session, "thread", tag)
    if not writeup:
        raise HTTPException(status_code=404, detail="No summary for this thread yet")
    return writeup
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && ../venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Regenerate the frontend types**

Run: `cd frontend && npm run gen:api`
Expected: `lib/api-schema.ts` gains a `Writeup` schema and `writeup?` on `ClusterDetail` and `Briefing`, plus the `/api/threads/{tag}` path. Run `cd frontend && npx tsc --noEmit` — expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/schemas.py backend/main.py backend/tests/test_writeup_api.py frontend/lib/api-schema.ts
git commit -m "Serve write-ups from the API"
```

---

### Task 3: Write-up candidates

**Files:**
- Create: `backend/writeup_candidates.py`
- Test: `backend/tests/test_writeup_candidates.py`

**Interfaces:**
- Consumes: `writeups.get`, `writeups.current_count`, `writeups.briefing_date`, `writeups.briefing_end` (Task 1); `main.list_clusters` (Task 2); `fetch_articles.tag_counts`
- Produces: `writeup_candidates.candidates(session) -> dict` shaped
  `{"briefing": {"subject": str, "reason": "new" | "refresh"} | None,
    "threads": [{"tag": str, "stories": int, "reason": "new" | "stale"}],
    "stories": [{"cluster_id": int, "headline": str, "source_count": int, "reason": "new" | "stale"}]}`;
  constants `MAX_THREADS = 3`, `MAX_STORIES = 5`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_writeup_candidates.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_writeup_candidates.py -q`
Expected: `ModuleNotFoundError: No module named 'writeup_candidates'`.

- [ ] **Step 3: Write `backend/writeup_candidates.py`**

```python
"""What the scheduled routine should write this run: the day's briefing, the busiest
ongoing threads and the most covered cross-spectrum stories that have no write-up or an
out-of-date one. Session-written write-ups are never offered.

Only subjects are returned; the routine reads each one's material with the MCP read tools
(get_day, get_thread, get_story), which keeps this result small.
"""
from datetime import timedelta
from typing import Optional

from sqlmodel import Session

import main  # the API's Top ranking, so stories are picked in the order readers see them
import writeups
from bias import SIDES
from fetch_articles import tag_counts
from timeutil import utcnow

MAX_THREADS = 3
MAX_STORIES = 5
THREAD_ACTIVE = timedelta(days=2)    # a thread qualifies if one of its stories moved this recently
THREAD_SPAN = timedelta(days=14)     # ...and it has MIN_THREAD_STORIES stories in this span
MIN_THREAD_STORIES = 2
MIN_SIDES = 2


def _reason(session: Session, kind: str, subject: str) -> Optional[str]:
    """"new" if unwritten, "stale" if coverage grew since the routine wrote it, else None."""
    writeup = writeups.get(session, kind, subject)
    if writeup is None:
        return "new"
    if writeup.author == "session":
        return None
    return "stale" if writeups.current_count(session, kind, subject) > writeup.basis_count else None


def candidates(session: Session) -> dict:
    result: dict = {"briefing": None, "threads": [], "stories": []}
    if not writeups.briefing_end(session):
        return result  # nothing fetched and clustered yet

    # The day keeps developing, so the routine rewrites its own briefing every run
    day = writeups.briefing_date(session)
    briefing = writeups.get(session, "briefing", day)
    if not (briefing and briefing.author == "session"):
        result["briefing"] = {"subject": day, "reason": "refresh" if briefing else "new"}

    now = utcnow()
    span = dict(tag_counts(session, now - THREAD_SPAN))
    for tag, _ in tag_counts(session, now - THREAD_ACTIVE):  # most active first
        if len(result["threads"]) == MAX_THREADS:
            break
        if span.get(tag, 0) < MIN_THREAD_STORIES:
            continue
        reason = _reason(session, "thread", tag)
        if reason:
            result["threads"].append({"tag": tag, "stories": span[tag], "reason": reason})

    top = main.list_clusters(sort="top", min_sources=MIN_SIDES, opinion="exclude", limit=200,
                             category=None, tag=None, blindspot=None, source_id=None, offset=0,
                             session=session)
    for story in top:
        if len(result["stories"]) == MAX_STORIES:
            break
        if sum(1 for side in SIDES if story["bias"][side]) < MIN_SIDES:
            continue
        reason = _reason(session, "story", str(story["id"]))
        if reason:
            result["stories"].append({"cluster_id": story["id"], "headline": story["headline"],
                                      "source_count": story["source_count"], "reason": reason})
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_writeup_candidates.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/writeup_candidates.py backend/tests/test_writeup_candidates.py
git commit -m "Pick write-up candidates for the routine"
```

---

### Task 4: MCP server — pipeline tools

**Files:**
- Modify: `backend/requirements.txt` (add `mcp==2.3.0`)
- Create: `backend/mcp_server.py`
- Create: `.mcp.json` (repo root)
- Test: `backend/tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `fetch_articles.fetch_new_articles/pending_articles/recent_clusters/active_tags`, `backup_db.backup`, `framing_candidates.candidates`, `save_clusters.save_clusters` (returns counts, Task 1), `writeup_candidates.candidates` (Task 3)
- Produces (MCP tools on `mcp_server.server`, all returning dicts):
  - `fetch_articles() -> {run_id, status, error, articles_fetched, articles_scraped_new, articles_pending, recent_clusters, active_tags}`
  - `get_pending_articles(offset=0, limit=50) -> {total, offset, articles}`
  - `save_clusters(clusters: list[StoryEntry], run_id=0) -> {clusters_created, clusters_updated, clusters_removed, framings_written, still_pending}`
  - `get_framing_candidates(limit=12) -> {stories}`
  - `save_framing(notes: list[FramingNote]) -> {framings_written}`
  - `get_writeup_candidates() -> {briefing, threads, stories, limits}`
  - module helpers `tool(fn)` (decorator) and `session()` (context manager) for Task 5

- [ ] **Step 1: Install the SDK**

Add to `backend/requirements.txt`:

```
mcp==2.3.0
```

Run: `venv/bin/pip install -r backend/requirements.txt`
Expected: installs `mcp-2.3.0` and its dependencies with no conflicts.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: `ModuleNotFoundError: No module named 'mcp_server'`.

- [ ] **Step 4: Write `backend/mcp_server.py` (pipeline half)**

```python
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
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

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


if __name__ == "__main__":
    init_db()
    server.run()
```

Note: `save_framing` relies on `save_clusters()`'s framing-only path (entries with `framing` and no `article_ids`); `FramingNote.model_dump()` has no `article_ids`, so it takes that path.

- [ ] **Step 5: Register the server**

Create `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "groundednews": {
      "command": "venv/bin/python",
      "args": ["backend/mcp_server.py"]
    }
  }
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: all pass. If the stdio test fails to start the server, run `venv/bin/python backend/mcp_server.py < /dev/null` from the repo root and read the traceback.

Run: `cd backend && ../venv/bin/python -m pytest -q`
Expected: the whole suite passes.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/mcp_server.py backend/tests/test_mcp_server.py .mcp.json
git commit -m "Add MCP server with pipeline tools"
```

---

### Task 5: MCP server — read and write-up tools

**Files:**
- Modify: `backend/mcp_server.py` (add read and write-up tools above `if __name__ == "__main__":`)
- Test: `backend/tests/test_mcp_server.py` (append)

**Interfaces:**
- Consumes: `mcp_server.tool`, `mcp_server.session` (Task 4); `main.list_clusters`, `main.get_cluster`, `main.search`, `main.briefing` (Task 2); `writeups.*` (Task 1)
- Produces (MCP tools):
  - `list_stories(sort="top", category=None, tag=None, opinion=None, limit=20) -> {stories: [brief]}`
  - `get_story(cluster_id) -> story with sources (title, summary, outlet, side, is_opinion), framing, writeup`
  - `search_stories(q, limit=20) -> {total, results: [brief]}`
  - `get_thread(tag, limit=30) -> {tag, stories: [brief, oldest first], writeup}`
  - `get_day() -> {subject, window_start, window_end, totals, stories, blindspots, tags, writeup}`
  - `save_writeup(kind, subject, title, body, author="session") -> public write-up`
  - `get_writeup(kind, subject) -> public write-up`
  - `delete_writeup(kind, subject) -> {deleted}`
  - "brief" = `{id, headline, summary, category, tags, article_count, source_count, last_updated, bias, is_opinion, outlets}`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_mcp_server.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && ../venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: the new tests fail with tool-not-found errors (`ToolFailed: Unknown tool: list_stories` or similar).

- [ ] **Step 3: Add the tools**

In `backend/mcp_server.py`, add `import main` and `from fastapi import HTTPException` to the imports, and above `if __name__ == "__main__":`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && ../venv/bin/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Smoke-test against the real (copied) database**

From the repo root:

```bash
venv/bin/python -c "
import sys, json, anyio; sys.path.insert(0, 'backend')
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
async def go():
    async with Client(StdioServerParameters(command='venv/bin/python', args=['backend/mcp_server.py'])) as c:
        for name in ('get_writeup_candidates', 'get_day'):
            r = await c.call_tool(name, {})
            print(name, 'error' if r.is_error else 'ok', len(r.content[0].text), 'chars')
anyio.run(go)"
```

Expected: both `ok`. `get_day` under ~60,000 characters (roughly 15k tokens); if it is larger, trim `_ARTICLE_FIELDS` summaries in `get_day` stories to 200 characters and re-run.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server.py backend/tests/test_mcp_server.py
git commit -m "Add MCP read and write-up tools"
```

---

### Task 6: Show write-ups on the site

**Files:**
- Modify: `frontend/package.json` / `package-lock.json` (add `react-markdown`)
- Modify: `frontend/lib/api.ts` (type + `getThreadWriteup`)
- Create: `frontend/components/news/writeup-card.tsx`
- Modify: `frontend/app/story/[id]/page.tsx:111` (card above `FramingCard`)
- Modify: `frontend/app/briefing/page.tsx` (card after `</header>`)
- Modify: `frontend/app/page.tsx` (thread card when `?tag=` is set)

**Interfaces:**
- Consumes: `Schemas["Writeup"]`, `ClusterDetail.writeup`, `Briefing.writeup`, `GET /api/threads/{tag}` (Task 2)
- Produces: `export type Writeup`, `api.getThreadWriteup(tag) -> Promise<Writeup | null>`, `<WriteupCard writeup={Writeup | null | undefined} />`

- [ ] **Step 1: Add the dependency**

Run: `cd frontend && npm install react-markdown@10.1.0`
Expected: added to `dependencies`.

- [ ] **Step 2: API client**

In `frontend/lib/api.ts`, after `export type Stats = Schemas["Stats"];`:

```ts
/** A longer AI-written piece (Markdown): story write-up, day's briefing or thread summary. */
export type Writeup = Schemas["Writeup"];
```

In the `api` object, after `getTags`:

```ts
  /** A thread's "where things stand" summary, or null if none has been written. */
  getThreadWriteup: async (tag: string): Promise<Writeup | null> => {
    try {
      return await apiFetch<Writeup>(`/api/threads/${encodeURIComponent(tag)}`);
    } catch (e) {
      if (e instanceof Error && e.message.startsWith("API error 404")) return null;
      throw e;
    }
  },
```

- [ ] **Step 3: The card**

Create `frontend/components/news/writeup-card.tsx`:

```tsx
import Markdown, { type Components } from "react-markdown";
import { Sparkles } from "lucide-react";
import type { Writeup } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";

const HEADINGS: Record<Writeup["kind"], string> = {
  story: "The story so far",
  briefing: "The day in brief",
  thread: "Where things stand",
};

// Tailwind's reset strips list and heading styles, so restore the few Markdown needs.
// Only children/href are passed on: react-markdown also hands each component a `node` prop.
const heading: Components["h3"] = ({ children }) => <h3 className="font-heading font-semibold">{children}</h3>;
const ELEMENTS: Components = {
  p: ({ children }) => <p className="leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5">{children}</ol>,
  h1: heading,
  h2: heading,
  h3: heading,
  a: ({ href, children }) => (
    <a href={href} className="underline underline-offset-2" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

/**
 * A story write-up, day's briefing or thread summary, written by Claude. Renders nothing
 * without one. Raw HTML in the Markdown is dropped; unsafe link URLs are stripped by react-markdown.
 */
export function WriteupCard({ writeup }: { writeup?: Writeup | null }) {
  if (!writeup) return null;
  const by = writeup.author === "session" ? "Written with Claude" : "Written by Claude";
  return (
    <Card>
      <CardContent className="space-y-3">
        <h2 className="font-heading font-semibold">{writeup.title || HEADINGS[writeup.kind]}</h2>
        <div className="space-y-3 text-sm">
          <Markdown skipHtml components={ELEMENTS}>
            {writeup.body}
          </Markdown>
        </div>
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <Sparkles className="mt-px size-3 shrink-0 opacity-70" aria-hidden />
          <span>
            {by} from the outlets&apos; headlines and summaries · updated {timeAgo(writeup.updated_at)}
            {writeup.stale &&
              ` · ${writeup.new_articles} new ${writeup.new_articles === 1 ? "article" : "articles"} since`}
          </span>
        </p>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Place it on the three pages**

`frontend/app/story/[id]/page.tsx`: add `import { WriteupCard } from "@/components/news/writeup-card";` with the other `components/news` imports, and directly above `<FramingCard framing={s.framing} />`:

```tsx
        <WriteupCard writeup={s.writeup} />
```

`frontend/app/briefing/page.tsx`: add the same import, and directly after the closing `</header>`:

```tsx
      <WriteupCard writeup={b.writeup} />
```

`frontend/app/page.tsx`: add the same import; after the `blindspots` `useApi` line:

```tsx
  const thread = useApi(`thread|${tag ?? ""}`, () => (tag ? api.getThreadWriteup(tag) : Promise.resolve(null)));
```

and directly after `{stories.error && <ErrorBanner>{stories.error}</ErrorBanner>}`:

```tsx
          {tag && <WriteupCard writeup={thread.data} />}
```

- [ ] **Step 5: Typecheck and build**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Expected: no errors.

- [ ] **Step 6: Seed write-ups in the copied DB**

From the repo root (this writes only to the worktree's copy of the database). It picks a multi-source story, the current briefing date and the busiest tag, and includes a hostile body (Review Focus 5):

```bash
venv/bin/python -c "
import sys; sys.path.insert(0, 'backend')
from sqlmodel import Session, select
from database import engine, init_db
from models import Cluster
from fetch_articles import active_tags
import writeups
init_db()
with Session(engine) as s:
    story = s.exec(select(Cluster).where(Cluster.source_count >= 3).order_by(Cluster.last_updated.desc())).first()
    tag = active_tags(s)[0]
    writeups.save(s, 'story', str(story.id), 'The story so far', 'Officials **confirmed** the deal.\n\n- Point one\n- Point two\n\n<script>alert(1)</script> [bad link](javascript:alert(1))', 'routine')
    writeups.save(s, 'briefing', writeups.briefing_date(s), 'The day in brief', 'A busy day.\n\n1. First\n2. Second', 'session')
    writeups.save(s, 'thread', tag, 'Where things stand', 'The thread so far.', 'routine')
    print('story', story.id, 'tag', tag)
"
```

- [ ] **Step 7: Verify in the browser**

Add two configurations to `.claude/launch.json` for this check only, and **do not commit them**:

```json
    {
      "name": "wt-backend",
      "runtimeExecutable": "bash",
      "runtimeArgs": ["-c", "cd backend && ../venv/bin/uvicorn main:app --port 8011"],
      "port": 8011
    },
    {
      "name": "wt-frontend",
      "runtimeExecutable": "bash",
      "runtimeArgs": ["-c", "cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8011 npx next dev -p 3011"],
      "port": 3011
    }
```

Start both with `preview_start`. Check, using `read_page` and a screenshot of each:
- `/story/<id from step 6>`: the card appears above "How each side framed it". The bold text and the bullets render. The `<script>` text is gone, and "bad link" is not a `javascript:` link (check with `find` / `read_page` that its `href` is empty or absent). The footer starts "Written by Claude from the outlets' headlines and summaries · updated …".
- `/briefing`: the card appears below the header, with a numbered list and "Written with Claude".
- `/?tag=<tag from step 6>`: the thread card appears above the story list. Another tag with no write-up shows no card.
- A story with no write-up looks exactly as before, and there are no console errors (`read_console_messages`).
- Repeat one page at mobile width (`resize_window` preset `mobile`), then reset with `desktop`.

Then run `git checkout .claude/launch.json`.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/api.ts frontend/components/news/writeup-card.tsx "frontend/app/story/[id]/page.tsx" frontend/app/briefing/page.tsx frontend/app/page.tsx
git commit -m "Show write-ups on story, briefing and thread pages"
```

---

### Task 7: Switch the routine over (after merge, with the user)

This task changes files outside the repo and in the main checkout, so it runs **after the branch is merged to `main`**, and every edit is shown to the user first.

**Files:**
- Modify: `~/.claude/scheduled-tasks/groundednews-scrape/SKILL.md`
- Modify: `/Users/phill/Documents/Projects/groundednews/.claude/settings.local.json` (main checkout; gitignored)

- [ ] **Step 1: Install the new dependency in the shared venv**

```bash
/Users/phill/Documents/Projects/groundednews/venv/bin/pip install -r /Users/phill/Documents/Projects/groundednews/backend/requirements.txt
```

- [ ] **Step 2: Pre-approve the server for the main checkout**

Read `/Users/phill/Documents/Projects/groundednews/.claude/settings.local.json`, and merge in (keeping every existing key):

```json
  "enabledMcpjsonServers": ["groundednews"]
```

Show the user the diff before saving.

- [ ] **Step 3: Rewrite the routine prompt**

Keep the introduction and every clustering, opinion, tag and framing rule word for word. Replace only the mechanics:

- **Step 1**: replace the `fetch_articles.py` command and its "This outputs JSON with…" list with:

  > Call the `fetch_articles` tool from the `groundednews` MCP server. It scrapes every feed, takes the day's database backup on the first run each day, and returns `run_id`, `articles_pending` (articles to cluster: newly scraped plus recent unclustered leftovers), `recent_clusters` and `active_tags`. Then call `get_pending_articles` with `offset` 0, 50, 100, … until you have all `total` articles. Each one has id, source_name, bias_label, title, url, is_opinion and summary.
  >
  > If `articles_pending` is 0, skip to Step 4.

- **Step 3**: replace the file-and-command instructions with:

  > Call `save_clusters` with your list of entries and the `run_id`. It checks the whole batch first, so if it returns an error (an unknown id, or an article in two entries) fix the entries and call it again; nothing was saved. Afterwards `still_pending` should be 0. If it isn't, cluster the leftovers with `get_pending_articles` and save again.

  Keep the example entries, shown as the `clusters` argument.

- **Step 4**: replace the two commands with calls to the `get_framing_candidates` tool and the `save_framing` tool (`notes: [{"cluster_id": …, "framing": {"left": …, "center": …, "right": …}}]`). Keep all the note-writing rules.

- **Insert a new Step 5, "Write-ups"** (the old Step 5 becomes Step 6):

  > Call `get_writeup_candidates`. It lists what to write this run: `briefing` (or null), up to 3 `threads` and up to 5 `stories`. Write-ups from the user's interactive sessions are never listed; leave them alone. For each one, read its material, then call `save_writeup` with `author: "routine"` (always pass this) and a Markdown `body`:
  > - **Briefing**: call `get_day`, then save with `kind: "briefing"` and `subject` set to the `subject` from `get_day`. Use about 200–350 words: the day's most important developments first, what was widely covered across the spectrum, and each side's notable blindspots. Use short paragraphs, or a short list of the top stories. Title it like "Monday, October 12".
  > - **Thread**: call `get_thread` with the tag, then save with `kind: "thread"` and `subject` set to the tag. Use about 150–250 words on where things stand now: the latest development first, then how it got here. Title it after the thread.
  > - **Story**: call `get_story` with the cluster_id, then save with `kind: "story"` and `subject` set to the cluster id as a string. Use about 150–300 words: what happened, the context the summaries give, and what is disputed or reported differently across outlets. Refer to the framing notes rather than repeating them.
  >
  > Follow the same neutrality rules as the framing notes. Ground every claim in the titles and summaries you were given, and say so when outlets disagree. Don't speculate beyond them, and use no loaded language from any side. When `reason` is "refresh" or "stale", update the existing write-up (it's included in the read result) rather than starting over.

- **Old Step 5 (now Step 6)**: add "how many write-ups were written or refreshed, by kind".

- **Fallback**: add after the introduction:

  > If the `groundednews` MCP tools aren't available, use the scripts instead: `venv/bin/python backend/fetch_articles.py > <scratchpad>/fetch.json`, then `venv/bin/python backend/save_clusters.py <scratchpad>/clusters.json <run_id>`, then `venv/bin/python backend/framing_candidates.py`. All of these run from `/Users/phill/Documents/Projects/groundednews`. Skip the write-ups step, and say in the report that the MCP server was unavailable.

Show the user the full diff of `SKILL.md` and save only once they approve.

- [ ] **Step 4: Trial run**

With the user's go-ahead, run the scheduled task once now (`run_scheduled_task` for `groundednews-scrape`). Then check:
- that its report lists the write-ups;
- `/briefing`, one story with a write-up, and one `/?tag=` page on the main site (the frontend on :3000, the backend on :8000);
- that `GET /api/runs` shows the run with status `success`.
