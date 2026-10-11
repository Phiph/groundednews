"""
Save clusters back to DB after Claude agent analysis.
Usage: python save_clusters.py <clusters.json | -> [run_id]

Pass a path to a JSON file, or "-" to read JSON from stdin. (Reading from a file
avoids shell-quoting problems with apostrophes in headlines.) A raw JSON string is
still accepted for backwards compatibility.

JSON format:
[
  {   # new story
    "headline": "...",
    "summary": "...",
    "category": "...",
    "tags": ["Iran war"],      # optional ongoing-story tags
    "article_ids": [1, 4, 7],
    "opinion_ids": [7]         # optional: articles that are opinion/commentary
  },
  {   # follow-up articles joining an existing story (headline/summary/category/tags optional;
      # tags are added to the story's existing ones)
    "cluster_id": 812,
    "article_ids": [9]
  },
  {   # framing only (no article_ids): how each side covered an existing story
    "cluster_id": 812,
    "framing": {"left": "...", "center": "...", "right": "..."}
  }
]
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from sqlmodel import Session, select
from database import init_db, engine
from models import Article, Cluster, ScrapeRun
from timeutil import utcnow


def _refresh_counts(session: Session, cluster: Cluster):
    articles = session.exec(select(Article).where(Article.cluster_id == cluster.id)).all()
    cluster.article_count = len(articles)
    cluster.source_count = len({a.source_id for a in articles})
    if articles:
        # Story recency follows when its coverage was published, not when it was
        # scraped or (re)clustered; scraped_at stands in when a feed gives no date
        times = [a.published_at or a.scraped_at for a in articles]
        cluster.first_seen = min(times)
        cluster.last_updated = max(times)
    if not cluster.image_url:
        cluster.image_url = next((a.image_url for a in articles if a.image_url), "")


FRAMING_SIDES = ("left", "center", "right")


def _set_framing(cluster: Cluster, framing: dict):
    cleaned = {side: str(framing[side]).strip() for side in FRAMING_SIDES if framing.get(side)}
    cluster.framing = json.dumps(cleaned)
    cluster.framing_updated = utcnow()


def save_clusters(run_id: int, clusters_data: list):
    created = updated = removed = framed = 0
    with Session(engine) as session:
        for c in clusters_data:
            if c.get("framing") and not c.get("article_ids"):
                cluster = session.get(Cluster, c.get("cluster_id"))
                if not cluster:
                    print(f"Warning: cluster {c.get('cluster_id')} not found; framing skipped", file=sys.stderr)
                    continue
                _set_framing(cluster, c["framing"])
                session.add(cluster)
                framed += 1
                continue

            articles = [session.get(Article, aid) for aid in c.get("article_ids", [])]
            articles = [a for a in articles if a]
            if not articles:
                continue

            cluster = session.get(Cluster, c["cluster_id"]) if c.get("cluster_id") else None
            if c.get("cluster_id") and not cluster:
                print(f"Warning: cluster {c['cluster_id']} not found; creating a new one", file=sys.stderr)

            if cluster:
                # Optionally refresh the story's wording as it develops
                for field in ("headline", "summary", "category"):
                    if c.get(field):
                        setattr(cluster, field, c[field])
                if c.get("tags"):
                    existing = json.loads(cluster.tags or "[]")
                    cluster.tags = json.dumps(existing + [t for t in c["tags"] if t not in existing])
                updated += 1
            else:
                cluster = Cluster(
                    headline=c.get("headline") or articles[0].title,
                    summary=c.get("summary", ""),
                    category=c.get("category", ""),
                    tags=json.dumps(c.get("tags", [])),
                )
                created += 1
            if c.get("framing"):
                _set_framing(cluster, c["framing"])
                framed += 1
            session.add(cluster)
            session.flush()

            previous = {a.cluster_id for a in articles if a.cluster_id and a.cluster_id != cluster.id}
            opinion_ids = set(c.get("opinion_ids", []))
            for article in articles:
                article.cluster_id = cluster.id
                # The scraper's URL/title heuristics catch most opinion; the agent catches the rest
                if article.id in opinion_ids:
                    article.is_opinion = True
                session.add(article)
            session.flush()
            _refresh_counts(session, cluster)

            # Articles moved out of another story: update it, or drop it if now empty
            for old_id in previous:
                old = session.get(Cluster, old_id)
                if not old:
                    continue
                _refresh_counts(session, old)
                if old.article_count == 0:
                    session.delete(old)
                    removed += 1
                else:
                    session.add(old)

        run = session.get(ScrapeRun, run_id) if run_id else None
        if run:
            run.clusters_created += created
            run.clusters_updated += updated
            run.status = "success"
            run.finished_at = utcnow()
            session.add(run)

        session.commit()
    print(json.dumps({"clusters_created": created, "clusters_updated": updated,
                      "clusters_removed": removed, "framings_written": framed}))


def _load(arg: str) -> list:
    if arg == "-":
        return json.load(sys.stdin)
    if os.path.isfile(arg):
        with open(arg) as f:
            return json.load(f)
    return json.loads(arg)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    init_db()
    data = _load(sys.argv[1])
    run_id = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    save_clusters(run_id, data)
