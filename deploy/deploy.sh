#!/usr/bin/env bash
# Pulse — deploy to the Hetzner box.
#
#   ./deploy/deploy.sh            # build, sync, migrate, restart
#   ./deploy/deploy.sh --no-build # skip the frontend build (backend-only change)
#   ./deploy/deploy.sh --skip-preflight  # skip local preflight checks
#   ./deploy/deploy.sh --allow-dirty     # ship uncommitted changes (recorded as such)
#
# The server is a plain rsync copy with no .git, matching the other apps on the
# box. Nothing builds on the server: it has 4 GB of RAM shared between six
# applications, and a Vite build there competes with live traffic.
set -euo pipefail

HOST=${PULSE_HOST:-89.167.8.178}
SSH_KEY=${PULSE_SSH_KEY:-/Users/dev/projects/keys/hetzner_deploy_ed25519}
REMOTE=/opt/Pulse
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH=(ssh -i "$SSH_KEY" "root@$HOST")

cd "$REPO_ROOT"

SKIP_BUILD=0
SKIP_PREFLIGHT=0
ALLOW_DIRTY=0
for arg in "$@"; do
  case "$arg" in
    --no-build) SKIP_BUILD=1 ;;
    --skip-preflight) SKIP_PREFLIGHT=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
  esac
done

# ---- Ship a commit, not a working tree ------------------------------------
# rsync copies what is on disk, and the history below records HEAD. Nothing
# held those to being the same: an uncommitted edit — half a change, a debug
# print, another session's work in this shared checkout — went to production
# without passing CI, under a commit id that does not contain it, which is the
# record rollback.sh trusts. Untracked files count: rsync ships them too.
# Ignored ones (frontend/dist, .env) do not, so --porcelain's view is the one.
DIRTY=$(git status --porcelain 2>/dev/null || true)
if [ -n "$DIRTY" ] && [ "$ALLOW_DIRTY" -eq 0 ]; then
  {
    echo "refusing to deploy: the checkout has uncommitted changes, which rsync"
    echo "would ship under a commit that does not contain them:"
    echo "$DIRTY" | sed 's/^/    /'
    echo "Commit them (and let CI pass), or deploy from a clean worktree."
    echo "--allow-dirty ships them anyway and records the deploy as <commit>-dirty."
  } >&2
  exit 1
fi

# ---- Preflight checks (local) --------------------------------------------
if [ "$SKIP_PREFLIGHT" -eq 0 ] && [ -x deploy/preflight.sh ]; then
  echo "==> running preflight checks"
  deploy/preflight.sh --env-only
  echo
fi

DEPLOY_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
if [ -n "$DIRTY" ]; then
  DEPLOY_COMMIT="${DEPLOY_COMMIT}-dirty"
fi
DEPLOY_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "==> deploying commit $DEPLOY_COMMIT at $DEPLOY_TIMESTAMP"

if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "==> building frontend"
  (cd frontend && npm run build)
fi

# Dependencies go in before the code they serve, from the requirements file
# alone. Installed after the sync, a pip failure (PyPI down, a yanked pin) left
# the new code on disk under services still running with the old packages —
# and Celery recycles its pool children every 200 tasks, so the worker went on
# to import the new code against them without anyone restarting it. Now the
# failure stops the deploy with the box exactly as it was.
#
# Skipped when the file is the one last installed, so a deploy that changes no
# pin does not need PyPI to be up at all. The stamp lives in the venv: it is
# about what is installed there, and rsync never touches it.
# A deploy that runs out of disk half way through the sync stops (set -e) with
# some files new and some old, under services still running — a tree no commit
# ever had. pip, the frontend sync and the migration all write too. So it does
# not start below a floor, the same check backup.sh makes before a dump.
MIN_FREE_MB=${PULSE_DEPLOY_MIN_FREE_MB:-1024}
echo "==> checking free space on $HOST:$REMOTE"
free_mb=$("${SSH[@]}" "df -Pm $REMOTE | awk 'NR==2 {print \$4}'")
if [ "${free_mb:-0}" -lt "$MIN_FREE_MB" ]; then
  echo "only ${free_mb:-?}MiB free on $HOST:$REMOTE, below the ${MIN_FREE_MB}MiB floor —" \
    "nothing was changed. Free some space and deploy again." >&2
  exit 1
fi

# Memory as well as disk. On 2026-10-29 this box (8 GB, shared by every
# product) sat at full RAM and full swap when a deploy added its own load, and
# everything on it stopped answering — load near 180, SSH timing out at the
# banner. A deploy needs headroom: pip, then four services restarting at once,
# two uvicorn workers and a Celery pool each importing the whole app. Below the
# floor it changes nothing. An answer that is not a number counts as none.
MIN_MEM_MB=${PULSE_DEPLOY_MIN_MEM_MB:-600}
echo "==> checking available memory on $HOST"
mem_mb=$("${SSH[@]}" "awk '/^MemAvailable:/ {print int(\$2/1024)}' /proc/meminfo")
case "$mem_mb" in ''|*[!0-9]*) mem_mb=0 ;; esac
if [ "$mem_mb" -lt "$MIN_MEM_MB" ]; then
  echo "only ${mem_mb}MiB of memory available on $HOST, below the ${MIN_MEM_MB}MiB floor —" \
    "nothing was changed. Wait for the box to settle (free -m) and deploy again." >&2
  exit 1
fi

echo "==> installing backend dependencies (before the code changes)"
rsync -az -e "ssh -i $SSH_KEY" \
  backend/requirements.txt "root@$HOST:$REMOTE/.deploy-requirements.txt"
"${SSH[@]}" bash -euo pipefail <<'DEPS_SCRIPT'
req=/opt/Pulse/.deploy-requirements.txt
stamp=/opt/Pulse/.venv/.requirements.sha256
want=$(sha256sum "$req" | cut -d' ' -f1)
if [ "$(cat "$stamp" 2>/dev/null || true)" = "$want" ]; then
  echo "requirements unchanged since the last install, skipping pip"
else
  chmod 0644 "$req"
  # pip itself first. The Dockerfile and CI upgrade it and this did not, so the
  # box's venv sat on pip 24.0 with seven published advisories (M17), and pip
  # is what fetches and unpacks every package installed below.
  sudo -u pulse /opt/Pulse/.venv/bin/pip install -q --upgrade pip
  sudo -u pulse /opt/Pulse/.venv/bin/pip install -q -r "$req"
  echo "$want" > "$stamp"
  chown pulse:pulse "$stamp"
fi
rm -f "$req"
DEPS_SCRIPT

echo "==> syncing to $HOST:$REMOTE"
# The excludes (deploy/rsync-excludes, shared with rollback.sh) are also what
# protects them from --delete: .env, the server's venv, the beat schedule, the
# deploy history and user uploads live only on the box and must survive a
# deploy. Uploads were safe before only while the local copy happened to hold
# every file the server did.
rsync -az --delete --exclude-from deploy/rsync-excludes \
  -e "ssh -i $SSH_KEY" \
  ./ "root@$HOST:$REMOTE/"

# frontend/dist is gitignored, so rsync it explicitly.
rsync -az --delete -e "ssh -i $SSH_KEY" \
  frontend/dist/ "root@$HOST:$REMOTE/frontend/dist/"

echo "==> migrating, restarting"
"${SSH[@]}" bash -euo pipefail <<REMOTE_SCRIPT
# rsync runs as root; leaving root-owned files under a service that runs as
# \`pulse\` is the classic post-deploy 500.
chown -R pulse:pulse /opt/Pulse

# Unit files. rsync puts them under /opt/Pulse/deploy/systemd, which is not
# where systemd looks — until this ran, editing a unit and deploying changed
# nothing, and the drift was invisible because \`systemctl status\` reports the
# copy in /etc while the reviewed one sits in the repo.
#
# Copied rather than symlinked: a symlink into /opt would make an rsync mid-run
# a live edit of an active unit. Ownership is set explicitly because the chown
# above just made the source pulse-owned, and a root-run unit file that a
# service account can write is a privilege escalation.
units_changed=0
unit_names=()
for source in /opt/Pulse/deploy/systemd/*.service /opt/Pulse/deploy/systemd/*.timer; do
  installed=/etc/systemd/system/\$(basename "\$source")
  unit_names+=("\$(basename "\$source")")
  if ! cmp -s "\$source" "\$installed"; then
    install -m 0644 -o root -g root "\$source" "\$installed"
    echo "installed \$(basename "\$source")"
    units_changed=1
  fi
done

if [ "\$units_changed" -eq 0 ] && [ \${#unit_names[@]} -gt 0 ] &&
   systemctl show "\${unit_names[@]}" -p NeedDaemonReload --value | grep -qx yes; then
  echo "systemd is running an outdated copy of a unit"
  units_changed=1
fi

if [ "\$units_changed" -eq 1 ]; then
  systemctl daemon-reload
fi

# And on. A timer installed above and left disabled never fires: the backup
# timer was copied into place by every deploy and enabled by none — a manual
# step in DEPLOYMENT.md nobody had taken, so the box had no database backup at
# all. enable --now is idempotent, so a timer already on is untouched.
for timer in /opt/Pulse/deploy/systemd/*.timer; do
  [ -e "\$timer" ] || continue
  systemctl enable --now "\$(basename "\$timer")"
done

systemctl stop pulse-beat pulse-worker || true
cd /opt/Pulse/backend
# Everything below runs from here so that Settings finds ../.env itself. The
# database URL used to be read out of that file and passed to sudo as an env
# assignment, which put the password in argv — readable through ps by every
# user on this shared box, and written by sudo into the auth log each deploy.

# Snapshot the current alembic revision before migrating, so a failed deploy
# can downgrade back to exactly where it was.
PREV_REV=\$(sudo -u pulse \
  /opt/Pulse/.venv/bin/alembic current 2>/dev/null | grep -oP '^[a-f0-9]+' || echo "unknown")
echo "pre-migration alembic revision: \$PREV_REV"

# Advisory lock prevents two overlapping deploys from running migrations
# concurrently. The lock id (737868) is arbitrary but fixed; pg_try_advisory_lock
# returns false (exit 1 from psql) when another session holds it.
if ! sudo -u pulse \
  /opt/Pulse/.venv/bin/python -c "
import os, sys
from sqlalchemy import create_engine, text
from app.config import settings
e = create_engine(settings.database_url)
with e.connect() as c:
    if not c.execute(text('SELECT pg_try_advisory_lock(737868)')).scalar():
        print('ERROR: another migration is running', file=sys.stderr)
        sys.exit(1)
    import subprocess
    r = subprocess.run(
        ['/opt/Pulse/.venv/bin/alembic', 'upgrade', 'head'],
        cwd='/opt/Pulse/backend',
        env={**os.environ},
    )
    c.execute(text('SELECT pg_advisory_unlock(737868)'))
    sys.exit(r.returncode)
"; then
  # Left stopped. The new tree is already on disk, so a worker or beat started
  # here imports the new code against the schema this migration just failed
  # to bring up to it — the background half of the app writing to columns that
  # are not there yet. pulse-api and pulse-web keep the old code in memory
  # and stay up; rollback.sh puts the old tree back and starts the rest.
  echo "migration failed — pulse-worker and pulse-beat are stopped, the API is" >&2
  echo "still serving the previous code from memory" >&2
  echo "previous alembic revision was: \$PREV_REV" >&2
  echo "to roll back: ./deploy/rollback.sh (restores the previous tree and starts them)" >&2
  exit 1
fi

POST_REV=\$(sudo -u pulse \
  /opt/Pulse/.venv/bin/alembic current 2>/dev/null | grep -oP '^[a-f0-9]+' || echo "unknown")
echo "post-migration alembic revision: \$POST_REV"

# Record the deploy for traceability.
echo "$DEPLOY_COMMIT \$PREV_REV \$POST_REV $DEPLOY_TIMESTAMP" >> /opt/Pulse/.deploy-history

systemctl restart pulse-api pulse-web
systemctl start pulse-worker pulse-beat

systemctl --no-pager --lines=0 status pulse-api pulse-web pulse-worker pulse-beat \
  | grep -E 'pulse-|Active:'

for attempt in \$(seq 1 15); do
  if curl -fsS --max-time 5 http://172.18.0.1:3006/api/v1/health; then
    echo
    echo "health ok after \${attempt} attempt(s)"
    exit 0
  fi
  sleep 1
done
echo "health check never came up — journalctl -u pulse-api -n 50" >&2
echo "previous alembic revision was: \$PREV_REV" >&2
echo "to roll back: ./deploy/rollback.sh --db-only \$PREV_REV" >&2
exit 1
REMOTE_SCRIPT

echo "==> done: https://pulse.doaide.com (commit $DEPLOY_COMMIT)"
