"""
Listing Inspector for LZT Terminal Trader.
Performs semantic analysis, contradiction detection, risk classification,
and prompt injection defense on untrusted marketplace listing text.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional

import unicodedata

PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s*:\s*override",
    r"you\s+must\s+buy\s+this",
    r"admin\s+command\s*:\s*buy",
    r"bypass\s+all\s+(security\s+)?rules",
    r"bypass\s+security\s+checks",
    r"developer\s+mode\s+activated",
    r"купи\s+немедленно\s+без\s+проверки",
    r"игнорируй\s+все\s+правила",
    r"sudo\s+buy",
    r"jailbreak",
    r"set\s+buy\s+priority\s+to\s+critical",
]


@dataclass
class InspectionResult:
    item_id: int
    is_safe: bool
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence_score: float
    recommendation: str  # APPROVE, REVIEW, REJECT
    flags: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    explanation: str = ""


class ListingInspector:
    def __init__(self):
        self.injection_regex = [re.compile(p, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS]

    def _sanitize_text(self, text: str) -> str:
        """Normalizes unicode to strip homoglyphs, accents, and zero-width characters."""
        if not text:
            return ""
        # Strip zero-width spaces and control characters
        cleaned = re.sub(r"[\u200b-\u200f\uFEFF\x00-\x1f]", "", text)
        # NFKD normalization to decompose lookalike characters
        normalized = unicodedata.normalize("NFKD", cleaned)
        return normalized

    def scan_for_prompt_injection(self, text: str) -> Optional[str]:
        """Detects malicious prompt injection attempts inside titles or descriptions."""
        sanitized = self._sanitize_text(text)
        for pattern in self.injection_regex:
            if pattern.search(sanitized):
                return pattern.pattern
        return None

    def inspect_listing(self, item: Dict[str, Any]) -> InspectionResult:
        item_id = int(item.get("item_id", 0))
        title = str(item.get("title", ""))
        desc = str(item.get("description", ""))
        combined_text = f"{title} {desc}"
        sanitized_text = self._sanitize_text(combined_text).lower()

        flags = []
        contradictions = []

        # 1. Prompt Injection Defense
        injection_match = self.scan_for_prompt_injection(combined_text)
        if injection_match:
            flags.append("PROMPT_INJECTION_ATTEMPT_DETECTED")
            return InspectionResult(
                item_id=item_id,
                is_safe=False,
                risk_level="CRITICAL",
                confidence_score=0.99,
                recommendation="REJECT",
                flags=flags,
                contradictions=contradictions,
                explanation=f"Malicious prompt injection string detected in listing text (pattern: {injection_match}).",
            )

        # 2. Contradiction Detection
        has_2fa = bool(item.get("has_2fa", False))
        spamblock = bool(item.get("spamblock", False))
        format_type = str(item.get("format_type", "")).lower()
        country = str(item.get("country", "")).upper()
        age_days = int(item.get("age_days", 0))

        # Check 2FA contradictions
        no_2fa_claims = ["2fa off", "no 2fa", "без 2fa", "без пароля", "2фа выкл", "без облачного пароля"]
        if any(c in sanitized_text for c in no_2fa_claims) and has_2fa:
            contradictions.append("Title/description claims 2FA is OFF, but metadata indicates 2FA is ACTIVE.")

        # Check Spamblock contradictions (guard against 'not clean' / 'не чистый')
        is_clean_claimed = False
        if re.search(r"\bno\s+spam(block)?\b", sanitized_text):
            is_clean_claimed = True
        elif re.search(r"\bбез\s+спамблока\b", sanitized_text):
            is_clean_claimed = True
        elif re.search(r"(?<!not\s)(?<!un)\bclean\b", sanitized_text):
            is_clean_claimed = True
        elif re.search(r"(?<!не\s)\bчистый\b", sanitized_text):
            is_clean_claimed = True

        if is_clean_claimed and spamblock:
            contradictions.append("Title/description claims clean spam status, but metadata shows SPAMBLOCK.")

        # Check Format contradictions
        if "tdata" in sanitized_text and "tdata" not in format_type and format_type:
            contradictions.append(f"Title mentions TData, but item format is declared as '{format_type}'.")

        # Check Geo contradictions
        geo_tag_match = re.search(r"\[([A-Z]{2})\]", title.upper())
        if geo_tag_match:
            tag_geo = geo_tag_match.group(1)
            if country and country != "UNKNOWN" and tag_geo != country:
                contradictions.append(f"Title geo tag '[{tag_geo}]' contradicts declared country '{country}'.")

        # Check Age/Year contradictions (e.g. title says 2021 registration but age is under 90 days)
        year_match = re.search(r"\b(201[5-9]|202[0-3])\b", title)
        if year_match and age_days < 90:
            claimed_year = year_match.group(1)
            contradictions.append(f"Title claims {claimed_year} vintage registration, but account age is only {age_days} days.")

        # 3. Trait Evaluation
        if age_days < 14:
            flags.append("VERY_FRESH_REGISTRATION")
        if spamblock:
            flags.append("ACTIVE_SPAMBLOCK")
        if has_2fa:
            flags.append("ACTIVE_2FA_PASSWORD")

        # 4. Risk Classification
        if contradictions:
            risk_level = "HIGH"
            recommendation = "REJECT"
            confidence = 0.90
            explanation = "Contradictions detected between seller description and actual account properties: " + "; ".join(contradictions)
        elif spamblock or has_2fa:
            risk_level = "HIGH"
            recommendation = "REJECT"
            confidence = 0.85
            explanation = "High risk traits detected (Spamblock or unverified 2FA)."
        elif "VERY_FRESH_REGISTRATION" in flags:
            risk_level = "MEDIUM"
            recommendation = "REVIEW"
            confidence = 0.75
            explanation = "Fresh account (<14 days), lower trust factor."
        else:
            risk_level = "LOW"
            recommendation = "APPROVE"
            confidence = 0.95
            explanation = "Listing is clean, consistent, and adheres to safety standards."

        is_safe = risk_level in ("LOW", "MEDIUM")

        return InspectionResult(
            item_id=item_id,
            is_safe=is_safe,
            risk_level=risk_level,
            confidence_score=confidence,
            recommendation=recommendation,
            flags=flags,
            contradictions=contradictions,
            explanation=explanation,
        )



inspector = ListingInspector()
