# 0004: Unreviewed publishing is gated by deterministic checks

## Context
Autopilot can publish without review under the author's name. The obvious gate
is the model's own `confidence`, but that number is self-reported, and the
model reads untrusted text: commit messages, feed entries, webhook payloads.
Text that talks the model into `"confidence": 1.0` would publish itself.

## Decision
`confidence` is only the first condition. Every candidate must also pass
deterministic gates computed by Pulse, not the model: link check, SEO score and
blocking issues, a garbled-text check, a fact check of product names against
what Pulse knows about the project, a duplicate check, and a quality score
built from Flesch reading ease and code density. Any one holds the piece for
review, and all the reasons are recorded on it. The model is never asked to
grade its own output.

## Consequences
- Prompt injection can move `confidence` but not the gates. The fencing of
  source material in the prompt is acknowledged in the code as "not a security
  boundary"; the gates are the boundary.
- The gates are blunt. Flesch doesn't know good writing, and the fact check can
  hold a piece that names something real but unlisted. They're tuned to catch
  pieces nobody should read, and a held piece only costs a review.
- New projects default to autopilot `off`. `draft` is the safe step up.

## Rejected
- **An LLM reviewer ("is this good?"):** same trust problem, twice the cost,
  and non-deterministic, so it can't be tested.

## In the code
`content_pipeline.generate_and_route`, `quality.report`, `seo.seo_score`,
`factcheck`, `dedup`. Walked through in `docs/BUSINESS_LOGIC.md` §1.
