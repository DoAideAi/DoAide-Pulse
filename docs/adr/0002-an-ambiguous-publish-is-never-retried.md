# 0002: A publish whose outcome is unknown is never retried automatically

## Context
Publishing is a POST that creates something on someone else's platform: a
Dev.to article, a toot, a Buttondown email to an entire list. When the request
was *sent* and no clear answer came back (a read timeout, a dropped connection,
a 500/502/504, or a 2xx whose body can't be read), the post may well exist.

## Decision
These failures raise `OutcomeUnknown`, and the publication goes **terminal**
with an error saying to check the platform before retrying. They aren't
retried in-process or on the publication's backoff schedule. Only failures that
provably didn't land are retried automatically: a connect error, a 429 or 503
("not processed"), or a GET of any kind.

## Consequences
- No duplicate posts and no second newsletter. This was a real bug before the
  rule (C103 M5).
- Some transient blips that would have recovered alone now need a person to
  look and press Retry. That is the cost, accepted on purpose.
- **Known gap:** a publish cut off by the Celery soft time limit is still
  retried (`SoftTimeLimitExceeded` in `publishing_service.execute`). It has the
  same ambiguity and is a candidate for the same treatment.

## Rejected
- **Retry everything with backoff:** the previous behaviour, which duplicated
  sends.
- **Check for an existing post before retrying:** not every platform can be
  asked, and a check-then-post is itself a race.

## In the code
`_is_retryable`, `_outcome_unknown`, `_unreadable_answer` and `OutcomeUnknown`
in `app/services/publishers/base.py`; the `OutcomeUnknown` branch of
`publishing_service.execute`. See `docs/ERRORS.md#publication-errors`.
