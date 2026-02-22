"""Database seed — creates built-in detection rules and default policies on first startup."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.policy import Policy
from backend.models.rule import DetectionRule

logger = logging.getLogger(__name__)

BUILT_IN_RULES = [
    {
        "name": "Social Security Number",
        "description": "US Social Security Numbers (XXX-XX-XXXX format)",
        "entity_type": "SSN",
        "detection_method": "regex",
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "priority": 10,
        "confidence": 0.95,
    },
    {
        "name": "Credit Card Number",
        "description": "Major credit card numbers (Visa, Mastercard, Amex)",
        "entity_type": "CREDIT_CARD",
        "detection_method": "regex",
        "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
        "priority": 10,
        "confidence": 0.9,
    },
    {
        "name": "Email Address",
        "description": "Standard email addresses",
        "entity_type": "EMAIL",
        "detection_method": "regex",
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "priority": 20,
        "confidence": 0.95,
    },
    {
        "name": "US Phone Number",
        "description": "US phone numbers with formatting (parens, dashes, dots, or spaces)",
        "entity_type": "PHONE",
        "detection_method": "regex",
        "pattern": r"(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]?\d{4}\b",
        "priority": 30,
        "confidence": 0.85,
    },
    {
        "name": "IPv4 Address",
        "description": "IPv4 addresses (excludes common non-routable ranges)",
        "entity_type": "IP_ADDRESS",
        "detection_method": "regex",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "priority": 30,
        "confidence": 0.85,
    },
    {
        "name": "AWS Access Key",
        "description": "AWS access key IDs (AKIA prefix)",
        "entity_type": "API_KEY",
        "detection_method": "regex",
        "pattern": r"\bAKIA[0-9A-Z]{16}\b",
        "priority": 5,
        "confidence": 0.98,
    },
    {
        "name": "Generic API Secret",
        "description": "Key-value pairs that look like secrets (api_key=, secret=, token=, password=)",
        "entity_type": "SECRET",
        "detection_method": "regex",
        "pattern": r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*['\"]?([A-Za-z0-9_/+=.-]{8,})['\"]?",
        "priority": 15,
        "confidence": 0.8,
    },
    {
        "name": "Internal Hostname",
        "description": "Internal network hostnames (.internal, .local, .corp, .lan)",
        "entity_type": "HOSTNAME",
        "detection_method": "regex",
        "pattern": r"\b[a-z][a-z0-9-]{1,30}\.(?:internal|local|corp|lan|intra|priv)\b",
        "priority": 40,
        "confidence": 0.75,
    },
    {
        "name": "Connection String",
        "description": "Database connection strings (postgresql://, mysql://, mongodb://, redis://)",
        "entity_type": "CONNECTION_STRING",
        "detection_method": "regex",
        "pattern": r"(?:postgres(?:ql)?|mysql|mongodb|redis|amqp)://\S+",
        "priority": 5,
        "confidence": 0.95,
    },
    {
        "name": "MAC Address",
        "description": "Network MAC addresses",
        "entity_type": "MAC_ADDRESS",
        "detection_method": "regex",
        "pattern": r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
        "priority": 50,
        "confidence": 0.9,
    },
]

DEFAULT_POLICIES = [
    {
        "name": "Block SSN sharing",
        "description": "Prevent Social Security Numbers from being sent to LLMs",
        "entity_type": "SSN",
        "action": "block",
        "severity": "critical",
        "notify": True,
        "min_confidence": 0.9,
        "priority": 1,
    },
    {
        "name": "Block credit cards",
        "description": "Prevent credit card numbers from being sent to LLMs",
        "entity_type": "CREDIT_CARD",
        "action": "block",
        "severity": "critical",
        "notify": True,
        "min_confidence": 0.85,
        "priority": 2,
    },
    {
        "name": "Warn on internal FQDNs",
        "description": "Flag internal domain names (deep subdomains, AD domains) for review before sending to LLM",
        "entity_type": "FQDN",
        "action": "warn",
        "severity": "medium",
        "notify": False,
        "min_confidence": 0.7,
        "priority": 50,
    },
    {
        "name": "Redact all PII by default",
        "description": "Replace all detected PII with placeholders before sending to LLM",
        "entity_type": "*",
        "action": "redact",
        "severity": "medium",
        "notify": False,
        "min_confidence": 0.7,
        "priority": 100,
    },
]


async def seed_built_in_data(org_id: str, db: AsyncSession) -> None:
    """Seed built-in rules and default policies for an organization.

    Only creates them if they don't already exist (idempotent).
    """
    # Check if rules already seeded for this org
    result = await db.execute(
        select(DetectionRule).where(
            DetectionRule.organization_id == org_id,
            DetectionRule.is_built_in == True,
        ).limit(1)
    )
    if result.scalar_one_or_none():
        return  # Already seeded

    logger.info(f"Seeding built-in rules and policies for org {org_id}")

    for rule_data in BUILT_IN_RULES:
        rule = DetectionRule(
            organization_id=org_id,
            is_built_in=True,
            is_active=True,
            **rule_data,
        )
        db.add(rule)

    for policy_data in DEFAULT_POLICIES:
        policy = Policy(
            organization_id=org_id,
            is_built_in=True,
            is_active=True,
            **policy_data,
        )
        db.add(policy)

    await db.flush()
    logger.info(f"Seeded {len(BUILT_IN_RULES)} rules and {len(DEFAULT_POLICIES)} policies")
