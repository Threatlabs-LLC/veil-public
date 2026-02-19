from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin, UUIDMixin


class MappingSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "mapping_sessions"

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"))
    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # JSON string: {"PERSON": 3, "EMAIL": 1, ...} — next counter per entity type
    entity_counter: Mapped[str] = mapped_column(Text, default="{}")

    conversation = relationship("Conversation", back_populates="mapping_session")
    entities = relationship("Entity", back_populates="session", cascade="all, delete-orphan")


class Entity(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entities"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mapping_sessions.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_subtype: Mapped[str | None] = mapped_column(String(50))
    original_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    placeholder: Mapped[str] = mapped_column(String(100), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(30), default="regex")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    context_snippet: Mapped[str | None] = mapped_column(Text)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)

    session = relationship("MappingSession", back_populates="entities")

    __table_args__ = (
        UniqueConstraint(
            "session_id", "entity_type", "normalized_value",
            name="uq_entity_session_type_norm",
        ),
    )
