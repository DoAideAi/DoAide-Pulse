# 0001: Bearer tokens in a header, never a cookie

## Context
The SPA and the API share one origin behind Caddy. Cookie sessions are the usual
choice for a same-origin app, and they bring CSRF with them: any site can make a
browser send a cookie with a form post.

## Decision
Every authenticated request carries `Authorization: Bearer <jwt>` (or
`X-API-Key` on `/machine`). The API never sets or reads a cookie, and CORS sends
no `Access-Control-Allow-Credentials`.

## Consequences
- **No CSRF surface.** A cross-site form can't attach the header, so there's no
  CSRF middleware and none is needed. Adding any cookie-based auth, even a
  "remember me", reopens this and needs CSRF protection with it.
- The token lives in the SPA's storage, so XSS is the threat to design against.
  That's why the markdown renderer escapes everything before emitting tags, and
  why the API serves a strict CSP.
- Tokens are stateless JWTs. Revocation is a timestamp (`users.tokens_valid_from`,
  moved by a password reset) compared with the token's `iat`; there's no
  denylist.

## Rejected
- **HttpOnly session cookie:** better against XSS token theft, but it needs
  CSRF tokens on every write and a server-side session store.

## In the code
`app/deps.py` (`get_current_user`, `require_scope`), `app/security.py`, the
CORS block in `app/main.py`, `frontend/src/lib/api.js`.
