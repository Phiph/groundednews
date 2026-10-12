"""
API response shapes. FastAPI validates every response against these, and they are the
source of the frontend's types: after changing one, run `npm run gen:api` in frontend/
to regenerate frontend/lib/api-schema.ts. Descriptions become doc comments there.
"""
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, NaiveDatetime

from models import ScrapeRunPublic, SourcePublic

Side = Literal["left", "center", "right"]


class ClusterSource(BaseModel):
    """One outlet's article in a story."""
    source_id: int
    source_name: str
    bias_label: str
    title: str
    url: str
    published_at: datetime = Field(description="Publish time, or when we found it if the feed gave none")
    image_url: str
    is_opinion: bool


class ClusterSourceDetail(ClusterSource):
    summary: str


class Bias(BaseModel):
    """Distinct outlets covering a story, per side."""
    left: int
    center: int
    right: int
    unknown: int
    blindspot: Optional[Literal["left", "right"]] = Field(
        description="Side that is largely ignoring the story, if any")


class Writeup(BaseModel):
    """A longer AI-written piece in Markdown: a story write-up, a day's briefing or a thread summary."""
    kind: Literal["story", "briefing", "thread"]
    subject: str = Field(description="Cluster id, UTC date (YYYY-MM-DD) or tag")
    title: str
    body: str = Field(description="Markdown")
    author: Literal["routine", "session"] = Field(
        description='"routine" = drafted by the scheduled task; "session" = written in an interactive session')
    updated_at: NaiveDatetime
    stale: bool = Field(description="Coverage has grown since it was written")
    new_articles: int = Field(description="Articles added since it was written")


class Cluster(BaseModel):
    """A story: articles from several outlets about the same event."""
    id: int
    headline: str
    summary: str
    category: str
    tags: list[str]
    framing: dict[str, str] = Field(
        description="How each side's outlets framed the story, keyed by side; {} until written")
    image_url: str
    article_count: int
    source_count: int
    first_seen: datetime
    last_updated: datetime
    bias: Bias
    is_opinion: bool = Field(description="Only opinion pieces so far, no straight reporting")
    sources: list[ClusterSource]


class ClusterDetail(Cluster):
    sources: list[ClusterSourceDetail]
    writeup: Optional[Writeup] = None


class SearchResults(BaseModel):
    total: int
    results: list[Cluster]


class TagCount(BaseModel):
    tag: str
    count: int


class SourceSummary(BaseModel):
    """An outlet's activity over the summary window."""
    id: int
    name: str
    home_url: str
    bias_label: str
    enabled: bool
    articles: int
    opinion: int
    stories: int
    latest_article: Optional[datetime]


class SourcesSummary(BaseModel):
    days: int
    sources: list[SourceSummary]


class CategoryCount(BaseModel):
    category: str
    count: int


class SourceProfile(BaseModel):
    source: SourcePublic
    days: int
    articles: int
    opinion: int
    stories: int
    shared_stories: int = Field(description="Stories at least one other outlet also covered")
    exclusive_stories: int
    first_reports: int = Field(description="Shared stories where this outlet published first")
    categories: list[CategoryCount]
    missed: list[Cluster] = Field(description="Widely covered recent stories this outlet didn't cover")


class BriefingBlindspots(BaseModel):
    left: list[Cluster]
    right: list[Cluster]


class BriefingTotals(BaseModel):
    stories: int
    articles: int
    outlets: int


class Briefing(BaseModel):
    window_start: Optional[datetime] = Field(description="Start of the 24h window, which ends at the newest story")
    window_end: Optional[datetime]
    stories: list[Cluster] = Field(description="Top 10 news stories (no opinion-only) with 2+ outlets, best first")
    blindspots: BriefingBlindspots = Field(description="Up to 3 per side, from the wider 72h window")
    tags: list[TagCount]
    totals: BriefingTotals
    writeup: Optional[Writeup] = Field(default=None, description="The written briefing for window_end's date; until the new day's is written, the previous day's (marked stale)")


class QualityDay(BaseModel):
    """One day of clustering quality, by when stories first appeared (UTC)."""
    date: str
    stories: int
    multi_source: int
    share: float = Field(description="multi_source / stories, 0-1")


class Stats(BaseModel):
    total_clusters: int
    total_articles: int
    active_sources: int
    last_run: Optional[ScrapeRunPublic]


class ScrapeStarted(BaseModel):
    status: Literal["started"]


class ScrapeStatus(BaseModel):
    running: bool
