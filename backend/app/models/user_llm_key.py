"""A user's own LLM API key.

Pulse ships with a server-wide provider chain (``OPENROUTER_API_KEY`` and
friends, see :mod:`app.services.llm_router`). Those keys are the operator's,
and on free tiers they run out. A user who brings their own key gets it tried
*first* for everything Pulse writes on their behalf, with the server chain
still behind it as the fallback — so a bad or exhausted personal key degrades
to the old behaviour rather than to no AI at all.

One row per user. The key is encrypted the same way platform credentials are
(:mod:`app.services.crypto`), and only a short hint of it is kept in the clear
so the settings page can say which key is stored.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class UserLLMKey(Base, TimestampMixin):
    __tablename__ = "user_llm_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    #: One of :data:`app.services.user_llm.PROVIDERS`.
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Blank means the provider preset's default model.
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    #: The last four characters, for "…abcd" on the settings page.
    key_hint: Mapped[str] = mapped_column(String(12), default="", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<UserLLMKey user={self.user_id} provider={self.provider}>"
