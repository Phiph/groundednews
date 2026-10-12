from sqlmodel import create_engine, Session, SQLModel
from config import DATABASE_URL

# The API and the MCP server can write at the same moment; wait for the lock instead of failing
engine = create_engine(
    DATABASE_URL, echo=False,
    connect_args={"timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)


# Columns added after the initial schema; create_all() won't add them to existing tables
_ADDED_COLUMNS = {
    "article": {"image_url": "VARCHAR NOT NULL DEFAULT ''", "is_opinion": "BOOLEAN NOT NULL DEFAULT 0"},
    "source": {
        "last_error": "VARCHAR NOT NULL DEFAULT ''",
        "failure_streak": "INTEGER NOT NULL DEFAULT 0",
        "last_success": "DATETIME",
        "last_new_article": "DATETIME",
        "etag": "VARCHAR NOT NULL DEFAULT ''",
        "last_modified": "VARCHAR NOT NULL DEFAULT ''",
    },
    "cluster": {
        "image_url": "VARCHAR NOT NULL DEFAULT ''",
        "tags": "VARCHAR NOT NULL DEFAULT '[]'",
        "framing": "VARCHAR NOT NULL DEFAULT '{}'",
        "framing_updated": "DATETIME",
    },
}


def init_db():
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        # create_all() only indexes tables it creates, so add these to existing databases too
        for table in SQLModel.metadata.sorted_tables:
            for index in table.indexes:
                index.create(conn, checkfirst=True)
        _init_search(conn)


# Full-text search over stories: one row per cluster (rowid = cluster.id) holding its
# headline, summary, tags and every outlet's article title, since outlets word stories
# differently. Triggers keep it in sync whichever script writes to the database.
_STORY_ROW = """
    SELECT c.id, c.headline, c.summary, c.tags,
           (SELECT group_concat(a.title, ' ') FROM article a WHERE a.cluster_id = c.id)
    FROM cluster c WHERE c.id IN ({ids})
"""
_SEARCH_SCHEMA = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS story_fts USING fts5(
        headline, summary, tags, titles, tokenize = 'porter unicode61 remove_diacritics 2')""",
    f"""CREATE TRIGGER IF NOT EXISTS story_fts_cluster_insert AFTER INSERT ON cluster BEGIN
        INSERT INTO story_fts(rowid, headline, summary, tags, titles) {_STORY_ROW.format(ids="new.id")};
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS story_fts_cluster_update AFTER UPDATE OF headline, summary, tags ON cluster BEGIN
        DELETE FROM story_fts WHERE rowid = old.id;
        INSERT INTO story_fts(rowid, headline, summary, tags, titles) {_STORY_ROW.format(ids="new.id")};
    END""",
    """CREATE TRIGGER IF NOT EXISTS story_fts_cluster_delete AFTER DELETE ON cluster BEGIN
        DELETE FROM story_fts WHERE rowid = old.id;
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS story_fts_article_insert AFTER INSERT ON article WHEN new.cluster_id IS NOT NULL BEGIN
        DELETE FROM story_fts WHERE rowid = new.cluster_id;
        INSERT INTO story_fts(rowid, headline, summary, tags, titles) {_STORY_ROW.format(ids="new.cluster_id")};
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS story_fts_article_update AFTER UPDATE OF cluster_id, title ON article BEGIN
        DELETE FROM story_fts WHERE rowid IN (old.cluster_id, new.cluster_id);
        INSERT INTO story_fts(rowid, headline, summary, tags, titles) {_STORY_ROW.format(ids="old.cluster_id, new.cluster_id")};
    END""",
    f"""CREATE TRIGGER IF NOT EXISTS story_fts_article_delete AFTER DELETE ON article WHEN old.cluster_id IS NOT NULL BEGIN
        DELETE FROM story_fts WHERE rowid = old.cluster_id;
        INSERT INTO story_fts(rowid, headline, summary, tags, titles) {_STORY_ROW.format(ids="old.cluster_id")};
    END""",
]


def _init_search(conn):
    for statement in _SEARCH_SCHEMA:
        conn.exec_driver_sql(statement)
    # Build (or repair) the index if it doesn't cover every story
    indexed = conn.exec_driver_sql("SELECT count(*) FROM story_fts").scalar()
    stories = conn.exec_driver_sql("SELECT count(*) FROM cluster").scalar()
    if indexed != stories:
        conn.exec_driver_sql("DELETE FROM story_fts")
        conn.exec_driver_sql(
            "INSERT INTO story_fts(rowid, headline, summary, tags, titles) "
            + _STORY_ROW.format(ids="SELECT id FROM cluster")
        )


def get_session():
    with Session(engine) as session:
        yield session


DEFAULT_SOURCES = [
    {"name": "BBC News", "feed_url": "http://feeds.bbci.co.uk/news/rss.xml", "home_url": "https://bbc.com", "bias_label": "center-left"},
    {"name": "ABC News", "feed_url": "https://feeds.abcnews.com/abcnews/topstories", "home_url": "https://abcnews.go.com", "bias_label": "center-left"},
    {"name": "CBS News", "feed_url": "https://www.cbsnews.com/latest/rss/main", "home_url": "https://cbsnews.com", "bias_label": "center-left"},
    {"name": "The Guardian", "feed_url": "https://www.theguardian.com/world/rss", "home_url": "https://theguardian.com", "bias_label": "left"},
    {"name": "Fox News", "feed_url": "https://moxie.foxnews.com/google-publisher/latest.xml", "home_url": "https://foxnews.com", "bias_label": "right"},
    {"name": "NPR", "feed_url": "https://feeds.npr.org/1001/rss.xml", "home_url": "https://npr.org", "bias_label": "center-left"},
    {"name": "Al Jazeera", "feed_url": "https://www.aljazeera.com/xml/rss/all.xml", "home_url": "https://aljazeera.com", "bias_label": "center"},
    {"name": "The Hill", "feed_url": "https://thehill.com/news/feed/", "home_url": "https://thehill.com", "bias_label": "center"},
    {"name": "New York Post", "feed_url": "https://nypost.com/feed/", "home_url": "https://nypost.com", "bias_label": "center-right"},
    {"name": "Washington Examiner", "feed_url": "https://www.washingtonexaminer.com/feed/", "home_url": "https://washingtonexaminer.com", "bias_label": "center-right"},
    {"name": "Washington Times", "feed_url": "https://www.washingtontimes.com/rss/headlines/news/", "home_url": "https://washingtontimes.com", "bias_label": "center-right"},
    {"name": "National Review", "feed_url": "https://www.nationalreview.com/feed/", "home_url": "https://nationalreview.com", "bias_label": "right"},
    {"name": "Daily Caller", "feed_url": "https://dailycaller.com/feed/", "home_url": "https://dailycaller.com", "bias_label": "right"},
    {"name": "UPI", "feed_url": "https://rss.upi.com/news/top_news.rss", "home_url": "https://upi.com", "bias_label": "center"},
    {"name": "Newsweek", "feed_url": "https://www.newsweek.com/rss", "home_url": "https://newsweek.com", "bias_label": "center"},
    {"name": "NewsNation", "feed_url": "https://www.newsnationnow.com/feed/", "home_url": "https://newsnationnow.com", "bias_label": "center"},
    {"name": "Christian Science Monitor", "feed_url": "https://rss.csmonitor.com/feeds/all", "home_url": "https://csmonitor.com", "bias_label": "center"},
]


def seed_sources(session: Session):
    from models import Source
    from sqlmodel import select
    existing = session.exec(select(Source)).all()
    if existing:
        return
    for s in DEFAULT_SOURCES:
        session.add(Source(**s))
    session.commit()
