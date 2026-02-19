"""Detection rules CRUD API — let orgs add custom patterns."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import get_current_user
from backend.db.session import get_db
from backend.licensing.dependencies import require_feature
from backend.licensing.tiers import FEATURE_CUSTOM_RULES, get_tier
from backend.models.organization import Organization
from backend.models.rule import DetectionRule
from backend.models.user import User

router = APIRouter(prefix="/rules", tags=["rules"])


# --- Schemas ---

class RuleCreate(BaseModel):
    name: str
    description: str | None = None
    entity_type: str
    detection_method: str = "regex"  # regex | dictionary
    pattern: str | None = None
    word_list: list[str] | None = None
    priority: int = 100
    confidence: float = 0.8
    sample_matches: list[str] | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    pattern: str | None = None
    word_list: list[str] | None = None
    priority: int | None = None
    confidence: float | None = None
    is_active: bool | None = None
    sample_matches: list[str] | None = None


class RuleOut(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    detection_method: str
    pattern: str | None
    word_list: list[str] | None
    priority: int
    confidence: float
    is_active: bool
    is_built_in: bool
    sample_matches: list[str] | None
    created_at: str
    updated_at: str


class TestResult(BaseModel):
    input_text: str
    matches: list[dict]
    total: int


# --- Helpers ---

def _rule_to_out(rule: DetectionRule) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        entity_type=rule.entity_type,
        detection_method=rule.detection_method,
        pattern=rule.pattern,
        word_list=json.loads(rule.word_list) if rule.word_list else None,
        priority=rule.priority,
        confidence=rule.confidence,
        is_active=rule.is_active,
        is_built_in=rule.is_built_in,
        sample_matches=json.loads(rule.sample_matches) if rule.sample_matches else None,
        created_at=str(rule.created_at),
        updated_at=str(rule.updated_at),
    )


# --- Endpoints ---

@router.get("", response_model=list[RuleOut])
async def list_rules(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all detection rules for the organization."""
    result = await db.execute(
        select(DetectionRule)
        .where(DetectionRule.organization_id == user.organization_id)
        .order_by(DetectionRule.priority, DetectionRule.name)
    )
    return [_rule_to_out(r) for r in result.scalars().all()]


@router.post("", response_model=RuleOut, status_code=201,
             dependencies=[Depends(require_feature(FEATURE_CUSTOM_RULES))])
async def create_rule(
    body: RuleCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom detection rule."""
    # Check tier limit on custom rules
    org = await db.get(Organization, user.organization_id)
    tier_def = get_tier(org.tier if org else "community")

    existing_count = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == user.organization_id,
            DetectionRule.is_built_in == False,
        )
    )
    custom_count = len(existing_count.scalars().all())
    if custom_count >= tier_def.max_custom_rules:
        raise HTTPException(
            403,
            f"Custom rule limit reached ({tier_def.max_custom_rules} on {tier_def.name} plan). "
            "Upgrade to add more rules.",
        )

    # Validate regex pattern if provided
    if body.detection_method == "regex" and body.pattern:
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(400, f"Invalid regex pattern: {e}")

    if body.detection_method == "dictionary" and not body.word_list:
        raise HTTPException(400, "word_list is required for dictionary detection method")

    rule = DetectionRule(
        organization_id=user.organization_id,
        name=body.name,
        description=body.description,
        entity_type=body.entity_type,
        detection_method=body.detection_method,
        pattern=body.pattern,
        word_list=json.dumps(body.word_list) if body.word_list else None,
        priority=body.priority,
        confidence=body.confidence,
        sample_matches=json.dumps(body.sample_matches) if body.sample_matches else None,
    )
    db.add(rule)
    await db.flush()

    return _rule_to_out(rule)


@router.get("/{rule_id}", response_model=RuleOut)
async def get_rule(
    rule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single detection rule."""
    result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.id == rule_id,
            DetectionRule.organization_id == user.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    return _rule_to_out(rule)


@router.patch("/{rule_id}", response_model=RuleOut,
              dependencies=[Depends(require_feature(FEATURE_CUSTOM_RULES))])
async def update_rule(
    rule_id: str,
    body: RuleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a detection rule."""
    result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.id == rule_id,
            DetectionRule.organization_id == user.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    if rule.is_built_in:
        raise HTTPException(403, "Cannot modify built-in rules")

    if body.pattern is not None:
        try:
            re.compile(body.pattern)
        except re.error as e:
            raise HTTPException(400, f"Invalid regex pattern: {e}")
        rule.pattern = body.pattern

    if body.name is not None:
        rule.name = body.name
    if body.description is not None:
        rule.description = body.description
    if body.word_list is not None:
        rule.word_list = json.dumps(body.word_list)
    if body.priority is not None:
        rule.priority = body.priority
    if body.confidence is not None:
        rule.confidence = body.confidence
    if body.is_active is not None:
        rule.is_active = body.is_active
    if body.sample_matches is not None:
        rule.sample_matches = json.dumps(body.sample_matches)

    return _rule_to_out(rule)


@router.delete("/{rule_id}",
               dependencies=[Depends(require_feature(FEATURE_CUSTOM_RULES))])
async def delete_rule(
    rule_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a detection rule."""
    result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.id == rule_id,
            DetectionRule.organization_id == user.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    if rule.is_built_in:
        raise HTTPException(403, "Cannot delete built-in rules")

    await db.delete(rule)
    return {"status": "deleted"}


@router.post("/{rule_id}/test", response_model=TestResult)
async def test_rule(
    rule_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a detection rule against sample input text."""
    result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.id == rule_id,
            DetectionRule.organization_id == user.organization_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")

    input_text = body.get("text", "")
    if not input_text:
        raise HTTPException(400, "text field is required")

    matches = []

    if rule.detection_method == "regex" and rule.pattern:
        try:
            pattern = re.compile(rule.pattern, re.IGNORECASE)
            for match in pattern.finditer(input_text):
                matches.append({
                    "value": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": rule.confidence,
                })
        except re.error as e:
            raise HTTPException(400, f"Regex error: {e}")

    elif rule.detection_method == "dictionary" and rule.word_list:
        words = json.loads(rule.word_list)
        text_lower = input_text.lower()
        for word in words:
            idx = 0
            word_lower = word.lower()
            while True:
                pos = text_lower.find(word_lower, idx)
                if pos == -1:
                    break
                matches.append({
                    "value": input_text[pos:pos + len(word)],
                    "start": pos,
                    "end": pos + len(word),
                    "confidence": rule.confidence,
                })
                idx = pos + 1

    return TestResult(
        input_text=input_text,
        matches=matches,
        total=len(matches),
    )
