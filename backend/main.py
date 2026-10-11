from contextlib import asynccontextmanager
import json
import re
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from collections import Counter
from sqlalchemy import Integer, func, text
from sqlmodel import Session, select
from pydantic import BaseModel

from database import init_db, seed_sources, get_session
from models import Source, Article, Cluster, ScrapeRun
from fetch_articles import fetch_new_articles


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(__import__("database").engine) as s:
        seed_sources(s)
    yield


app = FastAPI(title="GroundedNews API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Clusters ────────────────────────────────────────────────────────────────

# Ground News-style buckets: leaning outlets count toward their side
BIAS_BUCKETS = {"left": "left", "center-left": "left", "center": "center",
                "center-right": "right", "right": "right"}
BLINDSPOT_MIN_SOURCES = 3
BLINDSPOT_SHARE = 0.7


def _bias(sources: list[dict]) -> dict:
    """Distinct-outlet counts per side, plus which side (if any) is ignoring the story."""
    outlets: dict[str, str] = {}
    for s in sources:
        outlets[s["source_name"]] = BIAS_BUCKETS.get(s["bias_label"], "unknown")
    counts = {"left": 0, "center": 0, "right": 0, "unknown": 0}
    for side in outlets.values():
        counts[side] += 1
    total = len(outlets)
    blindspot = None
    if total >= BLINDSPOT_MIN_SOURCES:
        # "Blindspot for the right" = covered almost entirely by the left, and vice versa
        if counts["right"] == 0 and counts["left"] / total >= BLINDSPOT_SHARE:
            blindspot = "right"
        elif counts["left"] == 0 and counts["right"] / total >= BLINDSPOT_SHARE:
            blindspot = "left"
    return {**counts, "blindspot": blindspot}


def _serialize(cluster: Cluster, rows: list[tuple[Article, Source]], with_summaries: bool = False) -> dict:
    sources = []
    for a, src in rows:
        item = {
            "source_id": src.id,
            "source_name": src.name,
            "bias_label": src.bias_label,
            "title": a.title,
            "url": a.url,
            # Feeds without dates fall back to when we found the article, as story recency does
            "published_at": a.published_at or a.scraped_at,
            "image_url": a.image_url,
            "is_opinion": a.is_opinion,
        }
        if with_summaries:
            item["summary"] = a.summary
        sources.append(item)
    return {
        "id": cluster.id,
        "headline": cluster.headline,
        "summary": cluster.summary,
        "category": cluster.category,
        "tags": json.loads(cluster.tags or "[]"),
        "image_url": cluster.image_url or next((a.image_url for a, _ in rows if a.image_url), ""),
        "article_count": cluster.article_count,
        "source_count": cluster.source_count,
        "first_seen": cluster.first_seen,
        "last_updated": cluster.last_updated,
        "bias": _bias(sources),
        # Only opinion pieces so far, no straight reporting
        "is_opinion": bool(rows) and all(a.is_opinion for a, _ in rows),
        "sources": sources,
    }


def _articles_by_cluster(session: Session, cluster_ids: list[int]) -> dict[int, list]:
    grouped: dict[int, list] = {cid: [] for cid in cluster_ids}
    if not cluster_ids:
        return grouped
    rows = session.exec(
        select(Article, Source)
        .join(Source, Article.source_id == Source.id)
        .where(Article.cluster_id.in_(cluster_ids))
        .order_by(Article.published_at.desc())
    ).all()
    for a, src in rows:
        grouped[a.cluster_id].append((a, src))
    return grouped


TOP_WINDOW = timedelta(hours=72)


def _story_ids(*conditions):
    """Subquery of story ids with an article matching `conditions`. Unclustered articles are
    excluded: a NULL in the list would make NOT IN match nothing."""
    return select(Article.cluster_id).where(Article.cluster_id.is_not(None), *conditions)


SPECTRUM_BONUS = 0.25    # per extra side (left/center/right) covering the story
OPINION_ONLY_WEIGHT = 0.25  # stories with no straight reporting yet sink below news


def _top_score(story: dict, newest: datetime) -> float:
    """Wider coverage ranks higher, especially coverage from across the spectrum;
    older stories decay over roughly a day."""
    hours_old = max((newest - story["last_updated"]).total_seconds() / 3600, 0)
    coverage = story["source_count"] ** 1.3 + 0.2 * story["article_count"]
    sides = sum(1 for side in ("left", "center", "right") if story["bias"][side])
    score = coverage * (1 + SPECTRUM_BONUS * max(sides - 1, 0)) / (1 + hours_old / 18)
    return score * OPINION_ONLY_WEIGHT if story["is_opinion"] else score


@app.get("/api/clusters")
def list_clusters(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    blindspot: Optional[str] = None,  # "left" | "right" | "any"
    sort: str = "latest",  # "latest" | "top"
    min_sources: int = 1,
    opinion: Optional[str] = None,  # "exclude" (news only) | "only"
    source_id: Optional[int] = None,  # stories this outlet covered
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    q = select(Cluster).where(Cluster.source_count >= min_sources)
    if category:
        q = q.where(Cluster.category == category)
    if opinion in ("exclude", "only"):
        # A story counts as opinion while it has no straight reporting (matches is_opinion)
        has_reporting = Cluster.id.in_(_story_ids(Article.is_opinion == False))
        q = q.where(has_reporting if opinion == "exclude" else ~has_reporting)
    if source_id:
        q = q.where(Cluster.id.in_(_story_ids(Article.source_id == source_id)))
    if tag:
        q = q.where(Cluster.tags.contains(json.dumps(tag)))
    q = q.order_by(Cluster.last_updated.desc())
    if blindspot:
        q = q.where(Cluster.source_count >= BLINDSPOT_MIN_SOURCES)

    if sort != "top" and not blindspot:
        clusters = session.exec(q.offset(offset).limit(limit)).all()
        grouped = _articles_by_cluster(session, [c.id for c in clusters])
        return [_serialize(c, grouped[c.id]) for c in clusters]

    # Ranking and blindspot both depend on outlet bias, so serialize every candidate first
    newest = None
    if sort == "top":
        # The window is relative to the newest story so the feed still works
        # if scraping has paused for a while
        newest = session.exec(select(Cluster.last_updated).order_by(Cluster.last_updated.desc())).first()
        if newest:
            q = q.where(Cluster.last_updated >= newest - TOP_WINDOW)
    clusters = session.exec(q).all()
    grouped = _articles_by_cluster(session, [c.id for c in clusters])
    result = [_serialize(c, grouped[c.id]) for c in clusters]
    if blindspot:
        result = [r for r in result
                  if r["bias"]["blindspot"] and (blindspot == "any" or r["bias"]["blindspot"] == blindspot)]
    if newest:
        result.sort(key=lambda r: -_top_score(r, newest))
    return result[offset:offset + limit]


@app.get("/api/clusters/{cluster_id}")
def get_cluster(cluster_id: int, session: Session = Depends(get_session)):
    cluster = session.get(Cluster, cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return _serialize(cluster, _articles_by_cluster(session, [cluster_id])[cluster_id], with_summaries=True)


# Column weights for story_fts (headline, summary, tags, outlet titles)
SEARCH_WEIGHTS = "10.0, 3.0, 5.0, 2.0"


@app.get("/api/search")
def search(
    q: str,
    sort: str = "relevance",  # "relevance" | "latest"
    limit: int = 30,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    """Full-text search over stories. Every word must match; each is treated as a prefix,
    so results appear while typing and "elect" finds "election"."""
    words = re.findall(r"\w+", q)
    if not words:
        return {"total": 0, "results": []}
    # Quote each word so FTS5 operators (AND, NEAR, -) in the query are taken literally
    match = " ".join(f'"{w}"*' for w in words)
    hits = session.execute(
        text(f"SELECT rowid, bm25(story_fts, {SEARCH_WEIGHTS}) FROM story_fts WHERE story_fts MATCH :m"),
        {"m": match},
    ).all()
    relevance = {cid: -rank for cid, rank in hits}  # bm25 is negative; higher = better match
    clusters = session.exec(select(Cluster).where(Cluster.id.in_(list(relevance)))).all()

    if sort == "latest":
        clusters.sort(key=lambda c: c.last_updated, reverse=True)
    else:
        # Best match first, favouring widely covered stories (sqrt, so 9 outlets weigh 3x one)
        # and, gently, recent ones (a week-old story needs a ~2x better match)
        now = datetime.utcnow()
        clusters.sort(
            key=lambda c: relevance[c.id] * c.source_count ** 0.5
            / (1 + (now - c.last_updated).total_seconds() / 86400 / 7),
            reverse=True,
        )
    page = clusters[offset:offset + limit]
    grouped = _articles_by_cluster(session, [c.id for c in page])
    return {"total": len(clusters), "results": [_serialize(c, grouped[c.id]) for c in page]}


@app.get("/api/tags")
def list_tags(days: int = 7, limit: int = 20, session: Session = Depends(get_session)):
    """Most active ongoing-story tags, by number of stories updated in the last `days`."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    counts: dict[str, int] = {}
    for tags in session.exec(select(Cluster.tags).where(Cluster.last_updated >= cutoff)).all():
        for t in json.loads(tags or "[]"):
            counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{"tag": t, "count": n} for t, n in ranked]


# ── Sources ──────────────────────────────────────────────────────────────────

def _article_time():
    """When an article was published, or found if its feed gave no date."""
    return func.coalesce(Article.published_at, Article.scraped_at)


@app.get("/api/sources/summary")
def sources_summary(days: int = 7, session: Session = Depends(get_session)):
    """Per-outlet activity over the last `days`, for the outlets index."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = session.exec(
        select(
            Article.source_id,
            func.count(Article.id),
            # Without type_, SQLAlchemy reads the sum back as a Boolean (any count -> True -> 1)
            func.sum(Article.is_opinion, type_=Integer),
            func.count(func.distinct(Article.cluster_id)),
            func.max(_article_time()),
        )
        .where(_article_time() >= cutoff)
        .group_by(Article.source_id)
    ).all()
    stats = {sid: (n, int(op or 0), stories, latest) for sid, n, op, stories, latest in rows}
    result = []
    for src in session.exec(select(Source).order_by(Source.name)).all():
        n, op, stories, latest = stats.get(src.id, (0, 0, 0, None))
        result.append({
            "id": src.id, "name": src.name, "home_url": src.home_url, "bias_label": src.bias_label,
            "enabled": src.enabled, "articles": n, "opinion": op, "stories": stories, "latest_article": latest,
        })
    return {"days": days, "sources": result}


MISSED_MIN_SOURCES = 4  # a story this widely covered is notable when an outlet skips it


@app.get("/api/sources/{source_id}")
def source_profile(source_id: int, days: int = 30, session: Session = Depends(get_session)):
    """How an outlet covers the news: volume, opinion share, topics, how often it breaks
    stories first, and the widely covered stories it skipped."""
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    cutoff = datetime.utcnow() - timedelta(days=days)
    articles = session.exec(
        select(Article).where(Article.source_id == source_id, _article_time() >= cutoff)
    ).all()
    cluster_ids = list({a.cluster_id for a in articles if a.cluster_id})
    clusters = session.exec(select(Cluster).where(Cluster.id.in_(cluster_ids))).all()

    # First to report: earliest article among stories that several outlets covered
    shared = [c for c in clusters if c.source_count >= 2]
    grouped = _articles_by_cluster(session, [c.id for c in shared])
    first = sum(
        1 for c in shared
        if min(grouped[c.id], key=lambda row: row[0].published_at or row[0].scraped_at)[1].id == source_id
    )

    # Widely covered recent stories without this outlet, most important first
    newest = session.exec(select(Cluster.last_updated).order_by(Cluster.last_updated.desc())).first()
    missed = []
    if newest:
        candidates = session.exec(
            select(Cluster).where(
                Cluster.last_updated >= newest - TOP_WINDOW,
                Cluster.source_count >= MISSED_MIN_SOURCES,
                ~Cluster.id.in_(_story_ids(Article.source_id == source_id)),
            )
        ).all()
        rows = _articles_by_cluster(session, [c.id for c in candidates])
        missed = sorted((_serialize(c, rows[c.id]) for c in candidates), key=lambda r: -_top_score(r, newest))[:5]

    categories = Counter(c.category for c in clusters if c.category)
    return {
        "source": source,
        "days": days,
        "articles": len(articles),
        "opinion": sum(a.is_opinion for a in articles),
        "stories": len(clusters),
        "shared_stories": len(shared),
        "exclusive_stories": len(clusters) - len(shared),
        "first_reports": first,
        "categories": [{"category": k, "count": v} for k, v in categories.most_common()],
        "missed": missed,
    }


@app.get("/api/sources")
def list_sources(session: Session = Depends(get_session)):
    return session.exec(select(Source).order_by(Source.name)).all()


class SourceCreate(BaseModel):
    name: str
    feed_url: str
    home_url: str = ""
    bias_label: str = ""


@app.post("/api/sources", status_code=201)
def create_source(data: SourceCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(Source).where(Source.feed_url == data.feed_url)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Feed URL already exists")
    source = Source(**data.model_dump())
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@app.patch("/api/sources/{source_id}")
def update_source(source_id: int, data: dict, session: Session = Depends(get_session)):
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    for k, v in data.items():
        if hasattr(source, k):
            setattr(source, k, v)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(source_id: int, session: Session = Depends(get_session)):
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    session.delete(source)
    session.commit()


# ── Scrape runs ───────────────────────────────────────────────────────────────

@app.get("/api/runs")
def list_runs(limit: int = 20, session: Session = Depends(get_session)):
    return session.exec(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit)
    ).all()


_scrape_running = False


@app.post("/api/scrape")
def trigger_scrape(background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    global _scrape_running
    if _scrape_running:
        raise HTTPException(status_code=409, detail="Scrape already in progress")

    def _run():
        global _scrape_running
        _scrape_running = True
        from database import engine
        try:
            # Fetch only: clustering is done by the Claude session (scheduled task),
            # which picks up recent unclustered articles on its next run.
            with Session(engine) as s:
                fetch_new_articles(s)
        finally:
            _scrape_running = False

    background_tasks.add_task(_run)
    return {"status": "started"}


@app.get("/api/scrape/status")
def scrape_status():
    return {"running": _scrape_running}


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    from sqlmodel import func
    total_clusters = session.exec(select(func.count(Cluster.id))).one()
    total_articles = session.exec(select(func.count(Article.id))).one()
    total_sources = session.exec(select(func.count(Source.id)).where(Source.enabled == True)).one()
    last_run = session.exec(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(1)
    ).first()
    return {
        "total_clusters": total_clusters,
        "total_articles": total_articles,
        "active_sources": total_sources,
        "last_run": last_run,
    }
