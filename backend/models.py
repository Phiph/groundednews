from typing import Optional
from pydantic import ConfigDict, NaiveDatetime
from sqlmodel import Field, SQLModel, Relationship
from timeutil import utcnow


class SourceBase(SQLModel):
    """Source fields the API exposes. Field descriptions become doc comments in the
    generated frontend types (frontend/lib/api-schema.ts)."""
    name: str
    feed_url: str = Field(unique=True)
    home_url: str = ""
    bias_label: str = Field(default="", description='e.g. "left", "center-left", "center"')
    enabled: bool = True
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    last_scraped: Optional[NaiveDatetime] = None
    article_count: int = Field(default=0, description="Items in the feed on the last fetch")
    # Feed health
    last_error: str = Field(default="", description='Why the last fetch failed; "" if it worked')
    failure_streak: int = Field(default=0, description="Consecutive fetches that failed or returned nothing")
    last_success: Optional[NaiveDatetime] = None
    last_new_article: Optional[NaiveDatetime] = Field(
        default=None, description="When the feed last yielded an unseen article")


class Source(SourceBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # HTTP validators from the last good fetch, sent back so unchanged feeds answer 304
    etag: str = ""
    last_modified: str = ""

    articles: list["Article"] = Relationship(back_populates="source")


class SourcePublic(SourceBase):
    # Responses always include defaulted fields, so the generated types mark them required
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: int


class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    cluster_id: Optional[int] = Field(default=None, foreign_key="cluster.id", index=True)
    title: str
    url: str = Field(unique=True)
    summary: str = ""
    published_at: Optional[NaiveDatetime] = None
    image_url: str = ""
    is_opinion: bool = False      # opinion/editorial/review rather than straight reporting
    scraped_at: NaiveDatetime = Field(default_factory=utcnow, index=True)

    source: Optional[Source] = Relationship(back_populates="articles")
    cluster: Optional["Cluster"] = Relationship(back_populates="articles")


class Cluster(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    headline: str                 # AI-generated unified headline
    summary: str = ""             # AI-generated summary
    category: str = ""            # e.g. "Politics", "Tech", "World"
    image_url: str = ""           # lead image, taken from one of its articles
    tags: str = "[]"              # JSON list of ongoing-story tags, e.g. ["Iran war"]
    # JSON {"left": ..., "center": ..., "right": ...}: how each side framed the story,
    # written by the Claude session for stories covered across the spectrum
    framing: str = "{}"
    framing_updated: Optional[NaiveDatetime] = None
    article_count: int = 0
    source_count: int = 0
    first_seen: NaiveDatetime = Field(default_factory=utcnow)
    last_updated: NaiveDatetime = Field(default_factory=utcnow, index=True)

    articles: list[Article] = Relationship(back_populates="cluster")


class ScrapeRunBase(SQLModel):
    started_at: NaiveDatetime = Field(default_factory=utcnow)
    finished_at: Optional[NaiveDatetime] = None
    articles_fetched: int = 0
    articles_new: int = 0
    clusters_created: int = 0
    clusters_updated: int = 0
    status: str = Field(default="running", description="running | fetched | success | failed")
    error: str = ""


class ScrapeRun(ScrapeRunBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class ScrapeRunPublic(ScrapeRunBase):
    # Responses always include defaulted fields, so the generated types mark them required
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: int
