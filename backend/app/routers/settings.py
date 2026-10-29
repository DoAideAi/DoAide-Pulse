"""Platform connections — the settings page.

Credentials go in and never come out. Every response here is built from
:func:`app.services.publishers.capabilities` plus the connection's status,
never from the stored blob.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.mixins import utcnow
from app.models.platform_connection import ConnectionStatus, PlatformConnection
from app.models.publication import Platform
from app.models.user import User
from app.models.user_llm_key import UserLLMKey
from app.ratelimit import account_key, limiter
from app.schemas.errors import AUTHENTICATED, OWNED, errors
from app.schemas.settings import (
    ConnectionCreate,
    ConnectionOut,
    LLMKeyIn,
    LLMKeyOut,
    LLMKeySettings,
    LLMProviderOption,
    PlatformCapability,
)
from app.services import llm_router, publishers, user_llm
from app.services.crypto import CredentialEncryptionError, encrypt_credentials
from app.services.errors import clip_error, redact
from app.services.publishers.base import (
    CredentialError,
    NotImplementedAdapter,
    PublishError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "/platforms",
    response_model=list[PlatformCapability],
    summary="Every publishing platform and its connection state",
    responses=errors(*AUTHENTICATED),
)
def list_platforms(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[PlatformCapability]:
    """Every platform, what it needs, and whether this user has connected it."""
    connections = {
        c.platform: c
        for c in db.scalars(
            select(PlatformConnection).where(PlatformConnection.user_id == user.id)
        )
    }
    return [
        PlatformCapability(
            **capability,
            connection=(
                ConnectionOut.model_validate(connections[Platform(capability["platform"])])
                if Platform(capability["platform"]) in connections
                else None
            ),
        )
        for capability in publishers.capabilities()
    ]


@router.put(
    "/connections",
    response_model=ConnectionOut,
    summary="Connect a platform, or replace its credentials",
    responses=errors(
        status.HTTP_400_BAD_REQUEST,
        *AUTHENTICATED,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_501_NOT_IMPLEMENTED,
        status.HTTP_502_BAD_GATEWAY,
    ),
)
@limiter.limit(settings.rate_limit_outbound_probe, key_func=account_key)
def upsert_connection(
    payload: ConnectionCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConnectionOut:
    """Save credentials for a platform, verifying them first.

    Verification is not optional. Storing an unverified token means the user
    finds out it is wrong when a scheduled post fails overnight, which is the
    worst possible moment.

    Which is also why this carries the outbound-probe budget: verification is a
    synchronous request to the platform, made from Pulse's address on the
    caller's say-so, and the credentials it verifies are the ones in the body
    rather than anything already stored — so it is the one endpoint here that
    answers "is this token good?" for a token the caller just made up. Left
    unlimited it is a credential-stuffing oracle against the platforms, run
    from Pulse. On the Git adapter it is worse than that: ``GitAdapter._token``
    falls back to the install's shared ``GITHUB_TOKEN`` when the connection
    carries none, so an unlimited loop here spends the same single budget that
    ``rate_limit_repo_scan`` exists to protect, and answers 403 to every account
    on the install once it is gone.
    """
    adapter = publishers.get_adapter(payload.platform)

    expected = {f.key for f in adapter.credential_fields}
    required = {f.key for f in adapter.credential_fields if f.required}

    # Every key the caller sent, whatever its value. Deriving this from the
    # non-blank entries — which is what it used to do — meant a misspelled field
    # whose value happened to be blank or whitespace was not "supplied", so it
    # was not unknown either: the check that exists to catch a typo skipped
    # exactly the payloads a typo produces. The key was then encrypted and
    # stored with the rest, and the connection looked correctly configured
    # while the real field sat empty.
    unknown = set(payload.credentials) - expected
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown credential field(s) for {adapter.display_name}: "
            f"{', '.join(sorted(unknown))}",
        )

    # Blank means unset, and it means that all the way down rather than only
    # here. A whitespace value stored for an optional field is worse than a
    # missing one: `credentials.get("branch") or "main"` returns the whitespace,
    # because " " is true.
    credentials = {
        key: str(value).strip()
        for key, value in payload.credentials.items()
        if str(value).strip()
    }

    missing = required - set(credentials)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{adapter.display_name} needs: {', '.join(sorted(missing))}",
        )
    if not credentials:
        # Only reachable for an adapter that requires nothing, where `missing`
        # is empty by definition. Storing `{}` would present as connected.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{adapter.display_name} needs at least one credential.",
        )

    try:
        display_name = adapter.verify(credentials)
    except NotImplementedAdapter as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"{adapter.display_name} publishing is not available yet. {exc}",
        ) from exc
    except CredentialError as exc:
        safe = redact(str(exc), publishers.secret_values(adapter, credentials))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{adapter.display_name} rejected the credentials: {safe}",
        ) from exc
    except PublishError as exc:
        # The platform is having a bad day — the credentials might be fine.
        safe = redact(str(exc), publishers.secret_values(adapter, credentials))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{adapter.display_name} is not responding — the credentials "
            f"may be fine but could not be verified right now. {safe}",
        ) from exc

    try:
        encrypted = encrypt_credentials(credentials)
    except CredentialEncryptionError as exc:
        logger.error("credential encryption failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not encrypt credentials for storage. "
            "Check the server's encryption configuration.",
        ) from exc

    def _existing() -> PlatformConnection | None:
        return db.scalar(
            select(PlatformConnection).where(
                PlatformConnection.user_id == user.id,
                PlatformConnection.platform == payload.platform,
            )
        )

    def _store(connection: PlatformConnection) -> None:
        connection.encrypted_credentials = encrypted
        connection.display_name = display_name
        connection.status = ConnectionStatus.CONNECTED
        connection.last_verified_at = utcnow()
        connection.last_error = None
        # The destination's language. ``ConnectionCreate`` declared and
        # validated it and nothing ever wrote it, so every destination stayed
        # English: the publish path's translation lookup read a column no
        # request could set, and "publish this one in French" was not a thing
        # a user could do. Written only when sent, so re-saving credentials
        # without it leaves the language the destination already had.
        if "language" in payload.model_fields_set:
            connection.language = payload.language
        db.commit()

    connection = _existing()
    try:
        if connection is None:
            connection = PlatformConnection(user_id=user.id, platform=payload.platform)
            db.add(connection)
        _store(connection)
    except IntegrityError:
        # A second Save pressed while the first was still in ``verify`` — a
        # network call, so the window is seconds wide. Both found no row and
        # both inserted; ``uq_connection_user_platform`` failed this one, which
        # was a 500 for credentials that had just verified. Both sets verified,
        # so the later write simply wins, as it would have one second later.
        db.rollback()
        connection = _existing()
        if connection is None:  # pragma: no cover - the conflict means it exists
            raise
        _store(connection)
    db.refresh(connection)
    logger.info(
        "user %s connected %s (display=%s)",
        user.id,
        payload.platform.value,
        display_name,
    )
    return ConnectionOut.model_validate(connection)


@router.post(
    "/connections/{platform}/verify",
    response_model=ConnectionOut,
    summary="Re-check stored credentials",
    responses=errors(*OWNED, status.HTTP_429_TOO_MANY_REQUESTS),
)
@limiter.limit(settings.rate_limit_outbound_probe, key_func=account_key)
def verify_connection(
    platform: Platform,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConnectionOut:
    """Re-check stored credentials, e.g. after a platform reports them invalid.

    Always 200 once the connection exists — the verdict is in the returned
    ``status`` and ``last_error``, not in the status code. A platform that is
    merely unreachable leaves ``status`` alone rather than marking the
    connection invalid: an outage is not proof the token is bad, and flipping it
    would make the user re-enter one that works.

    Carries the outbound-probe budget for the reason
    :func:`upsert_connection` does — one call is one synchronous request to the
    platform — minus the stuffing-oracle half, since the credentials here are
    the stored ones. What is left is still a button that turns one HTTP request
    from the caller into one from Pulse, and on the Git adapter one that can
    spend the install's shared ``GITHUB_TOKEN``.
    """
    from app.services.crypto import decrypt_credentials

    connection = db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id,
            PlatformConnection.platform == platform,
        )
    )
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{platform.value} is not connected. Add it in Settings first.",
        )

    adapter = publishers.get_adapter(platform)
    # Held so the failure arms can strip them back out of whatever the platform
    # said. ``verify`` runs against a token the user has just pasted in, and its
    # message lands in ``last_error`` — a plaintext column rendered on the
    # settings page, next to the encrypted copy of the same value. Empty when
    # decryption is what failed, which is the one case there is nothing to
    # remove. See ``publishing_service._redact_credentials`` for the same guard
    # on the publish path.
    credentials: dict = {}
    previous_status = connection.status
    connection_id = connection.id
    ciphertext = connection.encrypted_credentials
    values: dict
    try:
        credentials = decrypt_credentials(ciphertext)
        values = {
            "display_name": adapter.verify(credentials),
            "status": ConnectionStatus.CONNECTED,
            "last_verified_at": utcnow(),
            "last_error": None,
        }
    except (CredentialError, CredentialEncryptionError) as exc:
        values = {
            "status": ConnectionStatus.INVALID,
            "last_error": clip_error(
                redact(str(exc), publishers.secret_values(adapter, credentials))
            ),
        }
    except (PublishError, NotImplementedAdapter) as exc:
        # Leave the status alone: an unreachable platform is not proof the
        # credentials are bad, and flipping to INVALID would make the user
        # re-enter a working token.
        values = {
            "last_error": clip_error(
                redact(str(exc), publishers.secret_values(adapter, credentials))
            )
        }

    # Written only onto the credentials that were checked. The call above is a
    # network round-trip, and a save from another tab in the meantime had its
    # fresh credentials marked with the verdict on the old ones — INVALID, in
    # the case that matters — while a removal meanwhile was a StaleDataError
    # and a 500. Either way the row now says something this check did not see.
    db.rollback()
    written = db.execute(
        update(PlatformConnection)
        .where(
            PlatformConnection.id == connection_id,
            PlatformConnection.encrypted_credentials == ciphertext,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    ).rowcount
    db.commit()

    current = db.get(PlatformConnection, connection_id, populate_existing=True)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{platform.value} was disconnected while it was being checked.",
        )
    if not written:
        logger.info(
            "user %s verified %s, but the credentials were replaced meanwhile; "
            "result discarded",
            user.id,
            platform.value,
        )
    elif current.status != previous_status:
        logger.warning(
            "user %s connection %s status changed: %s -> %s",
            user.id,
            platform.value,
            previous_status.value,
            current.status.value,
        )
    else:
        logger.info(
            "user %s verified %s: status=%s",
            user.id,
            platform.value,
            current.status.value,
        )
    return ConnectionOut.model_validate(current)


@router.delete(
    "/connections/{platform}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect a platform",
    responses=errors(*OWNED),
)
def delete_connection(
    platform: Platform,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Forget a platform's credentials.

    A hard delete, unlike the rest of Pulse: there is nothing here worth
    keeping, and "deleted" has to mean the ciphertext is gone. Content already
    published there is untouched — this removes the ability to publish again,
    not the record of having done so.
    """
    connection = db.scalar(
        select(PlatformConnection).where(
            PlatformConnection.user_id == user.id,
            PlatformConnection.platform == platform,
        )
    )
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{platform.value} is not connected — nothing to disconnect.",
        )
    logger.warning(
        "user %s disconnected %s — every queued publication for it now fails "
        "as unconnected until it is reconnected",
        user.id,
        platform.value,
    )
    db.delete(connection)
    db.commit()


# --------------------------------------------------------------------------- #
# Personal LLM key                                                             #
# --------------------------------------------------------------------------- #


def _llm_settings(db: Session, user: User) -> LLMKeySettings:
    row = user_llm.get_row(db, user.id)
    return LLMKeySettings(
        providers=[
            LLMProviderOption(
                provider=name,
                label=preset.label,
                default_model=preset.default_model,
                key_url=preset.key_url,
                key_prefix=preset.key_prefix,
            )
            for name, preset in user_llm.presets().items()
        ],
        key=LLMKeyOut.model_validate(row) if row and row.encrypted_key else None,
    )


@router.get(
    "/llm-key",
    response_model=LLMKeySettings,
    summary="Your own LLM key: which providers are supported and what is stored",
    responses=errors(*AUTHENTICATED),
)
def get_llm_key(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> LLMKeySettings:
    """The providers a personal key can be for, and the stored one if any.

    The key itself never comes back — only its last four characters.
    """
    return _llm_settings(db, user)


@router.put(
    "/llm-key",
    response_model=LLMKeySettings,
    summary="Save your own LLM key, verifying it first",
    responses=errors(
        status.HTTP_400_BAD_REQUEST,
        *AUTHENTICATED,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
@limiter.limit(settings.rate_limit_outbound_probe, key_func=account_key)
def save_llm_key(
    payload: LLMKeyIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LLMKeySettings:
    """Check the key with one tiny completion, then store it encrypted.

    From then on everything Pulse writes for this account tries this key
    first, with the server's own providers behind it as the fallback.

    Rate-limited like platform connections, for the same reason: verifying is
    an outbound request made on the caller's say-so with a key they just typed.
    """
    try:
        user_llm.verify(payload.provider, payload.api_key, payload.model)
    except llm_router.LLMError as exc:
        safe = redact(str(exc), [payload.api_key])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The key did not work: {clip_error(safe)} Check that it was "
            "copied whole and can use the model you chose, then save it again.",
        ) from exc

    try:
        encrypted = encrypt_credentials({"api_key": payload.api_key})
    except CredentialEncryptionError as exc:
        logger.error("LLM key encryption failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not encrypt the key for storage. "
            "Check the server's encryption configuration.",
        ) from exc

    def _store(row: UserLLMKey) -> None:
        row.provider = payload.provider
        row.model = payload.model
        row.encrypted_key = encrypted
        row.key_hint = user_llm.hint(payload.api_key)
        row.last_verified_at = utcnow()
        row.last_error = None
        db.commit()

    row = user_llm.get_row(db, user.id)
    try:
        if row is None:
            row = UserLLMKey(user_id=user.id, provider=payload.provider)
            db.add(row)
        _store(row)
    except IntegrityError:
        # Two Saves inside the verifying completion both inserted; the unique
        # ``user_id`` failed this one. Same answer as ``upsert_connection``:
        # both keys verified, so the later write wins instead of a 500.
        db.rollback()
        row = user_llm.get_row(db, user.id)
        if row is None:  # pragma: no cover - the conflict means it exists
            raise
        _store(row)
    # Which provider the account's generations now bill to is the first thing
    # to know when the bill or the output changes; the key itself never is
    # logged, nor its hint.
    logger.info("LLM key saved for user %s (provider %s)", user.id, payload.provider)
    return _llm_settings(db, user)


@router.delete(
    "/llm-key",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove your own LLM key",
    responses=errors(*AUTHENTICATED),
)
def delete_llm_key(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    """Forget the key. Generation goes back to the server's providers."""
    row = user_llm.get_row(db, user.id)
    if row is not None:
        provider = row.provider
        db.delete(row)
        db.commit()
        logger.info("LLM key removed for user %s (provider %s)", user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
