"""
Core scrape-and-cluster pipeline. Used by both the API scheduler and the CLI.
"""
from datetime import datetime
from sqlmodel import Session, select
from models import Source, Article, Cluster, ScrapeRun
from scraper import scrape_feed
from analyzer import cluster_articles
from config import MAX_ARTICLES_PER_SCRAPE
import traceback


def run_pipeline(session: Session) -> ScrapeRun:
    run = ScrapeRun()
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        sources = session.exec(select(Source).where(Source.enabled == True)).all()
        all_new_articles: list[Article] = []

        for source in sources:
            print(f"  Scraping {source.name}...")
            raw = scrape_feed(source.feed_url, MAX_ARTICLES_PER_SCRAPE)
            run.articles_fetched += len(raw)

            for item in raw:
                existing = session.exec(
                    select(Article).where(Article.url == item["url"])
                ).first()
                if existing:
                    continue

                article = Article(
                    source_id=source.id,
                    title=item["title"],
                    url=item["url"],
                    summary=item["summary"],
                    published_at=item["published_at"],
                    image_url=item["image_url"],
                )
                session.add(article)
                all_new_articles.append(article)
                run.articles_new += 1

            source.last_scraped = datetime.utcnow()
            source.article_count = len(raw)

        session.commit()

        # Re-fetch with IDs now assigned
        for a in all_new_articles:
            session.refresh(a)

        if all_new_articles:
            print(f"  Clustering {len(all_new_articles)} new articles with AI...")
            article_dicts = []
            for a in all_new_articles:
                src = session.get(Source, a.source_id)
                article_dicts.append({
                    "title": a.title,
                    "summary": a.summary,
                    "source": src.name if src else "Unknown",
                    "article_id": a.id,
                })

            clusters = cluster_articles(article_dicts)

            for c_data in clusters:
                indices = c_data.get("indices", [])
                matched_articles = [
                    all_new_articles[i] for i in indices if i < len(all_new_articles)
                ]
                if not matched_articles:
                    continue

                # Find existing cluster to merge into (same headline similarity is hard here,
                # so we create new clusters for new batches and let the UI show recent ones)
                cluster = Cluster(
                    headline=c_data["headline"],
                    summary=c_data.get("summary", ""),
                    category=c_data.get("category", ""),
                    article_count=len(matched_articles),
                    source_count=len({a.source_id for a in matched_articles}),
                    image_url=next((a.image_url for a in matched_articles if a.image_url), ""),
                )
                session.add(cluster)
                session.commit()
                session.refresh(cluster)

                for article in matched_articles:
                    article.cluster_id = cluster.id
                    session.add(article)

                run.clusters_created += 1

            session.commit()

        run.status = "success"
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()

    except Exception as e:
        run.status = "failed"
        run.error = traceback.format_exc()[:1000]
        run.finished_at = datetime.utcnow()
        session.add(run)
        session.commit()
        print(f"Pipeline error: {e}")

    return run
