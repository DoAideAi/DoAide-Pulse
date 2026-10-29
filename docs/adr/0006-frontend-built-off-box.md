# 0006: The frontend is built off the server and shipped as files

## Context
Production is one Hetzner box with 8 GB shared by every DoAide product. A Vite build
needs Node and a burst of memory; neither belongs on that box. `frontend/dist/`
is gitignored.

## Decision
The frontend is built on the deploying machine, from a clean checkout of
`origin/main`, and its `dist/` is rsynced to `/opt/Pulse/frontend/dist/`. The
server never builds it. The backend arrives by rsync (`deploy/deploy.sh`) or,
since `/opt/Pulse` became a git checkout, by `git pull --ff-only`. Migrations
run under a PostgreSQL advisory lock before the services restart.

## Consequences
- **`git pull` on the server updates the backend only.** A deploy that pulls
  without rebuilding and syncing the frontend leaves every UI change undeployed.
  The M9 editor features sat undeployed this way until the next full deploy.
- Build from a **clean worktree**, never the main checkout: it often holds
  another session's uncommitted work, and the build ships whatever is on disk.
- Files written as root must go back to `pulse:pulse`, or the services hit
  permission errors and 500.

## Rejected
- **Building on the server:** memory and toolchain on a shared box.
- **Committing `dist/`:** large churn in history, and merge conflicts on
  generated, hashed files.

## In the code
`deploy/deploy.sh`, `deploy/DEPLOYMENT.md`.
