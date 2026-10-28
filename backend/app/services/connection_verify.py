"""Periodic re-verification of stored platform connections.

A credential that was revoked or expired on the platform side sits at
CONNECTED in Pulse until something tries to use it. On a quiet project
that can be weeks — and the first sign is a failed publication at 3am.

This module is the early-warning half. It decrypts each connection's
stored credentials, calls the same ``adapter.verify`` the settings page
uses, and stamps the result. The maintenance task in
:mod:`app.tasks.maintenance_tasks` runs it on a schedule.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.mixins import utcnow
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.services import publishers
from app.services.crypto import CredentialEncryptionError, decrypt_credentials
from app.services.errors import clip_error, redact
from app.services.publishers.base import (
    CredentialError,
    NotImplementedAdapter,
    PublishError,
)

logger = logging.getLogger(__name__)


def verify_all(db: Session) -> dict:
    """Re-verify every connection and return a summary.

    Each connection is handled independently: one dead token must not stop
    the rest from being checked.

    Each outcome is written with a conditional UPDATE that matches the
    ciphertext this sweep decrypted, and committed on its own. The verify call
    goes to the network and a sweep can take minutes, and the row loaded at the
    start was written back regardless: a user who reconnected meanwhile —
    exactly what "your token expired" invites — had the *new* credentials
    marked INVALID because the old ones were refused, and a connection removed
    meanwhile failed the single commit at the end, losing every other result.
    An outcome about credentials the row no longer holds is dropped.
    """
    # Read as plain values: the rows are not written through the ORM below, so
    # holding them would only invite reading stale state after a commit.
    connections = db.execute(
        select(
            PlatformConnection.id,
            PlatformConnection.user_id,
            PlatformConnection.platform,
            PlatformConnection.encrypted_credentials,
        ).where(PlatformConnection.status == ConnectionStatus.CONNECTED)
    ).all()

    valid = 0
    invalid = 0
    unreachable = 0

    for connection in connections:
        adapter = publishers.get_adapter(connection.platform)
        credentials: dict = {}
        values: dict

        try:
            credentials = decrypt_credentials(connection.encrypted_credentials)
            values = {
                "display_name": adapter.verify(credentials),
                "status": ConnectionStatus.CONNECTED,
                "last_verified_at": utcnow(),
                "last_error": None,
            }
            valid += 1
        except (CredentialError, CredentialEncryptionError) as exc:
            values = {
                "status": ConnectionStatus.INVALID,
                "last_verified_at": utcnow(),
                "last_error": clip_error(
                    redact(str(exc), publishers.secret_values(adapter, credentials))
                ),
            }
            invalid += 1
        except (PublishError, NotImplementedAdapter) as exc:
            values = {
                "last_error": clip_error(
                    redact(str(exc), publishers.secret_values(adapter, credentials))
                )
            }
            unreachable += 1
            # The status is left alone, so the status-change line below never
            # fires for this branch and the sweep's summary was the only trace:
            # "3 unreachable", naming none of them.
            logger.info(
                "connection %d (%s, user %d) could not be verified: %s",
                connection.id,
                connection.platform.value,
                connection.user_id,
                values["last_error"],
            )
        except Exception:
            logger.exception(
                "unexpected error verifying connection %d (%s for user %d)",
                connection.id,
                connection.platform.value,
                connection.user_id,
            )
            unreachable += 1
            continue

        written = db.execute(
            update(PlatformConnection)
            .where(
                PlatformConnection.id == connection.id,
                PlatformConnection.status == ConnectionStatus.CONNECTED,
                PlatformConnection.encrypted_credentials == connection.encrypted_credentials,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount
        db.commit()

        if not written:
            logger.info(
                "connection %d (%s, user %d) was replaced or removed while it was "
                "being verified; result discarded",
                connection.id,
                connection.platform.value,
                connection.user_id,
            )
        elif values.get("status") == ConnectionStatus.INVALID:
            logger.warning(
                "connection %d (%s, user %d) status changed: %s -> %s",
                connection.id,
                connection.platform.value,
                connection.user_id,
                ConnectionStatus.CONNECTED.value,
                ConnectionStatus.INVALID.value,
            )

    return {
        "checked": len(connections),
        "valid": valid,
        "invalid": invalid,
        "unreachable": unreachable,
    }
