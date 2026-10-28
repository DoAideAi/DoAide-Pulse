# Architecture decision records

Decisions that look wrong, or at least improvable, from inside a single file.
Each record says what was decided, what it costs, what was rejected, and where
the code that depends on it lives. Read the relevant one before "fixing"
something it describes.

| # | Decision |
|---|---|
| [0001](0001-bearer-tokens-not-cookies.md) | The API authenticates with a bearer token in a header, never a cookie |
| [0002](0002-an-ambiguous-publish-is-never-retried.md) | A publish whose outcome is unknown is never retried automatically |
| [0003](0003-single-tenant-with-an-operator.md) | Single-tenant by design; install-wide things belong to an "operator" |
| [0004](0004-deterministic-gates-over-model-judgement.md) | Unreviewed publishing is gated by deterministic checks, not by the model |
| [0005](0005-log-references-are-set-null-foreign-keys.md) | References from log-like rows are `ON DELETE SET NULL` foreign keys |
| [0006](0006-frontend-built-off-box.md) | The frontend is built off the server and shipped as files |

New records take the next number and the same headings: **Context**,
**Decision**, **Consequences**, **Rejected**, **In the code**.
