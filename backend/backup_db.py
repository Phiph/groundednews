"""
Daily database backup: copies the live SQLite database to backups/groundednews-YYYY-MM-DD.db
and keeps the newest KEEP copies. Uses SQLite's online backup API, so it's safe while the
API or a fetch is writing. Runs once a day: later calls the same day are no-ops.

Usage: python backup_db.py [--force]   (--force replaces today's backup)
Also called at the start of fetch_articles.py, so the scheduled task keeps backups current.
"""
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DATABASE_URL, PROJECT_ROOT

BACKUP_DIR = PROJECT_ROOT / "backups"
KEEP = 7


def backup(force: bool = False) -> Path | None:
    """Back up the database if today's copy doesn't exist yet. Returns the new file, if any."""
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    source = Path(DATABASE_URL[len("sqlite:///"):])
    if not source.exists():
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"groundednews-{date.today().isoformat()}.db"
    if target.exists() and not force:
        return None

    # Write to a temp name first so a half-written file never looks like a valid backup
    partial = target.with_suffix(".db.partial")
    # closing(): a bare `with sqlite3.connect()` only commits, it doesn't close the file
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(partial)) as dst:
        src.backup(dst)
    partial.replace(target)

    for old in sorted(BACKUP_DIR.glob("groundednews-*.db"))[:-KEEP]:
        old.unlink()
    return target


if __name__ == "__main__":
    made = backup(force="--force" in sys.argv)
    print(f"Backed up to {made}" if made else "Today's backup already exists (use --force to redo it)")
