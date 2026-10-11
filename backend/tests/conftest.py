"""Shared test setup.

Every test runs against a throwaway SQLite file, never backend/groundednews.db.
`config` reads DATABASE_URL once and `database` builds its engine at import time,
so the environment variable has to be set here, before anything imports them.
"""
import atexit
import os
import shutil
import sys
import tempfile
from datetime import timedelta
from itertools import count
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REAL_DB = BACKEND / "groundednews.db"

_tmpdir = Path(tempfile.mkdtemp(prefix="groundednews-tests-"))
atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)
TEST_DB = _tmpdir / "test.db"

_already_imported = {"config", "database", "main"} & set(sys.modules)
assert not _already_imported, f"{_already_imported} imported before the test database was configured"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"  # dotenv never overrides an existing variable
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402
from sqlmodel import Session  # noqa: E402

import backup_db  # noqa: E402
import database  # noqa: E402
from models import Article, Cluster, Source  # noqa: E402
from save_clusters import _refresh_counts  # noqa: E402
from timeutil import utcnow  # noqa: E402

_engine_db = Path(database.engine.url.database).resolve()
assert _engine_db == TEST_DB.resolve(), f"tests would use {_engine_db}, not the temp database"
assert _engine_db != REAL_DB.resolve(), "tests must never touch the real database"

database.init_db()


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table before each test, so tests can't see each other's rows."""
    with database.engine.begin() as conn:
        for table in ("article", "cluster", "scraperun", "source", "story_fts"):
            conn.exec_driver_sql(f"DELETE FROM {table}")
    yield


@pytest.fixture(autouse=True)
def no_real_backups(tmp_path, monkeypatch):
    """Anything that calls backup() writes into a temp dir, never the project's backups/."""
    monkeypatch.setattr(backup_db, "BACKUP_DIR", tmp_path / "backups")


@pytest.fixture
def db():
    with Session(database.engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client():
    """API client. Not entered as a context manager on purpose: that would run the
    lifespan, which seeds the 17 default outlets into the empty database. Tests create
    exactly the outlets they need instead (test_api.py covers the seeding itself)."""
    from fastapi.testclient import TestClient
    import main
    return TestClient(main.app)


class Factory:
    """Small builders for outlets, articles and stories, committed straight away so the
    API and the scripts (which open their own sessions) can see them."""

    def __init__(self, session: Session):
        self.session = session
        self._n = count(1)

    def source(self, name: str | None = None, bias: str = "center", **kw) -> Source:
        n = next(self._n)
        source = Source(name=name or f"Outlet {n}", feed_url=f"https://outlet{n}.example/feed",
                        bias_label=bias, **kw)
        return self._save(source)

    def article(self, source: Source, title: str | None = None, cluster: Cluster | None = None,
                hours_ago: float | None = 1, **kw) -> Article:
        """`hours_ago` sets published_at (None leaves it empty, as for an undated feed item)."""
        n = next(self._n)
        if "published_at" not in kw:
            kw["published_at"] = utcnow() - timedelta(hours=hours_ago) if hours_ago is not None else None
        article = Article(source_id=source.id, cluster_id=cluster.id if cluster else None,
                          title=title or f"Article {n}", url=f"https://news.example/{n}", **kw)
        return self._save(article)

    def story(self, *sources: Source, headline: str | None = None, hours_ago: float = 1,
              opinion: bool = False, **kw) -> Cluster:
        """A story with one article from each of `sources`, counts and dates filled in
        the way save_clusters does it."""
        cluster = self._save(Cluster(headline=headline or f"Story {next(self._n)}", **kw))
        for source in sources:
            self.article(source, cluster=cluster, hours_ago=hours_ago, is_opinion=opinion,
                         scraped_at=utcnow() - timedelta(hours=hours_ago))
        return self.refresh(cluster)

    def refresh(self, cluster: Cluster) -> Cluster:
        _refresh_counts(self.session, cluster)
        return self._save(cluster)

    def _save(self, obj):
        self.session.add(obj)
        self.session.commit()
        self.session.refresh(obj)
        return obj


@pytest.fixture
def make(db) -> Factory:
    return Factory(db)


def pytest_configure(config):
    # feedparser 6.0.11 trips a Python 3.13 deprecation inside its own HTML sanitizer
    config.addinivalue_line("filterwarnings", "ignore::DeprecationWarning:feedparser.*")
    # starlette 0.38's TestClient uses an anyio alias that newer anyio deprecates
    config.addinivalue_line("filterwarnings", "ignore:The anyio.abc.BlockingPortal alias:DeprecationWarning")
