# 0003: Single-tenant by design, with an "operator" for install-wide things

## Context
Pulse ships as one person's install. The account comes from
`python -m app.seed`, and registration is closed by default. But accounts are
real rows, every query is owner-scoped, and registration can be opened. Some
data has no owner by nature: LLM token usage, widget sign-ups not tied to a
project, cross-product dashboards, in-app feedback.

## Decision
Everything with an owner is filtered to the caller. A sweep test checks every
endpoint against another account's ids. Things that belong to the install go
to the **operator**: `accounts.is_operator` is true for an email in
`PRODUCT_ACTIVITY_ADMIN_EMAILS`, or, with that list empty and registration
closed, for the install's first account — the one `app.seed` made.

## Consequences
- On the shipped single-user install, the operator rule is invisible.
- **Closing registration again promotes no one.** It used to make *every*
  account the operator ("closed" was read as "single-user"), so inviting a few
  people and then closing sign-ups handed each of them the install's feedback,
  dashboards and unattributed newsletter addresses. Deactivating the first
  account does not pass the role on either; set the admin list for that.
- **Opening registration without setting `PRODUCT_ACTIVITY_ADMIN_EMAILS` means
  no one is the operator.** Widget sign-ups then show for nobody, and
  operator-only pages answer 403. This is deliberate: it fails closed.
- LLM usage on `/metrics` is install-wide for every caller; the table has no
  owner column. That's documented in `ops_metrics`, not hidden.
- Per-account ceilings (50 projects, 20 webhooks, rate limits on creation and
  AI) exist because a second account shares the install's AI quota.

## Rejected
- **Full multi-tenancy with organisations:** no user needed it, and every
  query would carry another dimension.

## In the code
`app/services/accounts.py` (`is_operator`), `require_product_admin`,
`analytics_service.subscriber_growth`,
`tests/test_every_endpoint_is_scoped_to_its_caller.py`.
