"""
Stories that need a "how each side framed it" note, for the Claude agent to write.
Run after save_clusters.py. Prints JSON: a list of stories covered by at least two sides
(left/center/right) that have no framing yet, or have gained articles since it was written,
most important first. Each lists its articles grouped by side.

Usage: python framing_candidates.py [limit]
Write the notes back with save_clusters.py: [{"cluster_id": N, "framing": {...}}]
"""
import sys
import json
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import timedelta
from sqlmodel import Session, select
from database import init_db, engine
from models import Article, Cluster, Source
from bias import SIDES, bias_breakdown, side_of, top_score

WINDOW = timedelta(hours=72)  # matches the Top feed's window
MIN_SIDES = 2


def candidates(session: Session, limit: int = 12) -> list[dict]:
    newest = session.exec(select(Cluster.last_updated).order_by(Cluster.last_updated.desc())).first()
    if not newest:
        return []
    clusters = session.exec(
        select(Cluster).where(Cluster.last_updated >= newest - WINDOW, Cluster.source_count >= MIN_SIDES)
    ).all()
    rows = session.exec(
        select(Article, Source)
        .join(Source, Article.source_id == Source.id)
        .where(Article.cluster_id.in_([c.id for c in clusters]))
        .order_by(Article.published_at)
    ).all()
    by_cluster: dict[int, list] = {}
    for article, source in rows:
        by_cluster.setdefault(article.cluster_id, []).append((article, source))

    result = []
    for c in clusters:
        items = by_cluster.get(c.id, [])
        sources = [{"source_name": s.name, "bias_label": s.bias_label} for _, s in items]
        bias = bias_breakdown(sources)
        if sum(1 for side in SIDES if bias[side]) < MIN_SIDES:
            continue
        # Fresh framing covers every article already; skip unless coverage has grown since
        newest_article = max(a.scraped_at for a, _ in items)
        if c.framing_updated and c.framing_updated >= newest_article:
            continue
        story = {
            "cluster_id": c.id,
            "headline": c.headline,
            "summary": c.summary,
            "current_framing": json.loads(c.framing or "{}"),
            "articles_by_side": {side: [] for side in SIDES},
            # Used for ranking only; dropped before printing
            "_score": top_score({
                "last_updated": c.last_updated, "source_count": c.source_count,
                "article_count": c.article_count, "bias": bias,
                "is_opinion": all(a.is_opinion for a, _ in items),
            }, newest),
        }
        for a, s in items:
            side = side_of(s.bias_label)
            if side in story["articles_by_side"]:
                story["articles_by_side"][side].append({
                    "source_name": s.name, "title": a.title,
                    "summary": a.summary[:300], "is_opinion": a.is_opinion,
                })
        result.append(story)

    result.sort(key=lambda r: -r["_score"])
    for r in result:
        del r["_score"]
    return result[:limit]


if __name__ == "__main__":
    init_db()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    with Session(engine) as session:
        print(json.dumps(candidates(session, limit), indent=1))
