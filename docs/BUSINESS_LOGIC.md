# How Pulse decides things

The non-obvious logic, in one place: how a piece is scored, when the autopilot
publishes without asking, and how a publish time is chosen. Each section states
the rule as the code applies it and points at the function that does it. The
code's own docstrings explain why each constant is what it is; this document is
the map between them.

The numbers below are checked against the code by
`backend/tests/test_business_logic_doc_matches_code.py`. If you change a
weight or a threshold, that test tells you to update this file too.

---

## 1. From a commit to a piece: the generation pipeline

```
signal (commit / release / RSS / webhook / schedule / button)
  → content_generator.generate        one LLM call: title, body, excerpt,
                                       meta, keywords, tags, confidence
      llm_router: OpenRouter → Gemini → Groq → Cerebras → deterministic template
  → content_pipeline.generate_and_route   the gates below → APPROVED or REVIEW
  → seo_autofix.apply                  deterministic fixes (meta, excerpt…)
  → publishing_service.queue           one Publication per destination
```

**The model chain never hard-fails.** Each provider is skipped for a cooldown
after repeated failures. When all of them are down, the generator returns a
deterministic template built from the project record, with `confidence = 0.0`,
which can never be published unreviewed. A trigger that would lose its event on
an outage gets a `GenerationUnavailable` instead and retries later
(`defer_on_outage`).

### When the autopilot publishes without asking

`generate_and_route` (`app/services/content_pipeline.py`) starts from the
project's **autopilot mode**:

| Mode | Behaviour |
|---|---|
| `off` | Changes are noticed; nothing is written. The default. |
| `draft` | Every piece goes to the review queue. |
| `auto` | Published unreviewed **only if every gate below passes**. |
| `full` | Skips the confidence test, but still subject to every other gate. |

A piece is a candidate for unreviewed publishing (`auto`) when the mode is
`auto` or `full`, at least one destination is connected and publishable, and
either:
- `confidence ≥ AUTOPILOT_AUTO_PUBLISH_CONFIDENCE` (**0.8**), or
- `confidence ≥ AUTOPILOT_AUTO_APPROVE_CONFIDENCE` (**0.75**) and the piece is
  not the fallback template, or
- the mode is `full`.

Then each gate can take `auto` away. Every gate is evaluated even after one
fails, so a held piece carries *all* its reasons in `content.source` for the
reviewer:

1. **Dead links:** any link in the body that `link_check` finds broken
   (`LINK_CHECK_ENABLED`).
2. **SEO score below `SEO_SCORE_THRESHOLD` (70):** waived when the piece is
   auto-approvable (above).
3. **Blocking SEO issues:** `seo.blocking_issues`, things like no meta
   description, whatever the score says.
4. **Garbled text:** runs of another script wedged mid-sentence
   (e.g. `front<CJK> end`). Six such pieces once reached Dev.to and Bluesky.
5. **Unsupported names:** product names in the body that nothing Pulse knows
   about the project supports. First the brief, keywords, commits and signal are
   checked (free). Only for a piece that fails that, the repo's README is
   fetched as a second chance (`FACTCHECK_ENABLED`, `FACTCHECK_README_ENABLED`).
   A GitHub outage leaves the first answer standing rather than failing the
   generation.
6. **Duplicate:** a near-identical title, or the same commits already written
   up, within `DEDUP_WINDOW_DAYS` (30) in the same project
   (`dedup.duplicate_of`).
7. **Quality score below `AUTOPILOT_AUTO_PUBLISH_MIN_QUALITY` (60):** see §2.

Passing every gate makes the piece `APPROVED` and queues it; failing any makes
it `REVIEW`.

> **The weak point, stated plainly.** `confidence` is the model's own
> self-assessment. When it reports none, the default is **0.5**, below both
> bars. It is the first gate on unreviewed publishing, so text in a commit
> message that talks the model into `"confidence": 1.0` gets past it. Source
> material is fenced and labelled in the prompt, but the code is explicit that
> this "is not a security boundary". The defences that do not trust the model
> are gates 1–7, all deterministic. Keep a project on `draft` until its gates
> have earned trust.

Separately, autopilot writes at most `AUTOPILOT_DAILY_CONTENT_LIMIT` (2) pieces
a day per project, and triggers at most `TRIGGER_DAILY_CONTENT_LIMIT` (3). With
`MAX_PROJECTS_PER_USER` (50), that bounds an account's automatic model calls.

---

## 2. The quality score (0–100)

`quality.report` (`app/services/quality.py`). One number, because the failure
it guards against is a piece that is mediocre in every direction at once.

```
score = 0.5 × SEO score  +  0.3 × readability points  +  0.2 × code points
```

**Readability points** come from the Flesch reading ease of the *prose*:
`prose_lines` drops code, image syntax, link targets and markdown furniture,
and keeps line breaks, so a bullet list isn't read as one 90-word sentence.

```
ease = 206.835 − 1.015 × (words / sentences) − 84.6 × (syllables / words)
```

- Full marks for an ease of **40–80**.
- Below 40: **−2 points per point of ease**. Dense prose is the real failure.
- Above 80: **−1 per point**. Too simple is only a preference.
- Under **30 words** there is no reading ease. The 0.3 weight then moves to
  code points instead of scoring the piece zero, so a tweet is not marked down
  for being short.

**Code points** come from the share of the body that is code: fenced and inline
code, measured in non-whitespace characters so indentation doesn't count.
- Full marks up to **40 %** code.
- Above that, a linear fall to 0 at 100 %.
- No penalty for having no code at all.

**An empty body scores 0** regardless of its envelope.

**Where it's used:**
- Moving a piece from draft to review requires `CONTENT_QUALITY_MIN_SCORE`
  (**50**) when `CONTENT_QUALITY_GATE_ENABLED`.
- Autopilot's unreviewed publishing requires 60 (§1, gate 7).
- The editor shows the breakdown.

Flesch-Kincaid knows sentence length and syllables, not good writing. The
thresholds are set to catch the piece nobody should have to read, not to grade
style.

---

## 3. The SEO score (0–100)

`seo.seo_score` (`app/services/seo.py`) starts at **100** and subtracts. The
focus keyword is `focus_keyword`, or the first keyword if none is set.

| Check | Deduction |
|---|---|
| No title | −15 |
| Title over 60 characters | −5 |
| No meta description | −15 |
| Meta description outside 70–155 characters | −5 |
| Meta description lacks the focus keyword | −5 |
| No keywords at all | −5 |
| Title lacks the focus keyword | −10 |
| Keyword density outside 0.5–3.0 % / outside 1.0–2.5 % | −10 / −5 |
| First paragraph lacks the focus keyword | −10 |
| No headings / no heading has the focus keyword | −10 / −5 |
| A heading level skipped (H2 → H4), per skip | −5 |
| No cover image | −5 |
| An image without alt text | −5 |
| Under 300 words | −5 |
| Slug over 60 characters / slug lacks the focus keyword | −3 / −2 |

Floored at 0. `seo.audit` reports the same checks as messages for the editor's
SEO panel. The two are kept in step deliberately, so a deduction always has a
message the user can act on. Autopilot holds back below 70 (§1, gate 2), and the
score is half of the quality score (§2).

---

## 4. Choosing a publish time

`scheduling.optimal_slots` (`app/services/scheduling.py`), used by
`POST /content/{id}/schedule` with `optimize`, and previewed by
`GET /seo/optimal-slots` and `GET /content/{id}/schedule/suggestions`.

**1. Which hours and weekdays.**
`learned_cadence.learn` reads the user's own results first. Each published post
on the platform contributes its views in the first
`VELOCITY_EARLY_WINDOW_HOURS` (24 h) after going out, bucketed by its publish
hour and weekday. A learned answer replaces the generic table only when the
platform has at least `LEARNED_CADENCE_MIN_SAMPLES` (**5**) observations *and*
every bucket it names (the winning hour, each weekday in the rota) has at least
`LEARNED_CADENCE_MIN_BUCKET` (**2**) posts of its own. The winner in each is the
bucket with the highest **median** early views, with ties going to the earlier
slot. Otherwise the table in `cadence.py` stands: published guidance per
platform, e.g. Tue–Thu at 13:00 UTC for Dev.to. Either way, the posts-per-week
ceiling (`max_per_week`) always comes from the table. Metrics show which post did
well; they can't show how much posting an audience tolerates.

**2. Not on top of something else.**
`cadence.next_slot` walks forward from now to the next allowed weekday and
hour, skipping slots the account already has taken.

**3. Canonical first.**
When the project names a canonical platform and it's in the batch, that
platform is scheduled first, and every copy goes at least
`SYNDICATION_DELAY_SECONDS` (**900**, 15 min) behind it. A copy published before
the original has a URL can't carry a `rel=canonical` link to it.
`publishing_service.queue` applies the same rule to immediate publishes.

**Times are UTC throughout.** A naive datetime from a client is read as UTC. A
time in the past, or further ahead than `SCHEDULE_MAX_HORIZON_DAYS`, is refused
rather than published on the next sweep. A mistyped year would otherwise mean
"publish immediately".

---

## 5. After queueing: retries and recovery

Each `Publication` is one piece on one platform. One success makes the piece
`published`. It's `failed` only when every platform still in play has given up.
Cancelled rows don't count either way.

| Failure | What happens |
|---|---|
| Network blip, 5xx, 429 | Retried in-process (`Adapter._request`): idempotent requests freely; a POST only when it provably never landed (connect error, 429, 503). |
| Still failing | Parked with backoff and re-tried by the beat sweep until `PUBLISH_MAX_RETRIES`. |
| Platform rate limit | Parked until the platform's own `Retry-After`. |
| 4+ failures in a row on one platform | The circuit breaker parks that platform's rows for a cooldown (`PUBLISH_BREAKER_*`). |
| **Outcome unknown** (sent, then timed out / dropped / unreadable answer) | **Terminal**, with "check before retrying". Retrying could post twice; for a newsletter, a second email to the whole list. |
| No connection for the platform | Terminal, then **re-armed automatically** once that connection exists (`recover_unblocked_publications`). |
| Credential rejected | Terminal; the connection is marked invalid, but only if it still holds the refused credentials. |

The messages for each, and what the user should do, are in
[`ERRORS.md`](ERRORS.md#publication-errors).
