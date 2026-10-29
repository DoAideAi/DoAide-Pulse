# Pulse — production deployment

Pulse runs on the shared Hetzner box `89.167.8.178` (Ubuntu 24.04, 8 GB RAM)
alongside every other DoAide product and Knol. It is **not** Docker:
`docker-compose.yml` in the repo root is local-dev only. Production is four
systemd units in front of the host's PostgreSQL and Redis, published by the
shared Caddy container.

| | |
|---|---|
| Host | `89.167.8.178` |
| SSH | `ssh -i /Users/dev/projects/keys/hetzner_deploy_ed25519 root@89.167.8.178` |
| Code | `/opt/Pulse` — synced by `deploy.sh` with rsync; also a git checkout of `main` (`.git` is excluded from the sync and never shipped) |
| Runs as | system user `pulse` (not root) |
| Public URL | `https://pulse.doaide.com` |
| Deploy | `./deploy/deploy.sh` — from a clean checkout; it refuses uncommitted changes (`--allow-dirty` ships them, recorded as `<commit>-dirty`), and refuses to start below 1 GiB free disk or 600 MiB available memory on the box (`PULSE_DEPLOY_MIN_MEM_MB`). The frontend is always built locally, never on the server. |

## Ports

Chosen to sit after the apps already on the box (GoSumo 3001/3002,
Documedic 3003/3004, HomeNex 3005, Authmatic 8000):

| Port | Service |
|---|---|
| 3006 | `pulse-api` — uvicorn, 2 workers |
| 3007 | `pulse-web` — static SPA server |

Both bind **`172.18.0.1`** (the `knol_knol` Docker bridge gateway), not
`0.0.0.0`. That address is the host as seen from inside the Caddy container, so
Caddy can reach Pulse while the public internet cannot — the box has no host
firewall, and the sibling apps' `0.0.0.0` binds are in fact reachable on the
open internet. The cost is that the units depend on Docker being up; they have
`After=docker.service` and `Restart=always`, so a Docker restart resolves
itself within `RestartSec`.

## Services

| Unit | What it does |
|---|---|
| `pulse-api` | FastAPI on 3006 |
| `pulse-web` | `deploy/static-server.mjs` serving `frontend/dist` on 3007 |
| `pulse-worker` | Celery worker — generation, publishing, metrics |
| `pulse-beat` | Celery beat — publish sweep (5 min), repo scan (1 h), metrics (6 h) |

```bash
systemctl status  pulse-api pulse-web pulse-worker pulse-beat
systemctl restart pulse-api pulse-web pulse-worker pulse-beat
journalctl -u pulse-api -f
```

All four are hardened (`ProtectSystem=strict`, `ProtectHome`,
`NoNewPrivileges`, `ReadWritePaths=/opt/Pulse`). Beat's schedule file is
pinned to `/opt/Pulse/backend/celerybeat-schedule` because its default
location — the working directory — is read-only under `ProtectSystem=strict`.

## Data stores

- **PostgreSQL 16**, the host instance on `127.0.0.1:5432`. Database `pulse`,
  owner role `pulse`. (GoSumo's Postgres on 5433 is a separate container and
  is not used here.)
- **Redis**, installed from apt for Pulse and listening on `127.0.0.1:6379`,
  DB 0 (app) / 1 (Celery broker) / 2 (results). GoSumo's containerised Redis on
  6380 is deliberately left alone — sharing it would couple Pulse's queue to
  GoSumo's container lifecycle and its `noeviction` budget.

## Frontend: built locally, never on the server

`npm run build` runs on the developer machine and `frontend/dist/` is rsynced.
The box's 8 GB are shared by every DoAide product on it; a Vite build there
competes with live traffic, and on 2026-10-29 the box ran out of memory. `frontend/dist` is gitignored, so `deploy.sh` syncs it in a
second explicit pass.

The SPA calls the API at the **relative** path `/api/v1`
(`frontend/src/lib/api.js`), which is why there is a single origin with Caddy
splitting `/api/*` to the API rather than a separate `api.pulse.doaide.com`.
A split-origin setup would need CORS plus an absolute URL baked into the build.

## Caddy

Pulse's vhost lives in the shared config at `/opt/knol/Caddyfile`
(container `knol-caddy`); the canonical copy of the block is
`deploy/Caddyfile.pulse`.

```bash
docker exec knol-caddy caddy validate --config /etc/caddy/Caddyfile
docker exec knol-caddy caddy reload   --config /etc/caddy/Caddyfile
```

> **`/opt/knol/Caddyfile` is a *file* bind-mount, so never edit it with
> `sed -i`, `vim`, or anything else that writes-then-renames.** Those replace
> the inode; the container stays pinned to the old one and silently keeps
> serving the previous config — `caddy reload` will cheerfully report success
> while changing nothing. Append with `>>` or truncate in place with `cat new >
> file`, both of which preserve the inode. If the inode has already been
> replaced, `docker compose -f /opt/knol/docker-compose.prod.yml up -d caddy`
> re-links it (brief blip for every site on the box).
>
> As of the initial Pulse deploy the host file and the running config are
> **byte-for-byte identical in content but on different inodes** — a Caddy
> container recreate is needed before any further Caddyfile edit will take
> effect.

To verify a vhost's routing without touching the live proxy, run a throwaway
Caddy on the same network with just that block bound to a spare port:

```bash
{ echo ":8099 {"; sed -n '/^pulse.doaide.com {/,/^}/p' /opt/knol/Caddyfile | tail -n +2; } > /tmp/ht/Caddyfile
docker run --rm -d --name pulse-caddy-test --network knol_knol \
  -p 127.0.0.1:8099:8099 -v /tmp/ht/Caddyfile:/etc/caddy/Caddyfile:ro caddy:2-alpine
curl -s http://127.0.0.1:8099/api/v1/health
docker rm -f pulse-caddy-test
```

## DNS

`pulse.doaide.com` needs an **A record → 89.167.8.178, proxy disabled (grey
cloud)** in the Cloudflare zone `doaide.com`, matching how
`documedic.doaide.com` is set up. Caddy solves the ACME HTTP-01 challenge
itself; an orange-cloud record would break issuance. Until the record exists,
Caddy retries every 60 s and logs `NXDOMAIN looking up A for
pulse.doaide.com` — it picks up the certificate on its own once DNS resolves,
with no restart needed.

## Environment

`/opt/Pulse/.env`, mode 600, owned by `pulse`; systemd reads it via
`EnvironmentFile`. Generated at deploy time and **never** in git. `JWT_SECRET`
and `TOKEN_ENCRYPTION_KEY` were generated on the box.

### Rotating `TOKEN_ENCRYPTION_KEY`

`TOKEN_ENCRYPTION_KEY` holds a **comma-separated list, newest first**: the head
key encrypts, every key in the list decrypts. Replacing the value outright is
still an outage — it makes every stored platform credential, webhook signing
secret and inbound trigger secret unreadable at once — so rotate in three steps
instead, with nothing going down in between:

1. **Prepend** the new key, keeping the old one behind it, and restart:

   ```sh
   NEW=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   # TOKEN_ENCRYPTION_KEY=<new>,<old>
   systemctl restart pulse-api pulse-worker pulse-beat
   ```

   Everything still reads; new writes go under the new key.

2. **Re-encrypt** what is already stored. The `rewrap-credentials` beat job does
   this nightly, but after a rotation run it now:

   ```sh
   cd /opt/Pulse/backend && .venv/bin/celery -A app.tasks.celery_app \
       call app.tasks.maintenance_tasks.rewrap_credentials
   ```

   It logs how many rows moved, per table, and is safe to run repeatedly.

3. **Drop the old key** — `TOKEN_ENCRYPTION_KEY=<new>` — and restart again.

Do not do step 3 before step 2: the ciphertext is the only copy of those
secrets. If it happens anyway, the fix is to put the old key back on the end of
the list and run step 2 — the sweep counts rows it cannot read and leaves them
untouched precisely so that recovery stays possible.

LLM calls go to **OpenRouter free models** (`openai/gpt-oss-20b:free`,
`openai/gpt-oss-120b:free`), using the same key Documedic uses. That key is on
OpenRouter's free tier: **50 free-model requests per day, shared across every
app using it**, after which calls return HTTP 429 and Pulse falls through its
provider chain to a static template.

### The fallback chain

`OpenRouter → Gemini → Groq → Cerebras → static template`
(`app/services/llm_router.py`). One dialect for all four, so a provider is just
a base URL, a key and a model name; a provider with a blank key is skipped
rather than attempted and failed. Whichever one serves a piece is recorded on it
(`generated_by_provider`), and `GET /api/v1/health` lists the configured chain
in the order it will be tried.

**No fallback key is set on the box yet** — `GEMINI_API_KEY` and `GROQ_API_KEY`
are present in `/opt/Pulse/.env` but empty, so the live chain is
`["openrouter"]` and a day when the shared quota is already spent is a day of
template output. Fixing that needs a key, which has to be created by hand:

```bash
# /opt/Pulse/.env, then: systemctl restart pulse-api pulse-worker pulse-beat
GEMINI_API_KEY=…    # https://aistudio.google.com/apikey
GROQ_API_KEY=…      # https://console.groq.com/keys
```

Both are free tiers with limits an order of magnitude above 50/day, and neither
is shared with the other apps on this box. Giving Pulse its own OpenRouter key
(or $10 of credit, which unlocks 1000/day) is still the better fix for the
primary provider; the fallbacks are what stop a bad afternoon from silently
degrading every generated post.

Verify what took effect:

```bash
curl -s https://pulse.doaide.com/api/v1/health | python3 -m json.tool
# → "llm_providers": ["openrouter", "gemini", "groq"]
```

## API docs

`/docs`, `/redoc` and `/openapi.json` are **404 in production**. The gate is
`ENVIRONMENT != production or DEBUG == true` (`app.main.docs_enabled`), and the
routes are removed rather than protected — an auth prompt would confirm the
schema is there, and there is nothing in it worth authenticating for.

The schema is a full inventory of every route and field, served on the same
origin as the SPA, which is what makes it worth withholding from anonymous
visitors. To read it against the live box, `DEBUG=true` in `/opt/Pulse/.env`
plus `systemctl restart pulse-api` — no Caddy edit, the vhost still routes
those paths.

## Health check

Two endpoints. **`GET /api/v1/health`** is public and is Caddy's `health_uri`;
**`GET /api/v1/health/detail`** needs a token and answers "why isn't X
working?". Both run the same two local probes, `SELECT 1` against Postgres
and a `PING` against Redis, each with a 2 s budget
(`HEALTH_CHECK_TIMEOUT_SECONDS`). The public body is just those two;
everything below is on the detail endpoint only.

**The status code is load-bearing.** A non-2xx takes this uvicorn out of
Caddy's upstream pool, and with one upstream `/api/*` then answers 502. So
exactly one dependency decides it:

| Dependency | On | Down ⇒ |
|---|---|---|
| `database` | both | **503**, `status: degraded` |
| `redis` | both | reported `unavailable`, `required: false`, warning in the journal, still 200 |

Redis used to be fatal with Celery on. It is not, because the API serves
without it: the limiter fails open and a publish whose broker handoff fails
runs inline (`content._dispatch`). Making it required turned a Redis outage,
which costs background work, into a total one, including the detail page you
need to see what broke (M6). An unexplained 502 is Postgres or the API process
itself, not Redis.

The detail endpoint adds, all `required: false`, so none can fail the probe:

| Field | Says | Not `ok` when |
|---|---|---|
| `workers` | a Celery worker answered `ping` | none answered (`unavailable`), or `disabled` with Celery off |
| `scheduler` | scheduled publications are going out | rows are well past due: `behind`, check pulse-beat |
| `queue` | tasks waiting in the broker | past `HEALTH_QUEUE_BACKLOG_WARN`: `behind`, the worker is not keeping up |
| `backups` | the newest `*.dump`'s age in `BACKUP_DIR` | older than `BACKUP_MAX_AGE_HOURS` (36) or none: `stale`; `unknown` if unreadable |
| `beat` | pulse-beat is running: its schedule file's age (`BEAT_SCHEDULE_FILE`) | older than `HEALTH_BEAT_STALE_SECONDS` (600): `stale`; no file: `unknown`; Celery off: `disabled` |

plus the LLM chain, every breaker's state (LLM, publishing, idea tool) and
which platforms are implemented. Each probe that is not `ok` also writes a
warning, so the fact is in the journal as well as on the page.

`deploy.sh` ends with `curl -fsS …/health`, so a deploy that leaves the
database unreachable fails at the last step instead of looking fine.

## Auth surface

`/auth/*` is the only part of the API reachable without a bearer token, so it is
the only part that is rate limited (`app/ratelimit.py`, slowapi).

- **Registration is closed.** `REGISTRATION_ENABLED=false` — `POST
  /auth/register` answers 403. The account is the seeded one. Opening it in
  production additionally requires `REGISTRATION_INVITE_TOKEN`; enabled without
  a token is refused rather than served open.
- **Limits** are 10/minute login, 5/hour register, 5/hour password reset,
  60/minute `/auth/me`. Counters are in **Redis DB 3** on this box
  (`RATE_LIMIT_STORAGE_URI=redis://localhost:6379/3`, set in `/opt/Pulse/.env`),
  so the numbers are exact. Left blank they live in process memory, which with
  `--workers 2` means each worker keeps its own and the real budget is double —
  and, because a caller's consecutive requests land on either worker, the limit
  is not observable from outside. Redis being unreachable degrades to allowing
  requests (`swallow_errors`), not to blocking them; the health check catches the
  outage separately.
- **The client address comes from Caddy**, which appends the peer it saw to
  `X-Forwarded-For`. Pulse reads the **rightmost** entry, so a caller cannot
  prepend a value and reset its own budget. `RATE_LIMIT_TRUST_FORWARDED_FOR=false`
  falls back to `request.client.host`, which behind this proxy is one bucket for
  the entire internet — only correct if the app is ever exposed directly.

### Password reset

`POST /auth/password-reset` (always 202, whatever the address) emails a
single-use link; `POST /auth/password-reset/confirm` spends it. Only a SHA-256
hash of the token is stored, the TTL is 60 minutes, and requesting a new link
invalidates the one before it.

**No SMTP is configured on the box**, so the link is written to the log instead
of sent — which is a workable way to reset your own password on a single-user
install:

```bash
journalctl -u pulse-api --since '2 min ago' | grep reset-password
```

To send it properly, set `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` in
`/opt/Pulse/.env` (Gmail wants an app password) and restart `pulse-api`.

Two things this flow does **not** do:

- **It does not log anyone out.** Pulse's JWTs are stateless with no revocation
  list, so tokens issued before a reset keep working until they expire —
  `ACCESS_TOKEN_EXPIRE_MINUTES`, 24 h by default. Resetting a password because
  a token leaked needs a `JWT_SECRET` rotation, which invalidates every session.
- **There is no frontend page for it yet.** The link points at
  `$FRONTEND_URL/reset-password?token=…` and the SPA has no such route, so the
  token has to be posted to the confirm endpoint by hand for now:

  ```bash
  curl -X POST https://pulse.doaide.com/api/v1/auth/password-reset/confirm \
    -H 'Content-Type: application/json' \
    -d '{"token":"…","new_password":"…"}'
  ```

## Migrations

```bash
cd /opt/Pulse/backend
sudo -u pulse env $(grep -E '^DATABASE_URL=' /opt/Pulse/.env | xargs) \
  /opt/Pulse/.venv/bin/alembic upgrade head
```

`deploy.sh` stops the worker and beat before migrating and starts them after.

## What `deploy.sh` does, in order

Every step before 6 refuses with the box exactly as it was.

1. **A clean checkout.** Uncommitted or untracked changes stop it
   (`--allow-dirty` ships them, recorded as `<commit>-dirty`).
2. **The frontend build is this commit's.** `npm run build` stamps
   `frontend/dist/.build-commit` (package.json's `postbuild`); a build with no
   stamp, or whose `frontend/` differs from HEAD's, is refused. That is what
   stops `--no-build` shipping an old UI in front of new code. `pulse-web` never
   serves dot-files, so the stamp does not publish the production commit.
3. **Room on the box.** At least 1 GiB free on `/opt/Pulse`
   (`PULSE_DEPLOY_MIN_FREE_MB`) and 600 MiB available memory
   (`PULSE_DEPLOY_MIN_MEM_MB`). Then the deploy takes `/opt/Pulse/.deploy-lock`
   (an atomic `mkdir`, released on any exit), so two deploys never sync over
   each other. A held lock is refused with its owner (commit, user@host, start
   time); if that deploy is dead, `rm -rf /opt/Pulse/.deploy-lock` on the box.
4. **A backup.** `systemctl start pulse-backup.service`: a verified database
   dump and uploads archive from minutes before anything changes. A failed
   backup stops the deploy.
5. **Dependencies, before the code.** `backend/requirements.txt` and
   `backend/constraints.txt` go up together and are installed. requirements pins
   what Pulse imports, and constraints pins everything under it, so CI and the
   box resolve one set (see constraints.txt's header to regenerate it). Skipped
   when the pair hashes to `/opt/Pulse/.venv/.requirements.sha256`, the stamp of
   the last install. A pip failure stops the deploy.
6. **Code.** `rsync --delete --exclude-from deploy/rsync-excludes`, then
   `frontend/dist`. The exclude list is shared with `rollback.sh` and is the
   list of what survives `--delete`: `.env`, the venv, `backend/uploads/`,
   `.deploy-history`, the beat schedule. Add to it, never to an inline copy.
7. **Units.** Every file in `deploy/systemd` is installed into
   `/etc/systemd/system` if it differs; `daemon-reload` runs only then, and
   every timer is enabled.
8. **Migrate** under advisory lock 737868, with worker and beat stopped. If it
   fails they **stay stopped** (they would import the new code against the old
   schema), the API keeps serving the previous code from memory, and the
   message points at `rollback.sh`.
9. **Restart** api and web, start worker and beat, and poll `/health`.

## Seeding

```bash
cd /opt/Pulse/backend
sudo -u pulse env $(grep -vE '^#|^$' /opt/Pulse/.env | xargs) \
  /opt/Pulse/.venv/bin/python -m app.seed
```

Idempotent, keyed on `SEED_EMAIL`. The seed address must be a **routable**
domain: `EmailStr` rejects special-use TLDs, so the old `dev@pulse.local`
default seeded fine and then 500'd `/api/v1/auth/me` on response validation.

## Rollback

Use `rollback.sh`, from the developer machine — not `git checkout` and
`deploy.sh`:

```bash
./deploy/rollback.sh              # to HEAD~1
./deploy/rollback.sh <good-sha>   # to a specific commit
./deploy/rollback.sh --db-only <alembic-rev>   # schema only
```

The difference matters when the commit being undone added a migration. Only
the newer code knows how to undo it, so `rollback.sh` downgrades the database
to the old commit's head *before* syncing the old tree; `deploy.sh` at the old
commit would sync first and its `alembic upgrade head` could not find the
revision the database is at. It also installs the old commit's requirements
and rewrites the pip stamp to match, so the next forward deploy reinstalls
rather than skipping pip on a stale match.

`deploy.sh` takes a database dump itself before it changes anything — it
starts `pulse-backup.service` and stops if the dump fails — so a migration
always has a dump from minutes before it. For a code snapshot as well, before
anything risky:

```bash
ssh … 'tar czf /opt/backups/pulse-code-$(date +%s).tar.gz -C /opt Pulse'
ssh … 'sudo -u postgres pg_dump pulse | gzip > /opt/backups/pulse-db-$(date +%s).sql.gz'
```

## Backups

`pulse-backup.timer` runs `deploy/backup.sh` at 03:30 UTC. It writes a
verified `pg_dump --format=custom` into `/var/backups/pulse`, beside it an
`uploads-<stamp>.tar.gz` of `backend/uploads` (the cover and inline images,
which the dump does not contain and no deploy syncs). Every deploy takes one
too. It keeps every dump from the last 48 hours (`PULSE_BACKUP_RECENT_HOURS`),
so any recent deploy's backup is there to roll back to; then the newest of each
day to 14 days (`PULSE_BACKUP_RETENTION_DAYS`); then the newest of each week
for 8 weeks more (`PULSE_BACKUP_WEEKS`), so a mistake noticed a month late still
has a copy from before it. One a day rather than every dump: a day of deploys
kept a dump and a full uploads archive per deploy for two weeks, on the disk
every product shares. An archive is kept exactly as long as its dump.
Restoring the database without the images brings back every image URL as
a 404; unpack the archive of the same stamp into `/opt/Pulse/backend/uploads`
(`tar -xzf uploads-<stamp>.tar.gz -C /opt/Pulse/backend/uploads`, then
`chown -R pulse:pulse` it). The snapshot above is still worth taking before a risky
deploy — it is a point-in-time copy you chose; this is the one that exists when
nobody chose anything.

Deleting a piece is a real `DELETE` (`routers.content.delete_content` — archive
is the reversible option), so these dumps are the only way back from a mistaken
one.

```bash
# Did last night run?
ssh … 'systemctl status pulse-backup; ls -la /var/backups/pulse'
ssh … 'journalctl -u pulse-backup --since "2 days ago"'

# Take one now.
ssh … 'systemctl start pulse-backup'
```

Turning it on. `deploy.sh` installs both units into `/etc/systemd/system` and
enables every timer it installs (`systemctl enable --now`, idempotent) — it
used to leave that as a manual step, and on the box it was never taken, so no
dump had ever been written. The service creates `/var/backups/pulse` itself
(`ExecStartPre=+install -d …`). On a box deployed some other way, enable it by
hand, then run it once to see a dump land:

```bash
ssh … '
  systemctl enable --now pulse-backup.timer
  systemctl start pulse-backup && ls -la /var/backups/pulse'
```

**Restoring.** `--format=custom` is what makes a single table recoverable
without replaying the whole database, which is what an accidental delete
actually needs.

One thing to know before the incident rather than during it: `backup.sh` runs
`umask 077`, so the dumps are `0600` inside a `0700` directory owned by
`pulse`. That is deliberate — a dump holds every password hash and every
encrypted platform credential in the database, on a box every DoAide product shares. It
also means **`sudo -u postgres pg_restore` cannot read them.** Handing the path
straight to the `postgres` user fails with

```
pg_restore: error: could not open input file "...": Permission denied
```

which at 03:00 reads like a corrupt backup and is not one. Stage a copy the
`postgres` user owns, and keep it `0600` while it exists:

```bash
# What is in the dump. As root, which is not subject to the mode bits.
# <database> is PGDATABASE from DATABASE_URL: herald-<stamp>.dump on the box.
pg_restore --list /var/backups/pulse/<database>-<stamp>.dump

# Stage it where postgres can read it, without widening the mode.
install -d -o postgres -g postgres -m 0700 /var/backups/pulse-restore
install -o postgres -g postgres -m 0600 \
  /var/backups/pulse/<database>-<stamp>.dump /var/backups/pulse-restore/dump

# One table, into a scratch database first — never straight over prod.
sudo -u postgres createdb pulse_restore
sudo -u postgres pg_restore -d pulse_restore -t content \
  /var/backups/pulse-restore/dump

# The staged copy is a second unencrypted copy of the database. Remove it.
rm -rf /var/backups/pulse-restore
```

**Restore drill.** The above, whole rather than one table, is how you find out
the dumps are real before you need them. `--exit-on-error` is the point: without
it `pg_restore` reports a partial restore as success.

```bash
sudo -u postgres createdb pulse_restore_drill
sudo -u postgres pg_restore --exit-on-error -d pulse_restore_drill \
  /var/backups/pulse-restore/dump
# Compare against live, then drop it.
sudo -u postgres psql -d pulse_restore_drill -c 'select count(*) from content'
sudo -u postgres dropdb pulse_restore_drill
```

Last drilled 2026-08-15 against `pulse-20260815T033246Z.dump`: restored clean,
15/15 tables, 53 indexes and 14 foreign keys matching live, same Alembic head.

Two limits, stated so they are not discovered during an incident: the dumps sit
on the **same disk** as the database, so they cover operator error and
corruption but not losing the box; and copying them off-host is not set up yet.
