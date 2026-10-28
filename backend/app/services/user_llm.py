"""A user's own LLM key: presets, storage, verification, and the chain entry.

Every preset here speaks OpenAI's ``/chat/completions`` — the same dialect the
server chain in :mod:`app.services.llm_router` already uses — so a personal key
becomes one more :class:`~app.services.llm_router.Provider` placed at the
front of the chain. Nothing downstream needs to know whose key served a call.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user_llm_key import UserLLMKey
from app.services import crypto

if TYPE_CHECKING:
    # Annotation only: importing it at runtime here would make the two
    # modules circular — see build_provider.
    from app.services.llm_router import Provider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Preset:
    label: str
    base_url: str
    default_model: str
    #: Where the user goes to make a key. Shown as a link on the settings page.
    key_url: str
    #: What a key from this provider usually starts with — a hint for the form,
    #: never a validation rule (formats change and self-hosted proxies differ).
    key_prefix: str = ""


def _presets() -> dict[str, Preset]:
    # A function, not a constant: the defaults come from settings so a model
    # swap in ``.env`` reaches personal keys too.
    return {
        "gemini": Preset(
            label="Google Gemini",
            base_url=settings.gemini_base_url,
            default_model=settings.gemini_model,
            key_url="https://aistudio.google.com/app/apikey",
            key_prefix="AIza",
        ),
        "openrouter": Preset(
            label="OpenRouter",
            base_url=settings.openrouter_base_url,
            default_model=settings.openrouter_model,
            key_url="https://openrouter.ai/settings/keys",
            key_prefix="sk-or-",
        ),
        "openai": Preset(
            label="OpenAI",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            key_url="https://platform.openai.com/api-keys",
            key_prefix="sk-",
        ),
        "groq": Preset(
            label="Groq",
            base_url=settings.groq_base_url,
            default_model=settings.groq_model,
            key_url="https://console.groq.com/keys",
            key_prefix="gsk_",
        ),
        "cerebras": Preset(
            label="Cerebras",
            base_url=settings.cerebras_base_url,
            default_model=settings.cerebras_model,
            key_url="https://cloud.cerebras.ai/platform/",
            key_prefix="csk-",
        ),
    }


def presets() -> dict[str, Preset]:
    """Every provider a user can bring a key for, Gemini first."""
    return _presets()


PROVIDERS = ("gemini", "openrouter", "openai", "groq", "cerebras")


def hint(api_key: str) -> str:
    """The last four characters, or nothing for a key too short to spare them."""
    key = api_key.strip()
    return key[-4:] if len(key) >= 12 else ""


def provider_name(user_id: int, provider: str) -> str:
    """The chain name for a personal key.

    Carries the user id because the circuit breaker is keyed by name: two users
    with Gemini keys must not trip each other's breaker. Fits
    ``llm_usage.PROVIDER_MAX_LENGTH``.
    """
    return f"own:{user_id}:{provider}"[:40]


def build_provider(
    provider: str, api_key: str, model: str = "", *, user_id: int = 0
) -> Provider:
    """A chain :class:`Provider` for this key. Imported lazily — see below."""
    # llm_router imports this module lazily too; importing it at the top here
    # would make the two modules circular.
    from app.services.llm_router import Provider

    preset = _presets()[provider]
    extra = {}
    if provider == "openrouter":
        extra = {
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_title,
        }
    return Provider(
        name=provider_name(user_id, provider),
        api_key=api_key.strip(),
        base_url=preset.base_url,
        model=(model or "").strip() or preset.default_model,
        extra_headers=extra,
    )


def get_row(db: Session, user_id: int) -> UserLLMKey | None:
    return db.scalar(select(UserLLMKey).where(UserLLMKey.user_id == user_id))


def provider_for(db: Session, user_id: int) -> Provider | None:
    """The user's key as a chain provider, or ``None`` when they have none.

    A key that cannot be decrypted is logged and treated as absent: the server
    chain behind it still works, and failing every generation over a rotated
    encryption key would be the wrong trade.
    """
    row = get_row(db, user_id)
    if row is None or not row.encrypted_key or row.provider not in _presets():
        return None
    try:
        api_key = crypto.decrypt_credentials(row.encrypted_key).get("api_key", "")
    except crypto.CredentialEncryptionError as exc:
        logger.warning("personal LLM key for user %s unreadable: %s", user_id, exc)
        return None
    if not api_key:
        return None
    return build_provider(row.provider, api_key, row.model, user_id=user_id)


def session_factory() -> Session:
    """A fresh session. A function so tests can point it at their database."""
    from app.database import SessionLocal

    return SessionLocal()


def load_for(user_id: int) -> Provider | None:
    """:func:`provider_for` on a session of its own, for the LLM chain.

    The chain is reached from code that has no session to lend — a Celery task
    halfway through generation, a helper three calls deep — so it opens one.
    """
    with session_factory() as db:
        return provider_for(db, user_id)


def verify(provider: str, api_key: str, model: str = "") -> str:
    """Make one tiny completion with the key. Returns the model that answered.

    Raises :class:`app.services.llm_router.LLMError` with the provider's own
    reason when it refuses — the settings page shows that to the user.
    """
    from app.services import llm_router

    candidate = build_provider(provider, api_key, model)
    llm_router._call(
        candidate,
        [{"role": "user", "content": "Reply with the single word: ok"}],
        model=candidate.model,
        temperature=0.0,
        max_tokens=16,
        timeout=20.0,
    )
    return candidate.model
