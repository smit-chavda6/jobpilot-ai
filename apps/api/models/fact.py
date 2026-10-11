"""ProfileFact atomic verified claims model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from apps.api.database import Base, TimestampMixin, generate_uuid

if TYPE_CHECKING:
    from apps.api.models.user import User


class ProfileFact(Base, TimestampMixin):
    """Atomic verifiable claim representing a candidate's verified experience, credential, or achievement."""

    __tablename__ = "profile_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="experience", nullable=False)
    confirmation_status: Mapped[str] = mapped_column(
        String(50), default="candidate", index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), default="resume", nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="facts")
