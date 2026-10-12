This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to optimize the locally installed [Geist](https://vercel.com/font) font, without downloading fonts during builds.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

## GroundedNews Docker deployment

From the repository root, run `docker compose up --build -d` to build and run
the frontend and backend in one image. Open http://localhost:3000. Next.js proxies
`/api/*` to the internal FastAPI server, so no separate API port or CORS setup is
needed. Local development uses the same proxy with the backend on port 8000.
`NEXT_PUBLIC_API_URL` can still override the API address at frontend build time.

After the first release, use `docker compose pull && docker compose up -d --no-build`
to run the published `ghcr.io/phiph/groundednews:latest` image. Versioned tags
(for example, `0.2.0`) are also published; pin a version for reproducible deployments.
Images currently target Linux amd64.

The named `groundednews-data` volume persists SQLite at `/data/groundednews.db`
across container replacement. Do not run `docker compose down -v` unless you intend
to delete that data. To use a host directory instead:

```sh
mkdir -p ./data
sudo chown 10001:10001 ./data
docker run -d --name groundednews -p 127.0.0.1:3000:3000 \
  --mount type=bind,source="$(pwd)/data",target=/data \
  ghcr.io/phiph/groundednews:latest
```

Mount the whole directory, not just the database file, so SQLite can write its
journal files. `DATABASE_URL` can override the location (for example,
`sqlite:////data/custom.db`). The image runs as UID 10001; bind mounts must be
writable by that UID. Stop the container before copying an existing SQLite
database into the volume or taking a file-level backup.

The API includes unauthenticated write/admin operations. Keep the service on a
trusted network; add authentication and TLS at a reverse proxy before exposing it
publicly. The Compose example binds only to localhost.

## CI and releases

The `CI` workflow runs backend pytest tests, frontend lint/build, and a Docker
smoke test on pull requests, merge queues, and pushes to main. The smoke test checks
the UI, static assets, same-origin API writes, graceful shutdown, and SQLite
persistence across container replacement. To run it locally after building:

```sh
docker build -t groundednews:test .
GROUNDEDNEWS_IMAGE=groundednews:test python -m pytest backend/tests/test_container.py -q
```

Install `backend/requirements-dev.txt` in your Python environment first. Normal
backend test runs skip this opt-in Docker test.

In GitHub repository settings, require **Backend tests**, **Frontend lint and
build**, and **Container build and smoke test** before merging. Enable Actions'
permission to create pull requests. Release-please runs only after all checks pass
on main. Use Conventional Commit PR titles when squash-merging (`fix: ...`,
`feat: ...`, or `feat!: ...`) so it can prepare a release PR with a changelog and
version bump. Merging that PR creates a GitHub release and publishes the combined
image to GHCR with version, major.minor, and `latest` tags.

Set the repository secret `RELEASE_PLEASE_TOKEN` to a fine-grained PAT with access
to this repository and Contents and Pull requests read/write permissions (or an
equivalently scoped GitHub App token) so release PRs trigger CI automatically.
Without it, release-please uses `GITHUB_TOKEN`, whose PRs do not trigger other
workflows; run CI manually on the release PR branch using the workflow's **Run
workflow** button before merging. Publishing
uses the built-in `GITHUB_TOKEN` with Packages write permission. Set the GHCR
package visibility to public if anonymous pulls are desired.
