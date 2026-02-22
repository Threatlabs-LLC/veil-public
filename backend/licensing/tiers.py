"""Tier definitions and feature registry.

Single source of truth for what each tier includes.
Community tier is always available — no license key needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --- Feature Constants ---

FEATURE_CUSTOM_RULES = "custom_rules"
FEATURE_WEBHOOKS = "webhooks"
FEATURE_MULTI_PROVIDER = "multi_provider"
FEATURE_ADVANCED_AUDIT = "advanced_audit"
FEATURE_SSO = "sso"
FEATURE_HIPAA = "hipaa"
FEATURE_CUSTOM_NER = "custom_ner"
FEATURE_DATA_RESIDENCY = "data_residency"
FEATURE_PRIORITY_SUPPORT = "priority_support"
FEATURE_FQDN_DETECTION = "fqdn_detection"


@dataclass(frozen=True)
class TierDefinition:
    name: str
    level: int  # 0=free, 1=solo, 2=team, 3=business, 4=enterprise
    max_users: int
    max_custom_rules: int
    max_webhooks: int
    audit_retention_days: int
    api_rate_limit: int  # requests per minute for /api/
    gateway_rate_limit: int  # requests per minute for /v1/
    features: frozenset[str] = field(default_factory=frozenset)


TIERS: dict[str, TierDefinition] = {
    "free": TierDefinition(
        name="Free",
        level=0,
        max_users=3,
        max_custom_rules=5,
        max_webhooks=0,
        audit_retention_days=7,
        api_rate_limit=60,
        gateway_rate_limit=120,
        features=frozenset(),
    ),
    "solo": TierDefinition(
        name="Solo",
        level=1,
        max_users=1,
        max_custom_rules=10,
        max_webhooks=1,
        audit_retention_days=30,
        api_rate_limit=120,
        gateway_rate_limit=240,
        features=frozenset({
            FEATURE_CUSTOM_RULES,
        }),
    ),
    "team": TierDefinition(
        name="Team",
        level=2,
        max_users=25,
        max_custom_rules=100,
        max_webhooks=5,
        audit_retention_days=90,
        api_rate_limit=300,
        gateway_rate_limit=600,
        features=frozenset({
            FEATURE_CUSTOM_RULES,
            FEATURE_WEBHOOKS,
            FEATURE_MULTI_PROVIDER,
            FEATURE_ADVANCED_AUDIT,
            FEATURE_SSO,
        }),
    ),
    "business": TierDefinition(
        name="Business",
        level=3,
        max_users=200,
        max_custom_rules=500,
        max_webhooks=20,
        audit_retention_days=365,
        api_rate_limit=600,
        gateway_rate_limit=1200,
        features=frozenset({
            FEATURE_CUSTOM_RULES,
            FEATURE_WEBHOOKS,
            FEATURE_MULTI_PROVIDER,
            FEATURE_ADVANCED_AUDIT,
            FEATURE_SSO,
            FEATURE_HIPAA,
            FEATURE_DATA_RESIDENCY,
            FEATURE_FQDN_DETECTION,
        }),
    ),
    "enterprise": TierDefinition(
        name="Enterprise",
        level=4,
        max_users=999999,
        max_custom_rules=999999,
        max_webhooks=100,
        audit_retention_days=730,
        api_rate_limit=2000,
        gateway_rate_limit=5000,
        features=frozenset({
            FEATURE_CUSTOM_RULES,
            FEATURE_WEBHOOKS,
            FEATURE_MULTI_PROVIDER,
            FEATURE_ADVANCED_AUDIT,
            FEATURE_SSO,
            FEATURE_HIPAA,
            FEATURE_DATA_RESIDENCY,
            FEATURE_CUSTOM_NER,
            FEATURE_FQDN_DETECTION,
            FEATURE_PRIORITY_SUPPORT,
        }),
    ),
}


def get_tier(tier_name: str) -> TierDefinition:
    """Get tier definition by name. Falls back to community."""
    return TIERS.get(tier_name, TIERS["free"])


def tier_has_feature(tier_name: str, feature: str) -> bool:
    """Check if a tier includes a specific feature."""
    return feature in get_tier(tier_name).features


def tier_at_least(current: str, required: str) -> bool:
    """Check if current tier meets or exceeds required tier level."""
    return get_tier(current).level >= get_tier(required).level
