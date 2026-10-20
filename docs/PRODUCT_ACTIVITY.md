# Cross-product activity (`/products`)

The Products page shows, per DoAide product, Umami traffic and the signups,
logins and key actions the product reports. Code: `backend/app/services/product_catalog.py`
(product list and key actions), `product_activity.py`, `umami.py`.

## Server configuration (`/opt/Pulse/.env`)

| Var | Purpose |
|---|---|
| `UMAMI_USERNAME` / `UMAMI_PASSWORD` | An Umami login (a view-only user is enough). Or `UMAMI_API_TOKEN`. |
| `UMAMI_WEBSITE_IDS` | `key=id,...` for sites Umami can't match by domain (Prospect has no tracker in its HTML yet). |
| `PRODUCT_INGEST_TOKEN` | Shared secret for `POST /api/v1/products/events`. Blank = endpoint closed. |
| `PRODUCT_ACTIVITY_ADMIN_EMAILS` | Who may open the page. Required if registration is open. |

Then `alembic upgrade head` (adds `product_events`).

## Reporting events from a product

Either option counts toward the same names (see `key_actions` in the catalog):

1. **Umami custom event** from the browser: `umami.track("gst_calculation")`, `umami.track("signup")`.
2. **Server-to-server** (needed for the signup/login feed):

```bash
curl -X POST https://pulse.doaide.com/api/v1/products/events \
  -H "X-Pulse-Ingest-Token: $PULSE_INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"events":[{"product":"gst","kind":"signup","actor":"user@example.com"},
                 {"product":"prospect","kind":"action","name":"email_sent"}]}'
```

`product` is a catalog key: `gst`, `prospect`, `autoapply`, `realty`, `n409`,
`herald`, `insurekit`, `taxfile`. `kind` is `signup`, `login` or `action`
(`action` needs a `name`). `actor` is masked (`u***@example.com`) before it is
stored. Up to 100 events per request; fire-and-forget, never block a user on it.
