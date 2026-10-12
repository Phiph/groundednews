# GroundedNews

A personal news aggregation platform inspired by Ground News. GroundedNews collects RSS articles from outlets across the political spectrum and groups coverage of the **same event** into a single story, so you can compare headlines, spot coverage gaps, and see how different sides framed the news.

The web app and RSS fetcher run locally without an AI API key. Clustering, framing, and write-ups are a separate analyst step: you can use a tool-enabled Claude Desktop session or recurring routine, using your Claude account rather than the Anthropic API. Claude works on the database through the bundled [MCP server](#claude-and-the-mcp-server) or, as a fallback, the analyst scripts. **Installing the app does not automatically enable AI clustering or schedule a routine.**

## Contents

- [What you can do](#what-you-can-do)
- [Local setup](#local-setup)
- [Docker setup](#docker-setup)
- [Populate your news feed](#populate-your-news-feed)
- [Claude Desktop automation without an API key](#claude-desktop-automation-without-an-api-key)
- [Claude and the MCP server](#claude-and-the-mcp-server)
- [Configuration, data, and backups](#configuration-data-and-backups)
- [Development and tests](#development-and-tests)
- [Troubleshooting](#troubleshooting)

## What you can do

- **Home:** browse stories by category or ongoing-story tag, sort by latest or top coverage, filter by source count, and include or exclude opinion. Filtering by a tag shows its thread write-up (“where things stand”), if one exists.
- **Story pages:** compare outlet headlines and summaries, follow coverage over time, open original articles, and read side-by-side framing notes and a longer story write-up when an analyst has written them.
- **Briefing:** catch up on prominent stories and coverage gaps, headed by a written “day in brief” when one exists.
- **Blindspot:** find stories predominantly covered by one side but absent from the other.
- **Search:** search story headlines, summaries, tags, and outlet article titles using SQLite full-text search.
- **Sources:** inspect outlet coverage and feed health. **Admin** lets you manage RSS feeds and bias labels, trigger a fetch, and inspect run history and clustering quality.
- **My diet:** review your reading balance. Story views and article clicks are stored in this browser's `localStorage`, not in a server-side reader account.

The backend seeds 17 feeds on an empty source table, including BBC News, The Guardian, Fox News, NPR, The Hill, and Newsweek. You can change these in Admin or add a feed with the CLI.

### What the bias bar means

Coverage bars count **distinct outlets**, not articles or an AI assessment of each article's language. `left` and `center-left` count toward the left bucket; `center-right` and `right` count toward the right bucket. Unrecognized labels are counted as unknown. Source ratings are editable assumptions, not authoritative verdicts.

A blindspot requires at least three outlets: one side has no coverage, and at least 70% of outlets are on the opposite side. This describes the feeds collected here, **not proof that an entire political side ignored a story**. Feed availability, incorrect clustering, and limited summaries can affect results. AI-generated headlines and framing notes should be reviewed against the original reporting.

## Local setup

### Prerequisites

- Python **3.12** and Node.js **22** with npm (the versions used by CI and Docker).
- Git and internet access for dependencies and RSS feeds.
- A Bash-compatible terminal for `start.sh` (macOS/Linux; on Windows, use WSL or Docker).

Get the repository, then work from its root. Replace `/absolute/path/to/groundednews` below with your checkout's actual path.

```bash
git clone https://github.com/Phiph/groundednews.git /absolute/path/to/groundednews
cd /absolute/path/to/groundednews
python3 -m venv venv
venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
./start.sh
```

No environment file, database server, or API key is required for the default setup. The backend creates SQLite tables and seeds sources on startup.

Open:

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

Press **Ctrl+C** to stop both services. The initial story list is empty until articles have been fetched **and clustered**.

To run the services separately, use two terminals:

```bash
# Terminal 1
cd /absolute/path/to/groundednews
venv/bin/uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

```bash
# Terminal 2
cd /absolute/path/to/groundednews/frontend
npm run dev
```

The frontend proxies `/api/*` to `127.0.0.1:8000`, so normal development needs no separate browser API URL.

> **Local-use security:** the API has unauthenticated write/admin endpoints. `start.sh` binds the backend to `0.0.0.0`; use the separate backend command above for a loopback-only backend, and keep development servers on a trusted machine/network. Add authentication and TLS at a reverse proxy before any public deployment.

## Docker setup

With Docker and the Compose plugin installed, run from the repository root:

```bash
docker compose up --build -d
docker compose logs -f
```

Open http://localhost:3000. One container runs Next.js and FastAPI; only the frontend port is published, bound to localhost. The named `groundednews-data` volume persists SQLite at `/data/groundednews.db`.

```bash
docker compose down   # Stop services; preserve the data volume
```

**Do not use `docker compose down -v` unless you intend to delete your database.**

When a published image is available, you can use it instead of building:

```bash
docker compose pull
docker compose up -d --no-build
```

The image is `ghcr.io/phiph/groundednews:latest`; versioned tags are also published for pinning. Images currently target Linux amd64. See the [existing deployment and release details](frontend/README.md#groundednews-docker-deployment) for bind mounts, permissions, and release configuration.

**Docker and native installations use different databases by default.** The [analyst routine](docs/claude-routine.md#reusable-analyst-routine) targets the native checkout. To operate on Docker's data, execute the scripts inside the running container instead.

**Before using the Docker fetch script**, configure a persistent, writable backup directory. Fetching calls the backup helper unconditionally and will fail with a permission error under the default Compose setup because `/app/backups` is not writable. On a Linux host:

```bash
mkdir -p /absolute/path/to/groundednews-backups
sudo chown 10001:10001 /absolute/path/to/groundednews-backups
```

Add this bind mount to the existing `groundednews` service's `volumes` list in `compose.yaml`, **keeping** the existing `groundednews-data:/data` mount:

```yaml
      - type: bind
        source: /absolute/path/to/groundednews-backups
        target: /app/backups
```

Recreate the service with `docker compose up -d` to apply the mount. Confirm it is writable by container UID 10001 (Docker Desktop host permissions can differ), then run the analyst commands:

```bash
docker compose exec -T groundednews python /app/backend/fetch_articles.py > /absolute/path/to/scratch/fetch.json
docker compose cp /absolute/path/to/scratch/clusters.json groundednews:/tmp/clusters.json
docker compose exec -T groundednews python /app/backend/save_clusters.py /tmp/clusters.json RUN_ID
docker compose exec -T groundednews python /app/backend/framing_candidates.py > /absolute/path/to/scratch/framing.json
docker compose cp /absolute/path/to/scratch/framing_notes.json groundednews:/tmp/framing_notes.json
docker compose exec -T groundednews python /app/backend/save_clusters.py /tmp/framing_notes.json
```

Create the host scratch directory first, replace `RUN_ID` with the fetched integer, and let the analyst produce each JSON input before copying it. Do not run native scripts expecting them to update the container's database.

## Populate your news feed

The pipeline is deliberately split:

```text
RSS feeds → fetch_articles.py → raw articles in SQLite
                                     ↓
                         Claude / human analyst
                                     ↓
                cluster, framing and write-up content
                                     ↓
            MCP tools (or save_clusters.py) → SQLite → web app
```

1. Fetch articles through Admin, `venv/bin/python cli.py scrape`, the MCP `fetch_articles` tool, or the `fetch_articles.py` script.
2. Have an analyst group them into stories and save the clusters.
3. Generate framing candidates, write grounded notes, and save them separately.
4. Optionally write story, thread, and briefing write-ups. These can only be saved through the MCP server; the scripts have no write-up step.

The web scraper and CLI scraper **do not perform AI analysis**. The routine's fetch includes recent unclustered leftovers from those scrapes, so they can be clustered on the next run.

Useful CLI commands, from the repository root:

```bash
venv/bin/python cli.py status
venv/bin/python cli.py sources
venv/bin/python cli.py sources add
venv/bin/python cli.py scrape
```

For machine-readable analyst input, use `backend/fetch_articles.py`, not `cli.py scrape`.

## Claude Desktop automation without an API key

Use a tool-enabled Claude Desktop session to cluster articles and write framing notes with your Claude account, without an Anthropic API key. Local file and shell access are required; account limits and scheduling availability still apply.

See the [Claude automation guide and reusable analyst routine](docs/claude-routine.md) for permissions, scheduling, safety checks, and the complete routine prompt.

## Claude and the MCP server

`backend/mcp_server.py` is a stdio [MCP](https://modelcontextprotocol.io) server that gives Claude typed tools over the GroundedNews database. It opens SQLite directly, so the web app does not need to be running. The committed `.mcp.json` registers it as `groundednews` for Claude Code sessions started in the repository root:

```json
{"mcpServers": {"groundednews": {"command": "venv/bin/python", "args": ["backend/mcp_server.py"]}}}
```

Claude Code asks you to approve project MCP servers the first time. For unattended routines, pre-approve it by adding `"enabledMcpjsonServers": ["groundednews"]` to the checkout's `.claude/settings.local.json` (Git ignores this file), so a scheduled run never stops at an approval prompt.

| Group | Tools |
| --- | --- |
| Pipeline | `fetch_articles`, `get_pending_articles`, `save_clusters`, `get_framing_candidates`, `save_framing`, `get_writeup_candidates` |
| Reading | `list_stories`, `get_story`, `search_stories`, `get_thread`, `get_day` |
| Write-ups | `save_writeup`, `get_writeup`, `delete_writeup` |

Unlike `save_clusters.py`, which warns and skips, the MCP `save_clusters` and `save_framing` tools validate the whole batch first and save nothing if any article or story ID is unknown, an article appears twice, or a story is both emptied (all its articles moved elsewhere) and given follow-ups. Emptying a story by moving its articles out is allowed; the empty story is deleted. The `fetch_articles` tool also runs the daily backup.

**Write-ups** are Markdown pieces shown on the site: a story write-up (subject: cluster ID), a thread summary (subject: tag), and a daily briefing (subject: the date `get_day` returns). Each records whether it was written by the scheduled `routine` or an interactive `session`. The routine never overwrites a session-written write-up, so your own edits stay. A write-up is marked stale, with “N new articles since”, when its subject gains articles. The website only displays write-ups; you can't edit them there.

In an interactive session you can ask Claude to read stories (“summarise the top stories today”) or write and rewrite write-ups. See the [routine guide](docs/claude-routine.md#mcp-routine) for the scheduled flow.

To use the MCP server against the Docker database, point the MCP command at the container instead, for example `"command": "docker", "args": ["compose", "exec", "-T", "groundednews", "python", "/app/backend/mcp_server.py"]`. The `fetch_articles` tool needs the writable backup mount described in [Docker setup](#docker-setup).

## Configuration, data, and backups

| Setting | Default / behavior |
| --- | --- |
| `DATABASE_URL` | `sqlite:///./backend/groundednews.db`; this relative form is resolved against the project root |
| `.groundednews_env` | Loaded by backend configuration, including standalone scripts; existing environment variables take precedence |
| `.env` | Exported by `start.sh`, **not automatically loaded by standalone backend scripts** |
| `NEXT_PUBLIC_API_URL` | Optional frontend API origin override; normally leave unset to use the same-origin proxy; applied at frontend build time |

To use the same custom database for the app and routine, put its `DATABASE_URL` in the root `.groundednews_env`, or export it consistently for every command. For example, `cp .env.example .groundednews_env`, then edit that file. Do not rely on `start.sh`'s `.env` when running scripts separately. Use a literal path (no shell substitutions inside dotenv values), and create the parent directory for a custom SQLite location.

The implementation relies on SQLite, including FTS5 search and SQLite-specific schema initialization. Changing `DATABASE_URL` does not make other database engines supported.

`fetch_articles.py` calls the SQLite online backup API before fetching. Backups live in root `backups/groundednews-YYYY-MM-DD.db`, at most once per day, retaining the newest seven copies. It skips backup if the database does not exist yet. Admin and `cli.py scrape` do not invoke this backup wrapper.

```bash
cd /absolute/path/to/groundednews
venv/bin/python backend/backup_db.py
venv/bin/python backend/backup_db.py --force   # Replace today's backup
```

For a native restore, stop the web app and any routines, preserve the current database, and copy the chosen backup over the configured database file before restarting. Online backups are safe while the app runs; ordinary file copies of the live database are not.

In Docker, the daily backup helper writes under `/app/backups`, which is **not** the Compose data volume and may not be writable by the image's non-root user. Do not assume automatic backups are persistent or available there; arrange a writable persistent backup mount if using that helper, or stop the container and back up the `/data` volume externally.

Environment files, databases, and native backups are ignored by Git. Keep scratch outputs outside the checkout, and maintain independent backups for data you care about.

## Development and tests

### Project layout

| Path | Purpose |
| --- | --- |
| `backend/main.py` | FastAPI routes and startup |
| `backend/models.py`, `schemas.py`, `database.py` | SQLModel storage, API models, SQLite initialization and seeded feeds |
| `backend/scraper.py`, `fetch_articles.py` | RSS collection and analyst input |
| `backend/save_clusters.py`, `framing_candidates.py` | Analyst outputs and framing work queue |
| `backend/mcp_server.py`, `.mcp.json` | MCP server for Claude sessions and routines |
| `backend/writeups.py`, `writeup_candidates.py` | Write-up storage, staleness and the routine's write-up queue |
| `backend/bias.py`, `backup_db.py` | Coverage rules and daily backups |
| `backend/tests/` | Pytest coverage, including opt-in Docker smoke tests |
| `frontend/app/`, `components/`, `lib/` | Next.js App Router UI, components, API client and browser history |
| `cli.py`, `start.sh` | Local management and development launcher |
| `Dockerfile`, `compose.yaml` | Combined production container |

The UI uses React, TypeScript, Tailwind CSS, and shadcn/Radix components. FastAPI exposes its schema at `/openapi.json`; use `/docs` to explore request and response models. Common endpoints include `/api/clusters`, `/api/search`, `/api/briefing`, `/api/threads/{tag}` (a thread's write-up), `/api/sources`, `/api/stats`, `/api/runs`, and `/api/scrape`. Write-ups are read-only over the HTTP API; only the MCP server writes them.

From the repository root:

```bash
venv/bin/python -m pip install -r backend/requirements-dev.txt
venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run lint
npm --prefix frontend run build
```

Normal backend tests use temporary databases and skip the opt-in container test. For focused analyst-script coverage:

```bash
venv/bin/python -m pytest backend/tests/test_agent_scripts.py backend/tests/test_fetch_articles.py backend/tests/test_save_clusters.py -q
```

For the MCP server and write-ups:

```bash
venv/bin/python -m pytest backend/tests/test_mcp_server.py backend/tests/test_writeups.py backend/tests/test_writeup_candidates.py backend/tests/test_writeup_api.py -q
```

After changing backend response models, regenerate the checked-in frontend API types:

```bash
cd /absolute/path/to/groundednews/frontend
npm run gen:api
```

To exercise the container:

```bash
cd /absolute/path/to/groundednews
docker build -t groundednews:test .
GROUNDEDNEWS_IMAGE=groundednews:test venv/bin/python -m pytest backend/tests/test_container.py -q
```

CI runs backend tests, frontend lint/build, and the container smoke test. See [release documentation](frontend/README.md#ci-and-releases) for Conventional Commit titles, release-please, and GHCR publishing.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Empty homepage after fetching | Raw articles need clustering. Run the analyst routine and check the save result. |
| `venv/bin/python` or `uvicorn` missing | Create `venv` at the repository root and install backend requirements. |
| UI cannot reach the API | Ensure port 8000 is serving FastAPI; inspect `/docs`. Keep `NEXT_PUBLIC_API_URL` unset for the default proxy. |
| Source stops producing articles | Inspect Admin feed errors/failure streaks and the feed URL. Conditional HTTP responses and duplicate filtering can also yield no new articles. |
| Routine has no pending articles | Recent unclustered articles are offered for 48 hours; continue to framing candidates even if the count is zero. |
| Wrong database or no changes visible | Check `.groundednews_env`, exported `DATABASE_URL`, and whether you mixed native and Docker installations. |
| “Database is locked” or conflicting runs | Stop overlapping fetch/save jobs and retry only after checking what was already saved. |
| Claude cannot execute a command | Confirm the selected Desktop mode has local shell/file tools and permissions; ordinary chat is insufficient. |
| `groundednews` MCP tools missing | Start Claude Code from the repository root, so the relative `venv/bin/python` in `.mcp.json` resolves, and check that backend requirements, which include `mcp`, are installed. Approve the server, or add it to `enabledMcpjsonServers`. |
| Routine didn't update a write-up | Write-ups saved from an interactive session are never overwritten by the routine. Delete the write-up with `delete_writeup` to hand it back. |
| Invalid JSON or skipped IDs | Inspect scratch files; use real integer IDs, a JSON array, and a file path rather than inline JSON. |
| Docker data disappears | Check the named volume; `down -v` deletes it. Back up data independently. |
