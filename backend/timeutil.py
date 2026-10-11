from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as naive UTC, the convention for every timestamp in the database.
    (datetime.utcnow() does the same but is deprecated from Python 3.12.)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
