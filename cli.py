#!/usr/bin/env python3
"""
GroundedNews CLI
Usage:
  python cli.py scrape          - Fetch new articles (clustering is done by the scheduled Claude task)
  python cli.py status          - Show latest stats and run history
  python cli.py sources         - List all configured sources
  python cli.py sources add     - Add a new RSS source interactively
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from datetime import datetime
from sqlmodel import Session, select


def get_session():
    from database import engine, init_db, seed_sources
    init_db()
    session = Session(engine)
    seed_sources(session)
    return session


def cmd_scrape():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching feeds...")
    session = get_session()
    from fetch_articles import fetch_new_articles
    run = fetch_new_articles(session)
    session.close()

    print()
    print("=" * 50)
    print(f"  Status:           {run.status.upper()}")
    print(f"  Articles fetched: {run.articles_fetched}")
    print(f"  Articles new:     {run.articles_new}")
    if run.finished_at and run.started_at:
        elapsed = (run.finished_at - run.started_at).total_seconds()
        print(f"  Duration:         {elapsed:.1f}s")
    if run.error:
        print(f"\n  Error: {run.error}")
    print("=" * 50)


def cmd_status():
    from models import ScrapeRun, Cluster, Article, Source
    from sqlmodel import func

    session = get_session()
    total_clusters = session.exec(select(func.count(Cluster.id))).one()
    total_articles = session.exec(select(func.count(Article.id))).one()
    total_sources = session.exec(select(func.count(Source.id)).where(Source.enabled == True)).one()
    runs = session.exec(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(5)).all()
    session.close()

    print()
    print("GroundedNews Status")
    print("=" * 50)
    print(f"  Active sources:  {total_sources}")
    print(f"  Total articles:  {total_articles}")
    print(f"  Total clusters:  {total_clusters}")
    print()
    print("Recent scrape runs:")
    for r in runs:
        ts = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "?"
        print(f"  {ts}  {r.status:8s}  +{r.articles_new} articles  {r.clusters_created} clusters")
    print()


def cmd_sources(args):
    from models import Source
    session = get_session()

    if args and args[0] == "add":
        print("Add a new RSS source")
        name = input("  Name: ").strip()
        feed_url = input("  RSS Feed URL: ").strip()
        home_url = input("  Home URL (optional): ").strip()
        bias_label = input("  Bias label (left/center-left/center/center-right/right): ").strip()
        source = Source(name=name, feed_url=feed_url, home_url=home_url, bias_label=bias_label)
        session.add(source)
        session.commit()
        print(f"  Added: {name}")
    else:
        sources = session.exec(select(Source).order_by(Source.name)).all()
        print()
        print(f"{'Name':<25} {'Bias':<15} {'Enabled':<8} {'Last scraped'}")
        print("-" * 70)
        for s in sources:
            last = s.last_scraped.strftime("%Y-%m-%d %H:%M") if s.last_scraped else "never"
            print(f"  {s.name:<23} {s.bias_label:<15} {'yes' if s.enabled else 'no':<8} {last}")
        print()

    session.close()


def main():
    args = sys.argv[1:]
    if not args or args[0] == "help":
        print(__doc__)
        return

    cmd = args[0]
    if cmd == "scrape":
        cmd_scrape()
    elif cmd == "status":
        cmd_status()
    elif cmd == "sources":
        cmd_sources(args[1:])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
