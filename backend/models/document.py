from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDMixin


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    organization_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer)
    entities_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    was_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    error_message: Mapped[str | None] = mapped_column(Text)
