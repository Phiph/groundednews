# GroundedNews

GroundedNews collects RSS news from across the political spectrum and groups
coverage of the same event into stories, so you can compare headlines, spot
coverage gaps, and explore how outlets frame the news.

## Quick start: run the published Docker image

You don't need to clone this repository or build the app. Install Docker, then
run:

```bash
docker volume create groundednews-data
docker run -d --name groundednews --restart unless-stopped \
  -p 127.0.0.1:3000:3000 \
  -v groundednews-data:/data \
  ghcr.io/phiph/groundednews:latest
```

Open [http://localhost:3000](http://localhost:3000). Your database is stored in
the `groundednews-data` Docker volume and persists when the container is
replaced. To stop the app, run `docker stop groundednews`; **do not remove the
volume** unless you intend to delete its data. The published image currently
supports Linux amd64.

The app starts with RSS sources, but the story list is empty until articles are
fetched and grouped into stories. Fetch articles in Admin, then use the
[analyst routine](docs/claude-routine.md) to cluster coverage and write framing
notes. The routine requires a tool-enabled Claude session; installing the app
does not run AI analysis or schedule it.

## Want to run from source?

Install Python 3.12 and Node.js 22, then from the repository root:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
./start.sh
```

Open [http://localhost:3000](http://localhost:3000). No API key is required for
the app or RSS fetcher. For the full source setup, Docker operations, data and
backup guidance, configuration, troubleshooting, and test commands, see the
[operations and development reference](docs/operations.md).

## Guides

- [Docker deployment, data, and backups](docs/operations.md#docker-setup)
- [Claude automation and analyst routine](docs/claude-routine.md)
- [Contributing](CONTRIBUTING.md)

The API includes unauthenticated write and admin operations. The quick start
binds to localhost; before exposing the service beyond a trusted machine, add
authentication and TLS at a reverse proxy. See the
[Docker deployment guidance](docs/operations.md#docker-setup) for details.
