# Contributing

## Commit messages

Releases are cut by [release-please](https://github.com/googleapis/release-please),
which reads [Conventional Commits](https://www.conventionalcommits.org/) to pick
the next version and write the changelog. Every commit must look like:

```
<type>[optional scope]: <description>
```

| Type | Release effect |
| --- | --- |
| `feat` | minor bump, listed under Features |
| `fix` | patch bump, listed under Bug Fixes |
| `feat!` / `fix!` or a `BREAKING CHANGE:` footer | major bump |
| `build`, `chore`, `ci`, `docs`, `perf`, `refactor`, `revert`, `style`, `test` | no release on their own |

Examples: `feat(briefing): add weekly digest`, `fix: handle empty RSS feeds`,
`chore(deps): bump fastapi to 0.120`.

Install the commit-msg hook once per clone so bad messages are rejected locally:

```bash
pipx install pre-commit
pre-commit install
```

CI checks every non-merge commit in a pull request as well, so commits made
without the hook (web edits, bots, agents) are still caught. Fix a bad message
with `git commit --amend` or `git rebase -i` and force-push.
