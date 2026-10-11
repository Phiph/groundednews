"""
Fetch-only script: scrapes RSS feeds and saves new articles to DB.
Prints articles awaiting clustering as JSON for the Claude agent to analyze —
the new ones plus any recent unclustered leftovers (e.g. from a web-app scrape) —
along with recent clusters so follow-up articles can join an existing story.
Usage: python fetch_articles.py
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from sqlmodel import Session, select
from database import init_db, seed_sources, engine
from models import Source, Article, Cluster, ScrapeRun
from scraper import fetch_feeds, fetch_og_images
from backup_db import backup
from timeutil import utcnow

# Unclustered articles older than this are considered stale and left alone;
# clusters updated within it are offered as merge targets
PENDING_WINDOW = timedelta(hours=48)
# Older stories offered as merge targets via their tags (see recent_clusters)
TAG_STORY_WINDOW = timedelta(days=14)
# Feeds keep old items around (and new sources bring a backlog); skip anything older than this
MAX_ARTICLE_AGE = timedelta(days=3)


def fetch_new_articles(session: Session) -> ScrapeRun:
    """Scrape all enabled feeds and store new articles without clustering them."""
    seed_sources(session)

    run = ScrapeRun()
    session.add(run)
    session.commit()
    session.refresh(run)

    sources = session.exec(select(Source).where(Source.enabled == True)).all()
    added: list[Article] = []
    now = utcnow()
    too_old = now - MAX_ARTICLE_AGE
    failures = []

    # Network in parallel; database writes stay on this thread
    results = fetch_feeds([s.feed_url for s in sources], max_articles=30)
    all_urls = [item["url"] for raw, _ in results for item in raw]
    seen = set(session.exec(select(Article.url).where(Article.url.in_(all_urls))).all())

    for source, (raw, error) in zip(sources, results):
        run.articles_fetched += len(raw)
        new_count = 0

        for item in raw:
            if item["url"] in seen or (item["published_at"] and item["published_at"] < too_old):
                continue
            seen.add(item["url"])

            article = Article(
                source_id=source.id,
                title=item["title"],
                url=item["url"],
                summary=item["summary"],
                published_at=item["published_at"],
                image_url=item["image_url"],
                is_opinion=item["is_opinion"],
            )
            session.add(article)
            added.append(article)
            new_count += 1

        run.articles_new += new_count
        source.last_scraped = now
        source.article_count = len(raw)
        # An empty feed counts as a failure too: it usually means the feed moved or broke
        source.last_error = error or ("" if raw else "Feed returned no items")
        if source.last_error:
            source.failure_streak += 1
            failures.append(f"{source.name}: {source.last_error}")
        else:
            source.failure_streak = 0
            source.last_success = now
        if new_count:
            source.last_new_article = now
        session.add(source)

    # Some feeds (e.g. CBS, Al Jazeera) carry no images; fall back to the page's og:image
    missing = [a for a in added if not a.image_url]
    for article, image in zip(missing, fetch_og_images([a.url for a in missing])):
        article.image_url = image

    run.error = "; ".join(failures)
    run.status = "failed" if sources and len(failures) == len(sources) else "fetched"
    run.finished_at = utcnow()
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def pending_articles(session: Session) -> list[dict]:
    """Recent articles that haven't been assigned to a cluster yet."""
    cutoff = utcnow() - PENDING_WINDOW
    rows = session.exec(
        select(Article, Source)
        .join(Source, Article.source_id == Source.id)
        .where(Article.cluster_id == None, Article.scraped_at >= cutoff)
        .order_by(Article.id)
    ).all()
    return [
        {
            "id": article.id,
            "source_name": source.name,
            "bias_label": source.bias_label,
            "title": article.title,
            "url": article.url,
            "is_opinion": article.is_opinion,
            "summary": article.summary[:300],
        }
        for article, source in rows
    ]


def recent_clusters(session: Session) -> list[dict]:
    """Stories the agent can merge follow-ups into: everything updated recently, plus the
    latest story for each active tag even if older, so long-running stories (a trial, a war)
    keep growing instead of restarting as a new story after a quiet couple of days."""
    cutoff = utcnow() - PENDING_WINDOW
    recent_ids = select(Article.cluster_id).where(Article.scraped_at >= cutoff)
    clusters = list(session.exec(
        select(Cluster).where(Cluster.id.in_(recent_ids)).order_by(Cluster.id)
    ).all())

    seen = {c.id for c in clusters}
    tagged = session.exec(
        select(Cluster)
        .where(Cluster.last_updated >= utcnow() - TAG_STORY_WINDOW, Cluster.tags != "[]")
        .order_by(Cluster.last_updated.desc())
    ).all()
    covered_tags = {t for c in clusters for t in json.loads(c.tags or "[]")}
    for c in tagged:  # newest first, so the first story seen for a tag is its latest
        new_tags = [t for t in json.loads(c.tags or "[]") if t not in covered_tags]
        if new_tags and c.id not in seen:
            clusters.append(c)
            seen.add(c.id)
        covered_tags.update(new_tags)

    return [
        {"cluster_id": c.id, "headline": c.headline, "category": c.category,
         "tags": json.loads(c.tags or "[]"), "last_updated": c.last_updated.strftime("%Y-%m-%d")}
        for c in clusters
    ]


def active_tags(session: Session, days: int = 14) -> list[str]:
    """Tags already in use recently, so the agent reuses names instead of inventing variants."""
    cutoff = utcnow() - timedelta(days=days)
    counts: dict[str, int] = {}
    for tags in session.exec(select(Cluster.tags).where(Cluster.last_updated >= cutoff)).all():
        for t in json.loads(tags or "[]"):
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts, key=lambda t: -counts[t])


def fetch_and_store():
    init_db()
    # The scheduled task runs this every few hours; the first run each day takes the backup
    backup()
    with Session(engine) as session:
        run = fetch_new_articles(session)
        pending = pending_articles(session)

        print(json.dumps({
            "run_id": run.id,
            "articles_fetched": run.articles_fetched,
            "articles_scraped_new": run.articles_new,
            # Count of articles to cluster (new + recent unclustered leftovers)
            "articles_new": len(pending),
            "new_articles": pending,
            "recent_clusters": recent_clusters(session),
            "active_tags": active_tags(session),
        }))


if __name__ == "__main__":
    fetch_and_store()
