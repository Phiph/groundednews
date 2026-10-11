import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".groundednews_env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend/groundednews.db")
# Resolve relative SQLite paths against the project root so the DB is found
# regardless of the working directory (start.sh runs uvicorn from backend/).
if DATABASE_URL.startswith("sqlite:///./"):
    DATABASE_URL = f"sqlite:///{PROJECT_ROOT / DATABASE_URL[len('sqlite:///./'):]}"
