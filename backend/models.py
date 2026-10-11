from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class Source(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    feed_url: str = Field(unique=True)
    home_url: str = ""
    bias_label: str = ""  # e.g. "left", "center", "right"
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_scraped: Optional[datetime] = None
    article_count: int = 0                         # items in the feed on the last fetch
    # Feed health
    last_error: str = ""                           # why the last fetch failed, "" if it worked
    failure_streak: int = 0                        # consecutive fetches that failed or returned nothing
    last_success: Optional[datetime] = None
    last_new_article: Optional[datetime] = None    # when the feed last yielded an unseen article

    articles: list["Article"] = Relationship(back_populates="source")


class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="source.id")
    cluster_id: Optional[int] = Field(default=None, foreign_key="cluster.id")
    title: str
    url: str = Field(unique=True)
    summary: str = ""
    published_at: Optional[datetime] = None
    image_url: str = ""
    is_opinion: bool = False      # opinion/editorial/review rather than straight reporting
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    source: Optional[Source] = Relationship(back_populates="articles")
    cluster: Optional["Cluster"] = Relationship(back_populates="articles")


class Cluster(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    headline: str                 # AI-generated unified headline
    summary: str = ""             # AI-generated summary
    category: str = ""            # e.g. "Politics", "Tech", "World"
    image_url: str = ""           # lead image, taken from one of its articles
    tags: str = "[]"              # JSON list of ongoing-story tags, e.g. ["Iran war"]
    article_count: int = 0
    source_count: int = 0
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    articles: list[Article] = Relationship(back_populates="cluster")


class ScrapeRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    articles_fetched: int = 0
    articles_new: int = 0
    clusters_created: int = 0
    clusters_updated: int = 0
    status: str = "running"  # running | success | failed
    error: str = ""
