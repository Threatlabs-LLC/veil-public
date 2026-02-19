from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDMixin


class DetectionRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "detection_rules"

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(20), default="regex")
    pattern: Mapped[str | None] = mapped_column(Text)  # regex pattern
    word_list: Mapped[str | None] = mapped_column(Text)  # JSON array for SQLite compat
    priority: Mapped[int] = mapped_column(Integer, default=100)
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_matches: Mapped[str | None] = mapped_column(Text)  # JSON array
