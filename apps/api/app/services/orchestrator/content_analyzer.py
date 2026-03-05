"""
Content Analyzer — regex-based detection of commitment, payment, and scope-change language.

Deterministic, fast, no API cost, auditable patterns.
Used by PolicyEngine to gate agent outbound messages that contain sensitive language.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ContentAnalysis:
    has_commitment: bool = False
    has_payment: bool = False
    has_scope_change: bool = False
    detected_patterns: List[str] = field(default_factory=list)
    risk_level: str = "none"  # "none" | "low" | "high"


# ── Pattern Sets ──────────────────────────────────────────────────────────────

COMMITMENT_PATTERNS = [
    (r"\b(?:agree|confirm|accept|commit|bind|obligat|approv)\w*\b.{0,30}\b(?:deal|order|contract|terms|offer|proposal)\b",
     "commitment language"),
    (r"\b(?:sign|execute|finalize)\w*\b.{0,20}\b(?:agreement|contract|deal)\b",
     "contract execution"),
    (r"\b(?:we (?:will|shall|agree to|commit to))\b.{0,40}\b(?:deliver|ship|pay|provide|supply)\b",
     "binding promise"),
    (r"\b(?:hereby|irrevocabl[ey]|unconditional)\b",
     "legal language"),
]

PAYMENT_PATTERNS = [
    (r"\b(?:pay|payment|invoice|deposit|wire|transfer|remit)\w*\b",
     "payment terms"),
    (r"\$[\d,]+\.?\d*",
     "dollar amount"),
    (r"\b\d+[.,]?\d*\s*(?:USD|EUR|CNY|RMB|GBP|JPY)\b",
     "currency amount"),
    (r"\b(?:bank account|routing number|swift|iban|ach)\b",
     "banking details"),
]

SCOPE_PATTERNS = [
    (r"\b(?:change|modify|amend|revise|update)\w*\b.{0,20}\b(?:scope|timeline|deadline|deliverable|specification)s?\b",
     "scope change"),
    (r"\b(?:extend|shorten|delay|postpone|accelerate)\w*\b.{0,20}\b(?:deadline|timeline|delivery|date)\b",
     "timeline change"),
]


class ContentAnalyzer:
    """Scan text for commitment, payment, and scope-change patterns."""

    def __init__(
        self,
        commitment_patterns: list = COMMITMENT_PATTERNS,
        payment_patterns: list = PAYMENT_PATTERNS,
        scope_patterns: list = SCOPE_PATTERNS,
    ):
        self._commitment = [(re.compile(p, re.IGNORECASE), label) for p, label in commitment_patterns]
        self._payment = [(re.compile(p, re.IGNORECASE), label) for p, label in payment_patterns]
        self._scope = [(re.compile(p, re.IGNORECASE), label) for p, label in scope_patterns]

    def analyze(self, content: str) -> ContentAnalysis:
        """Analyze content for sensitive patterns. Returns structured analysis."""
        result = ContentAnalysis()
        if not content:
            return result

        # Check each pattern category
        for regex, label in self._commitment:
            if regex.search(content):
                result.has_commitment = True
                result.detected_patterns.append(label)

        for regex, label in self._payment:
            if regex.search(content):
                result.has_payment = True
                result.detected_patterns.append(label)

        for regex, label in self._scope:
            if regex.search(content):
                result.has_scope_change = True
                result.detected_patterns.append(label)

        # Deduplicate patterns
        result.detected_patterns = list(dict.fromkeys(result.detected_patterns))

        # Determine risk level
        if result.has_commitment or result.has_payment:
            result.risk_level = "high"
        elif result.has_scope_change:
            result.risk_level = "low"

        return result
