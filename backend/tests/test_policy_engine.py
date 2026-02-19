"""Unit tests for the policy engine — matching, priority, actions, confidence."""

import pytest

from backend.core.policy_engine import (
    PolicyDecision,
    PolicyEvaluation,
    _match_policy,
    evaluate_policies,
)
from backend.detectors.base import DetectedEntity


# ── Fake policy objects matching the Policy model interface ────────────


class _FakePolicy:
    def __init__(self, name, entity_type, action, priority=100,
                 min_confidence=0.7, severity="medium", notify=False, is_active=True):
        self.name = name
        self.entity_type = entity_type
        self.action = action
        self.priority = priority
        self.min_confidence = min_confidence
        self.severity = severity
        self.notify = notify
        self.is_active = is_active


# ── _match_policy (synchronous, no DB) ────────────────────────────────


class TestMatchPolicy:
    def test_exact_type_match(self):
        policies = [_FakePolicy("Block SSN", "SSN", "block", priority=1)]
        entity = DetectedEntity(entity_type="SSN", value="123-45-6789",
                                start=0, end=11, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.action == "block"
        assert decision.policy_name == "Block SSN"

    def test_wildcard_matches_all(self):
        policies = [_FakePolicy("Redact All", "*", "redact", priority=1)]
        entity = DetectedEntity(entity_type="EMAIL", value="a@b.com",
                                start=0, end=7, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.action == "redact"
        assert decision.policy_name == "Redact All"

    def test_first_match_wins_by_priority(self):
        policies = [
            _FakePolicy("Block SSN", "SSN", "block", priority=1),
            _FakePolicy("Allow SSN", "SSN", "allow", priority=2),
        ]
        entity = DetectedEntity(entity_type="SSN", value="123-45-6789",
                                start=0, end=11, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.action == "block"

    def test_lower_priority_if_first_doesnt_match_type(self):
        policies = [
            _FakePolicy("Block CC", "CREDIT_CARD", "block", priority=1),
            _FakePolicy("Warn All", "*", "warn", priority=2),
        ]
        entity = DetectedEntity(entity_type="EMAIL", value="a@b.com",
                                start=0, end=7, confidence=0.9)
        decision = _match_policy(entity, policies)
        # EMAIL doesn't match CREDIT_CARD, falls through to wildcard
        assert decision.action == "warn"

    def test_confidence_threshold_skips_low_confidence(self):
        policies = [_FakePolicy("Block SSN", "SSN", "block",
                                priority=1, min_confidence=0.95)]
        entity = DetectedEntity(entity_type="SSN", value="123-45-6789",
                                start=0, end=11, confidence=0.8)
        decision = _match_policy(entity, policies)
        # Confidence 0.8 < threshold 0.95, should fall to default
        assert decision.action == "redact"  # default

    def test_confidence_at_threshold_matches(self):
        policies = [_FakePolicy("Block SSN", "SSN", "block",
                                priority=1, min_confidence=0.8)]
        entity = DetectedEntity(entity_type="SSN", value="123-45-6789",
                                start=0, end=11, confidence=0.8)
        decision = _match_policy(entity, policies)
        assert decision.action == "block"

    def test_no_matching_policy_defaults_to_redact(self):
        policies = [_FakePolicy("Block CC", "CREDIT_CARD", "block")]
        entity = DetectedEntity(entity_type="EMAIL", value="a@b.com",
                                start=0, end=7, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.action == "redact"
        assert decision.policy_name is None

    def test_empty_policies_defaults_to_redact(self):
        entity = DetectedEntity(entity_type="EMAIL", value="a@b.com",
                                start=0, end=7, confidence=0.9)
        decision = _match_policy(entity, [])
        assert decision.action == "redact"

    def test_notify_flag_propagated(self):
        policies = [_FakePolicy("Warn IP", "IP_ADDRESS", "warn",
                                notify=True)]
        entity = DetectedEntity(entity_type="IP_ADDRESS", value="10.0.0.1",
                                start=0, end=8, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.notify is True

    def test_severity_propagated(self):
        policies = [_FakePolicy("Block SSN", "SSN", "block",
                                severity="critical")]
        entity = DetectedEntity(entity_type="SSN", value="123-45-6789",
                                start=0, end=11, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.severity == "critical"

    def test_allow_action(self):
        policies = [_FakePolicy("Allow Email", "EMAIL", "allow", priority=1)]
        entity = DetectedEntity(entity_type="EMAIL", value="a@b.com",
                                start=0, end=7, confidence=0.9)
        decision = _match_policy(entity, policies)
        assert decision.action == "allow"


# ── PolicyEvaluation properties ────────────────────────────────────────


class TestPolicyEvaluation:
    def test_entities_to_redact(self):
        d1 = PolicyDecision(
            entity=DetectedEntity("EMAIL", "a@b.com", 0, 7),
            action="redact",
        )
        d2 = PolicyDecision(
            entity=DetectedEntity("PHONE", "555-1234", 10, 18),
            action="allow",
        )
        d3 = PolicyDecision(
            entity=DetectedEntity("SSN", "123-45-6789", 20, 31),
            action="warn",
        )
        evaluation = PolicyEvaluation(decisions=[d1, d2, d3])
        to_redact = evaluation.entities_to_redact
        assert len(to_redact) == 2  # redact + warn
        types = {e.entity_type for e in to_redact}
        assert "EMAIL" in types
        assert "SSN" in types
        assert "PHONE" not in types

    def test_entities_to_notify(self):
        d1 = PolicyDecision(
            entity=DetectedEntity("EMAIL", "a@b.com", 0, 7),
            action="warn", notify=True,
        )
        d2 = PolicyDecision(
            entity=DetectedEntity("PHONE", "555-1234", 10, 18),
            action="redact", notify=False,
        )
        evaluation = PolicyEvaluation(decisions=[d1, d2])
        to_notify = evaluation.entities_to_notify
        assert len(to_notify) == 1
        assert to_notify[0].entity.entity_type == "EMAIL"

    def test_blocked_evaluation(self):
        evaluation = PolicyEvaluation(
            decisions=[], blocked=True,
            block_reason="SSN detected",
        )
        assert evaluation.blocked is True
        assert evaluation.block_reason == "SSN detected"


# ── evaluate_policies (async, needs DB) ────────────────────────────────


@pytest.fixture
async def policy_db(db_engine):
    """Set up a DB session with policies for testing evaluate_policies."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from backend.models.organization import Organization
    from backend.models.policy import Policy

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        org = Organization(name="Test", slug="test", tier="free")
        session.add(org)
        await session.flush()

        # Block SSN (priority 1)
        session.add(Policy(
            organization_id=org.id, name="Block SSN", entity_type="SSN",
            action="block", priority=1, min_confidence=0.7,
            severity="critical", notify=True,
        ))
        # Block CC (priority 2)
        session.add(Policy(
            organization_id=org.id, name="Block CC", entity_type="CREDIT_CARD",
            action="block", priority=2, min_confidence=0.7,
            severity="high",
        ))
        # Redact all (priority 100, catch-all)
        session.add(Policy(
            organization_id=org.id, name="Redact All", entity_type="*",
            action="redact", priority=100, min_confidence=0.5,
        ))
        await session.commit()

        yield session, org.id


class TestEvaluatePolicies:
    async def test_blocks_ssn(self, policy_db):
        session, org_id = policy_db
        entities = [
            DetectedEntity("SSN", "123-45-6789", 0, 11, confidence=0.9),
        ]
        result = await evaluate_policies(entities, org_id, session)
        assert result.blocked is True
        assert "Block SSN" in result.block_reason

    async def test_redacts_email_via_wildcard(self, policy_db):
        session, org_id = policy_db
        entities = [
            DetectedEntity("EMAIL", "a@b.com", 0, 7, confidence=0.9),
        ]
        result = await evaluate_policies(entities, org_id, session)
        assert result.blocked is False
        assert result.decisions[0].action == "redact"

    async def test_warns_collected(self, policy_db):
        """When no block but wildcard catches, no warnings generated since action is redact."""
        session, org_id = policy_db
        entities = [
            DetectedEntity("PHONE", "555-1234", 0, 8, confidence=0.9),
        ]
        result = await evaluate_policies(entities, org_id, session)
        assert result.blocked is False
        # Wildcard policy has action=redact, not warn, so no warnings
        assert result.warnings is None or len(result.warnings) == 0

    async def test_mixed_entities_block_wins(self, policy_db):
        session, org_id = policy_db
        entities = [
            DetectedEntity("EMAIL", "a@b.com", 0, 7, confidence=0.9),
            DetectedEntity("SSN", "123-45-6789", 20, 31, confidence=0.9),
        ]
        result = await evaluate_policies(entities, org_id, session)
        assert result.blocked is True  # SSN triggers block

    async def test_empty_entities(self, policy_db):
        session, org_id = policy_db
        result = await evaluate_policies([], org_id, session)
        assert result.blocked is False
        assert len(result.decisions) == 0

    async def test_low_confidence_falls_to_default(self, policy_db):
        session, org_id = policy_db
        entities = [
            DetectedEntity("SSN", "maybe-ssn", 0, 9, confidence=0.3),
        ]
        result = await evaluate_policies(entities, org_id, session)
        # Confidence 0.3 < block threshold 0.7, but wildcard threshold is 0.5
        # Still below 0.5, so falls to default redact
        assert result.blocked is False
