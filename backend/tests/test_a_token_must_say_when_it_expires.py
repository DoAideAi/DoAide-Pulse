"""An access token without an expiry, issue time or subject is refused.

``jwt.decode`` checks ``exp`` only when the token carries one. Pulse always
writes it, but the decoder never insisted: anything else signed with
``JWT_SECRET`` — an operator reusing one secret across products is enough —
that said ``"type": "access"`` and left ``exp`` out was a session that never
ended, and one without ``iat`` was out of reach of ``tokens_valid_from`` (the
switch sign-out and password resets use) whenever no cutoff was set yet.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.security import create_access_token, decode_access_token_claims

V1 = "/api/v1"


def _token(**claims):
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _full(user_id):
    now = datetime.now(UTC)
    return {
        "sub": str(user_id), "type": "access",
        "iat": now.timestamp(), "exp": now + timedelta(hours=1),
    }


@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_a_token_missing_a_required_claim_is_refused(client, user, missing):
    claims = _full(user.id)
    del claims[missing]
    token = _token(**claims)

    assert decode_access_token_claims(token) is None
    resp = client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_a_complete_token_still_works(client, user):
    token = _token(**_full(user.id))
    resp = client.get(f"{V1}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_the_tokens_pulse_mints_carry_all_three():
    claims = decode_access_token_claims(create_access_token(7))
    assert claims and {"exp", "iat", "sub"} <= set(claims)
