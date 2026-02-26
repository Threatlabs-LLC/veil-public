from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDMixin


class UsageStat(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_stats"

    organization_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36))
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    request_count: Mapped[int] = mapped_column(BigInteger, default=0)
    total_input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    estimated_cost_microdollars: Mapped[int] = mapped_column(BigInteger, default=0)
    entities_detected: Mapped[int] = mapped_column(BigInteger, default=0)
    entities_sanitized: Mapped[int] = mapped_column(BigInteger, default=0)
    error_count: Mapped[int] = mapped_column(BigInteger, default=0)
