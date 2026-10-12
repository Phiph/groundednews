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
