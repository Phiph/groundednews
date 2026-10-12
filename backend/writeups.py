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
