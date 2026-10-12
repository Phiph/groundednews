# GroundedNews MCP server and write-ups — design

Date: 2026-10-12
Status: approved in conversation, awaiting spec review

## Goal

Give Claude sessions — the 6-hourly `groundednews-scrape` routine and interactive sessions —
one typed MCP interface to the GroundedNews database, and use it to add three kinds of
written content that the site shows:

- **Story write-ups**: a longer piece (what happened, background, what's disputed) on a story page
- **Daily briefing text**: a written "the day in brief" at the top of `/briefing`
- **Thread summaries**: a rolling "where things stand" for an ongoing tag

The routine drafts these each run; the user writes or rewrites them from interactive
sessions, and sometimes just reads/chats. Saved content is the main use; chat-only is occasional.

### Non-goals

- Editorial tools (merge/split clusters, move articles, edit headlines) — not wanted now
- Fetching full article text; write-ups are grounded in stored RSS titles and summaries only
- Write-up version history (the daily DB backup is the safety net)
- Any write path for write-ups from the website (no API write endpoint, no editing UI)
- Using the Anthropic API from the backend; all AI work stays in Claude sessions

## Architecture

A Python MCP server, `backend/mcp_server.py`, built with FastMCP from the `mcp` package over
stdio. It imports the existing backend modules and talks to the same SQLite database through
the shared `database.engine`; the FastAPI backend does not need to be running.

It is registered in a committed `.mcp.json` at the repo root:

```json
{"mcpServers": {"groundednews": {"command": "venv/bin/python", "args": ["backend/mcp_server.py"]}}}
```

The server is pre-approved via `enabledMcpjsonServers: ["groundednews"]` in the **main
checkout's** `.claude/settings.local.json` (gitignored, so this is a manual post-merge step,
done alongside the routine prompt change) so the routine never stops at an approval prompt.
The routine runs in the main checkout, so the relative paths resolve.

The existing scripts (`fetch_articles.py`, `save_clusters.py`, `framing_candidates.py`) stay
unchanged and keep their tests; they are the routine's fallback.

`mcp` is added to `backend/requirements.txt`, pinned to the current release.

## Data model

New table `Writeup` in `backend/models.py`:

| field | type | notes |
|---|---|---|
| `id` | int PK | |
| `kind` | str | `story` · `briefing` · `thread` |
| `subject` | str | cluster id (as string) · UTC date `YYYY-MM-DD` · tag name |
| `title` | str | |
| `body` | str | Markdown |
| `author` | str | `routine` · `session` |
| `basis_count` | int | article count of the story / thread / day when written |
| `created_at` | NaiveDatetime | |
| `updated_at` | NaiveDatetime | |

Unique constraint on (`kind`, `subject`). Datetimes are `NaiveDatetime` per the repo's naive-UTC
convention. Created by `init_db` like the other tables.

**Staleness** is computed, never stored: a write-up is stale when the subject's current article
count exceeds `basis_count`. "Current article count" is:
- story: `Cluster.article_count`
- thread: total articles across clusters carrying the tag
- briefing: total articles in that day's briefing window (same window as `/api/briefing`)

**Overwrite rule:** a save with `author="routine"` is rejected when the existing write-up has
`author="session"`. A session save always succeeds and sets `author="session"`.

## MCP tools

All arguments are Pydantic models / typed parameters. Invalid input raises a tool error with a
message Claude can act on.

### Pipeline (mostly the routine)

- `fetch_articles()` → runs `fetch_new_articles` (including the daily backup) and returns
  `run_id`, `status`, `articles_fetched`, `articles_new`, `error`, `recent_clusters`,
  `active_tags`. It does **not** return the article list (MCP output-size limits).
- `get_pending_articles(offset=0, limit=50)` → page of `pending_articles()` plus `total`.
- `save_clusters(clusters, run_id)` → same entry shapes as `save_clusters.py` (new story /
  follow-up / framing-only). Validates the whole batch first — unknown article ids, an article in
  two entries, unknown `cluster_id`, missing headline on a new story — and writes nothing if any
  check fails. Then calls the existing `save_clusters()` and returns its counts.
- `get_framing_candidates(limit=12)` → `framing_candidates.candidates()`.
- `save_framing(notes)` → `[{cluster_id, framing: {left?, center?, right?}}]`; validated, then
  saved via the framing-only path.
- `get_writeup_candidates()` → what the routine should write this run:
  - `briefing`: today's UTC date, always included unless a `session` write-up exists for it
  - `threads`: up to 3 tags from `active_tags` that gained stories since their write-up (or have
    none), most active first
  - `stories`: up to 5 multi-side clusters (≥2 sides) in the Top window with no write-up or a
    stale one, ranked by `top_score`
  - Session-authored write-ups are excluded from all three.
  - Each candidate includes the source material needed to write it (story: articles by side +
    framing; thread: its stories in time order; briefing: the day's data).

### Reading (interactive sessions)

- `list_stories(sort="top", category=None, tag=None, since=None, limit=20)`
- `get_story(cluster_id)` → story, articles grouped by side, framing, write-up (with `stale`)
- `search_stories(q, limit=20)` → FTS5 search, same as `/api/search`
- `get_thread(tag, days=14)` → the tag's stories in time order, plus its write-up
- `get_day(date=None)` → the `/api/briefing` payload for that day, plus its write-up

These reuse the serialization helpers in `main.py` (moved to a shared module if importing
`main` would be awkward), so the MCP and the API return the same shapes.

### Writing

- `save_writeup(kind, subject, title, body, author="session")` → validates `subject` against
  `kind` (story: existing cluster; thread: a tag in use; briefing: valid date), applies the
  overwrite rule, sets `basis_count` from the current count, upserts.
- `get_writeup(kind, subject)`
- `delete_writeup(kind, subject)`

## Routine changes

`~/.claude/scheduled-tasks/groundednews-scrape/SKILL.md` (outside the repo; the diff is shown
to the user before saving) is rewritten to use the tools:

1. `fetch_articles()`
2. Page through `get_pending_articles` and cluster (clustering, opinion and tag rules unchanged)
3. `save_clusters(clusters, run_id)`
4. `get_framing_candidates` → `save_framing`
5. **New:** `get_writeup_candidates()`, then write with `author="routine"`:
   - today's briefing, ~200–350 words, rewritten each run
   - up to 3 thread summaries, ~150–250 words each
   - up to 5 story write-ups, ~150–300 words each
   - same neutrality rules as framing notes; ground every claim in the given titles/summaries
6. Finish as now.

Fallback: if the `groundednews` MCP tools are unavailable, use the existing scripts for steps
1–4 and skip step 5.

## API and frontend

### API (`backend/main.py`, `backend/schemas.py`)

- `schemas.Writeup`: `title`, `body`, `author`, `updated_at`, `stale`, `new_articles`
  (current count − `basis_count`, floor 0).
- `GET /api/clusters/{id}` (`ClusterDetail`) gains optional `writeup`.
- `GET /api/briefing` gains optional `writeup` for the date of `window_end`.
- New `GET /api/threads/{tag}` → `schemas.Writeup`, 404 when none exists.
- Regenerate `frontend/lib/api-schema.ts` with `npm run gen:api`.

### Frontend

- `components/news/writeup-card.tsx`: renders Markdown with `react-markdown` (new dependency,
  raw HTML disabled); footer "Written by the routine / by you · updated 3h ago", plus
  "N new articles since" when stale. Times via `lib/format.ts`.
- `/story/[id]`: card above the framing card.
- `/briefing`: card at the top, above the existing computed sections.
- `/?tag=X`: thread card above the story list, fetched from `/api/threads/{tag}`; a 404 renders
  nothing.
- No write-up → no card; the site looks as it does today until write-ups exist.

## Error handling

- Tool validation errors are returned as MCP tool errors with specific messages.
- `save_clusters` and `save_framing` validate the full batch before writing (the CLI script keeps
  its current lenient warn-and-skip behaviour).
- **stdout hygiene:** stdio carries the MCP protocol, and existing modules `print` (e.g.
  `backup_db`). Tool bodies run with `contextlib.redirect_stdout(sys.stderr)` so stray output
  can't corrupt the stream.
- **SQLite contention:** the engine gets `connect_args={"timeout": 30}` (busy timeout) so a
  concurrent API write waits instead of failing with "database is locked".
- Fetch failures are reported in `fetch_articles()`'s result (`status`, `error`), not raised.

## Testing

- **pytest** (`backend/tests/`, existing temp-DB fixtures):
  - `test_writeups.py`: overwrite rule, staleness per kind, subject validation, upsert,
    delete, `basis_count`.
  - `test_mcp_tools.py`: write-up candidate selection and caps, session exclusion, pending
    pagination, `save_clusters` / `save_framing` batch validation (nothing written on failure).
  - One end-to-end test using the MCP SDK's in-memory client: list tools, call
    `get_pending_articles`, and assert nothing was written to stdout.
  - API tests: `writeup` on cluster detail and briefing; `/api/threads/{tag}` 200 and 404.
- **Frontend:** `npm run gen:api`, typecheck, build; browser check of story, briefing and tag
  pages with seeded write-ups and with none.
- **Routine:** after merge, one manual run of the scheduled task, then check the site.
