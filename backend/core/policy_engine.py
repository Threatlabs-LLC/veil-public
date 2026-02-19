"""Policy engine — evaluates detected entities against org policies.

Determines what action to take for each detected entity:
- allow: pass through unchanged
- redact: replace with placeholder (default behavior)
- block: reject the entire request
- warn: redact but flag for review
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.detectors.base import DetectedEntity
from backend.models.policy import Policy

logger = logging.getLogger(__name__)


@dataclass
class PolicyDecision:
    entity: DetectedEntity
    action: str  # allow | redact | block | warn
    policy_name: str | None = None
    severity: str = "medium"
    notify: bool = False


@dataclass
class PolicyEvaluation:
    decisions: list[PolicyDecision]
    blocked: bool = False
    block_reason: str | None = None
    warnings: list[str] | None = None

    @property
    def entities_to_redact(self) -> list[DetectedEntity]:
        return [d.entity for d in self.decisions if d.action in ("redact", "warn")]

    @property
    def entities_to_notify(self) -> list[PolicyDecision]:
        return [d for d in self.decisions if d.notify]


async def evaluate_policies(
    entities: list[DetectedEntity],
    org_id: str,
    db: AsyncSession,
) -> PolicyEvaluation:
    """Evaluate detected entities against organization policies.

    Policies are matched by entity_type (or * for all) and applied in priority order.
    First matching policy wins for each entity.
    """
    # Load active policies for this org, ordered by priority
    result = await db.execute(
        select(Policy)
        .where(
            Policy.organization_id == org_id,
            Policy.is_active == True,
        )
        .order_by(Policy.priority)
    )
    policies = result.scalars().all()

    decisions: list[PolicyDecision] = []
    warnings: list[str] = []
    blocked = False
    block_reason = None

    for entity in entities:
        decision = _match_policy(entity, policies)
        decisions.append(decision)

        if decision.action == "block":
            blocked = True
            block_reason = (
                f"Policy '{decision.policy_name}' blocks {entity.entity_type} "
                f"entities (detected: {entity.value[:20]}...)"
            )
        elif decision.action == "warn":
            warnings.append(
                f"{entity.entity_type} detected with confidence {entity.confidence:.0%}"
            )

    return PolicyEvaluation(
        decisions=decisions,
        blocked=blocked,
        block_reason=block_reason,
        warnings=warnings if warnings else None,
    )


def _match_policy(entity: DetectedEntity, policies: list[Policy]) -> PolicyDecision:
    """Find the first matching policy for an entity."""
    for policy in policies:
        # Match by entity type (* matches all)
        if policy.entity_type != "*" and policy.entity_type != entity.entity_type:
            continue

        # Check confidence threshold
        if entity.confidence < policy.min_confidence:
            continue

        return PolicyDecision(
            entity=entity,
            action=policy.action,
            policy_name=policy.name,
            severity=policy.severity,
            notify=policy.notify,
        )

    # Default: redact
    return PolicyDecision(entity=entity, action="redact")
