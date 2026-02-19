"""Usage tracking and metering — the billing foundation for SaaS.

Tracks every request: tokens, entities, provider, model, latency, cost.
Aggregates to daily rollups in usage_stats table.
"""

import time
from datetime import date, datetime, timezone
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.usage import UsageStat

# Approximate cost per 1M tokens (in microdollars) by model
# 1 USD = 1,000,000 microdollars
MODEL_COSTS: dict[str, tuple[int, int]] = {
    # (input_cost_per_1M, output_cost_per_1M) in microdollars
    "gpt-4o-mini": (150_000, 600_000),
    "gpt-4o": (2_500_000, 10_000_000),
    "gpt-4-turbo": (10_000_000, 30_000_000),
    "o3-mini": (1_100_000, 4_400_000),
    "claude-sonnet-4-6": (3_000_000, 15_000_000),
    "claude-haiku-4-5-20251001": (800_000, 4_000_000),
    "claude-opus-4-6": (15_000_000, 75_000_000),
}

DEFAULT_COST = (1_000_000, 3_000_000)  # $1/$3 per 1M tokens default


@dataclass
class RequestMetrics:
    """Metrics for a single chat request."""

    org_id: str
    user_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    entities_detected: int = 0
    entities_sanitized: int = 0
    latency_ms: int = 0
    is_error: bool = False


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> int:
    """Estimate cost in microdollars for a request."""
    input_rate, output_rate = MODEL_COSTS.get(model, DEFAULT_COST)
    input_cost = (input_tokens * input_rate) // 1_000_000
    output_cost = (output_tokens * output_rate) // 1_000_000
    return input_cost + output_cost


async def record_usage(db: AsyncSession, metrics: RequestMetrics) -> None:
    """Record usage metrics — upserts into daily aggregation row."""
    today = date.today().isoformat()
    cost = estimate_cost(metrics.model, metrics.input_tokens, metrics.output_tokens)

    # Try to find existing row for today's aggregation
    result = await db.execute(
        select(UsageStat).where(
            UsageStat.organization_id == metrics.org_id,
            UsageStat.user_id == metrics.user_id,
            UsageStat.provider == metrics.provider,
            UsageStat.model == metrics.model,
            UsageStat.period_start == today,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Increment counters
        existing.request_count += 1
        existing.total_input_tokens += metrics.input_tokens
        existing.total_output_tokens += metrics.output_tokens
        existing.total_tokens += metrics.input_tokens + metrics.output_tokens
        existing.estimated_cost_microdollars += cost
        existing.entities_detected += metrics.entities_detected
        existing.entities_sanitized += metrics.entities_sanitized
        if metrics.is_error:
            existing.error_count += 1
    else:
        # Create new daily row
        stat = UsageStat(
            organization_id=metrics.org_id,
            user_id=metrics.user_id,
            period_start=today,
            provider=metrics.provider,
            model=metrics.model,
            request_count=1,
            total_input_tokens=metrics.input_tokens,
            total_output_tokens=metrics.output_tokens,
            total_tokens=metrics.input_tokens + metrics.output_tokens,
            estimated_cost_microdollars=cost,
            entities_detected=metrics.entities_detected,
            entities_sanitized=metrics.entities_sanitized,
            error_count=1 if metrics.is_error else 0,
        )
        db.add(stat)


class UsageTracker:
    """Context manager for tracking request-level metrics."""

    def __init__(self, org_id: str, user_id: str, provider: str, model: str):
        self.metrics = RequestMetrics(
            org_id=org_id,
            user_id=user_id,
            provider=provider,
            model=model,
        )
        self._start_time: float = 0

    def start(self) -> None:
        self._start_time = time.time()

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.metrics.input_tokens += input_tokens
        self.metrics.output_tokens += output_tokens

    def record_entities(self, detected: int, sanitized: int) -> None:
        self.metrics.entities_detected += detected
        self.metrics.entities_sanitized += sanitized

    def record_error(self) -> None:
        self.metrics.is_error = True

    def finish(self) -> None:
        self.metrics.latency_ms = int((time.time() - self._start_time) * 1000)

    @property
    def cost_microdollars(self) -> int:
        return estimate_cost(
            self.metrics.model,
            self.metrics.input_tokens,
            self.metrics.output_tokens,
        )

    @property
    def cost_display(self) -> str:
        """Human-readable cost string."""
        usd = self.cost_microdollars / 1_000_000
        if usd < 0.01:
            return f"${usd:.6f}"
        return f"${usd:.4f}"
