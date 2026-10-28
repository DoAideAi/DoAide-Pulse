# Error reference

What Pulse's errors mean, what usually causes each one, and what to do about it.
It is organised the way you meet them: an HTTP answer from the API, or an error
written on a publication that did not go out.

The per-status vocabulary that `/docs` shows lives in
`backend/app/schemas/errors.py`; this file goes one level down, to the messages
themselves. `tests/test_error_reference_is_complete.py` fails if a status code
or publication error is added without an entry here.

## The shape, and the one thing to quote

Every error body is `{"detail": "..."}`. The only exception is FastAPI's own
422, whose `detail` is a list of `{loc, msg, type}` objects, one per invalid
field. The rejected value is stripped from those objects, so a password that
was one character short is never echoed back.

Every response, errors included, carries an **`X-Request-ID`** header. A 500
quotes it in its message. It is the key to the server log: the same id is on
every log line the request wrote, and on the lines of any background job it
queued.

```bash
journalctl -u pulse-api -u pulse-worker --since today | grep <request-id>
```

---

## HTTP errors

### 400: the request can't be carried out as asked

The body was valid JSON in the right shape, but the request asks for something
that isn't possible as stated.

| Message | Cause | What to do |
|---|---|---|
| `end is before start.` / `until is before since.` | An inverted window. It used to be an empty `200`, which read as "nothing there". | Swap the bounds. |
| `Calendar window cannot exceed 365 days.` | The calendar or idea window is too wide. | Ask for a year or less at a time. |
| `Give a scheduled_for, or set optimize …` / `… not both.` | `POST /content/{id}/schedule` needs exactly one of a time or `optimize`. | Send one. To publish now, use `POST /content/{id}/publish`. |
| `This piece is not queued anywhere yet — name the platforms …` | Scheduling a piece with no publications needs a platform list. | Pass `platforms`. |
| `Name the platforms …` | A slot suggestion with nothing queued and nothing connected. | Pass `platforms`, or connect one in Settings. |
| `If-Match …` | The optimistic-concurrency header was empty or not a quoted tag. | Send the piece's `version` as `If-Match: "4"`, or omit the header. |
| `{Platform} needs: …` / `Unknown credential field(s) …` | The connection form was missing a required credential, or had an unknown one. | Check the platform's fields in `GET /settings/platforms`. |
| `{Platform} rejected the credentials: …` | The platform said no while Pulse verified them. | Re-create the token on the platform; check its scopes. |
| `The key did not work: …` | A personal LLM key failed its test completion. | Check the key and the model name with the provider. |
| `That file is not a JPG, PNG, WebP or GIF image.` | Uploads are typed by their own leading bytes, not the `Content-Type` sent. | Upload a real image; SVG is refused on purpose. |
| `This reset link is invalid, already used, or expired.` | Reset links are single-use and expire (`PASSWORD_RESET_TOKEN_TTL_MINUTES`). | Request a new one. |
| `This project has no GitHub repo URL to scan.` | A repo scan on a project without `repo_url`. | Add the repo URL to the project. |
| `Request body contains a NUL character …` / `The URL contains a NUL character …` | PostgreSQL cannot store `\u0000`, so it's refused at the door (middleware). | Remove it. It's usually a bad paste or a binary file. |
| `Request body nested too deeply …` | JSON nested past 32 levels (middleware). | Flatten the payload. |

### 401: who are you?

| Message | Cause | What to do |
|---|---|---|
| `Token is invalid, expired, or was revoked by a password reset.` | Tokens last `ACCESS_TOKEN_EXPIRE_MINUTES` (24 h). A password reset ends every earlier one. A deactivated account's token is refused too. | Sign in again. |
| `Incorrect email or password.` | Deliberately the same answer for an unknown address, so it can't be used to find accounts. | Check both, or reset the password. |
| `Invalid or expired API key.` | A `/machine` call with a key that's wrong, revoked, rotated out, expired, or belongs to a deactivated account. The log line records which, by key prefix. | Mint or rotate a key in Settings. |
| `This trigger requires a valid signature …` | An inbound trigger with `require_signature` got no valid `X-Pulse-Signature` or `X-Hub-Signature-256`. | Sign the body with the trigger's secret, or turn the requirement off. |
| `Invalid ingest token.` | `POST /products/events` with the wrong `X-Pulse-Ingest-Token`. | Use the value of `PRODUCT_INGEST_TOKEN`. |

### 403: known, but not allowed

| Message | Cause | What to do |
|---|---|---|
| `Registration is currently closed.` | `REGISTRATION_ENABLED` is off (the default; the account comes from `python -m app.seed`). | Ask the operator. |
| `Invalid invite token.` | Registration is open but needs `REGISTRATION_INVITE_TOKEN`. | Ask the operator for the current token. |
| `This account has been deactivated.` | The password was right; the account is switched off. | Only the operator can reactivate it. |
| `This key is missing the … scope.` | The API key exists but wasn't granted that scope. | Mint a key with the scope. Scopes can't be added to an existing key. |
| `Cross-product activity is limited to …` / `Feedback is readable by this install's operator only.` | Operator-only views. The operator is anyone listed in `PRODUCT_ACTIVITY_ADMIN_EMAILS`, or, with that list empty, every account while registration is closed. | Add the email to `PRODUCT_ACTIVITY_ADMIN_EMAILS`. |

### 404: no such thing, or not yours

The two answers are deliberately identical: a 403 on another account's id would
confirm the id exists. A `?project_id=` filter naming another account's project
is a 404 on most lists (templates, triggers, API keys, tags, calendar) and
matches nothing on `GET /content`. Either way, nothing of theirs is returned.

The odd ones out:
- An inbound trigger URL that's wrong or deactivated is a 404, so a caller
  holding an old URL can't learn it once worked.
- A preview link that's unknown, revoked or expired is one 404, for the same
  reason.
- A piece **deleted while it was being translated** answers `This piece was
  deleted while it was being translated.`; nothing was saved.

### 409: the resource is in a state that makes this meaningless

Retrying won't help until the state changes.

| Message | Cause | What to do |
|---|---|---|
| `This piece is archived …` | Archived pieces don't go out, and can't be approved, rescheduled or retried. | `PATCH` its status out of `archived` first. |
| `This piece is live on the platforms …` | A published piece can only move to `archived`. | Archive it, or unpublish it on the platform. |
| `This piece is already published. Editing it here would not change what is live …` | Published pieces are locked. | Use the Headline panel (`POST /content/{id}/headlines/apply`) to change a live title. Body edits must be made on the platform. |
| `Already published — retrying would post it twice.` | Retry on a publication that succeeded. | Nothing to do. |
| `This piece has failed publications …` | Approving a failed piece. | Retry the failed publications, or move it back to draft. |
| `Cannot reschedule something already published or going out now …` | A row that's `publishing` is about to succeed; moving it is how a post goes out twice. | Wait for it to finish. |
| `At most N …` | Per-account ceilings: 50 projects, 100 templates, 20 webhooks; per project, 20 triggers and 20 live API keys. | Delete or revoke one first. |
| `You already have a template called …` / `An account with this email already exists. Sign in instead.` | Unique names. | Pick another, or sign in. |
| `This piece is already being translated into …` | Two translate requests for one language at once (a double-click). The first is already running and paying for the model call. | Reload in a moment. |
| `Somebody else changed this while you were editing it. Reload and try again.` | Another request wrote the piece between your load and your save. Raised for any write that loses that race. | Reload and reapply. |
| `The project's idea queue is full …` | `POST /machine/ideas` when every banked idea is too recent to prune. | Use or dismiss some ideas. |

### 412: your copy is out of date

`Somebody else has edited this piece since you loaded it (you have version X,
it is now Y).` You sent `If-Match` with an old version. Reload, reapply your
change, and save with the new version.

### 413: too big

`Request body too large (limit is N KB)` comes from middleware: 1 MB for JSON
and 10 MB for uploads. It counts chunked bodies as they arrive, so leaving out
`Content-Length` doesn't get around it. `File too large (max N MB)` and the
inbound trigger's `Payload larger than N KB` are the route-level versions.

### 422: the body didn't validate

FastAPI's 422 lists each invalid field. A 422 raised by a route carries one
sentence instead. The common route-level ones:

- `Still needs a value for …`: a template's required variable is empty.
  `POST /templates/{id}/preview` renders anyway and lists what's missing.
- `This template renders more than a piece can hold …`: placeholders can
  repeat, so a template can expand past the title or body limit.
- `These fields cannot be null: …`: in a PATCH, omit a field to keep it; send
  `""` or `[]` to clear it.
- `That passage is not in the saved draft.`: the passage edit works on the saved
  text, so save first.
- `Unknown platform: …`: the message lists the valid ones.

### 429: slow down

The rate-limit answer is `Too many requests — slow down and try again shortly.`
with `Retry-After` and `X-RateLimit-*` headers. Limits are counted per IP for
public and sign-in routes, per account for AI and outbound requests, and per key
for `/machine`. Every limit is a `RATE_LIMIT_*` setting (see `.env.example`).

Two route-level 429s:
- `Too many failed sign-ins for this account …`: 20 failed sign-ins an hour per
  address, from any IP (`RATE_LIMIT_LOGIN_FAILURES_PER_ACCOUNT`). Successful
  sign-ins don't count, and a completed **password reset lifts it**.
- `GitHub's rate limit has been reached.`: the shared `GITHUB_TOKEN` (or the
  60/hour unauthenticated budget) is spent.

### 500: Pulse failed

`Something went wrong on our end … quote request id …`. The body never says
more. The server log has the traceback on a line naming the method, the path
(credential segments redacted) and the user id; find it by the request id.

Operator-only 500s that do say more:
- `Could not encrypt … Check the server's encryption configuration.`:
  `TOKEN_ENCRYPTION_KEY` is missing or invalid. Production refuses to start
  without a valid one; this is the development fallback.

### 501, 502, 503: something Pulse depends on

| Status | Message | Cause | What to do |
|---|---|---|---|
| 501 | `{Platform} publishing is not available yet.` | A scaffolded adapter (LinkedIn, Twitter/X). | See the README's Platform support table. |
| 502 | `{Platform} is not responding — the credentials may be fine …` | The platform failed while Pulse verified a connection. | Try again later. The credentials weren't judged. |
| 502 | `Could not reach GitHub to scan this repository.` | GitHub didn't answer. | Check the repo URL; try again. |
| 503 | `The database is unavailable for a moment, so nothing was saved.` | PostgreSQL unreachable, or every pooled connection busy for `DB_POOL_TIMEOUT_SECONDS`. Sent with `Retry-After: 5`. | Retry. If it persists, check `GET /api/v1/health`. |
| 503 | `No provider could translate …` / `AI generation is temporarily unavailable …` | Every LLM provider in the chain failed or returned nothing usable. A failed re-translation **keeps the previous translation**. | Retry shortly. Configure fallback providers (`GEMINI_API_KEY`, `GROQ_API_KEY`) so one spent quota isn't an outage. |
| 503 | `Product event ingest is not enabled …` | `PRODUCT_INGEST_TOKEN` is unset. | Set it on the server and in the reporting product. |
| 503 | (health) | `GET /api/v1/health` answers 503 when a required dependency (database, Redis) is down. Caddy uses it to take the API out of rotation. | See `deploy/DEPLOYMENT.md`. |

---

## Publication errors

These never come back from an HTTP call. They're written on the publication row
and shown in the editor's **Publications** panel. Whether Pulse tries again on
its own depends on the error.

| Error on the publication | Retried automatically? | What to do |
|---|---|---|
| `No live {platform} connection — add one in Settings.` | **Yes, once you connect.** A beat sweep (`recover_unblocked_publications`) re-arms these rows as soon as the named connection is live. | Connect the platform in Settings. |
| `{Platform} rejected …` (a credential error) | No. The connection is marked invalid too, and only if it still holds the credentials that were refused. A reconnect made meanwhile is left alone. | Reconnect with a fresh token, then press **Retry**. |
| `… may already have gone out. Check {Platform} before retrying.` / `… has probably gone out …` | **No, on purpose.** The request reached the platform and then timed out, dropped, or answered unreadably. Retrying could post twice, or send a newsletter to the whole list again. | Look on the platform. If it isn't there, press **Retry**. |
| `Paused: recent publishes to this platform have been failing …` | Yes, after the circuit breaker's cooldown (`PUBLISH_BREAKER_*`). | Usually nothing. A platform outage is the common cause. |
| `Publishing timed out — the platform took too long to answer` | Yes, on the retry budget (`PUBLISH_MAX_RETRIES`), with backoff. | Nothing, unless it keeps happening. |
| A rate-limit message from the platform | Yes, parked until the platform's own `Retry-After`. | Nothing. |
| Any other platform error | Yes, with backoff, until `PUBLISH_MAX_RETRIES` is spent. Then it's terminal and the piece shows `failed`. | Read the error. Press **Retry** once the cause is fixed. |
| `This piece was archived before it went out.` | No: archiving cancels what was queued. | Un-archive and publish again. |
| `The piece was moved back before it went out.` | No: moving a piece back to draft or review withdraws it. | Approve or publish it again. |
| `The account was deactivated before this went out.` | No. | Only the operator can reactivate the account. |

Cancelling a schedule (`DELETE /content/{id}/schedule`, the editor's
**Cancel schedule**) marks rows `cancelled` without an error. Publishing again
re-arms them.
