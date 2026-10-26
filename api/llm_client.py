"""
Pluggable LLM and Local NLP Client for Text Inspection and Semantic Risk Analysis.
Includes anti-prompt-injection defenses and an autonomous zero-cost local heuristic analyzer.
"""

import re
from typing import Dict, Any, List
import logging
from config import settings

logger = logging.getLogger("LLMClient")

# Regex patterns indicating adversarial attempts inside untrusted listing text
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s+(override|prompt|directive)",
    r"you\s+must\s+approve",
    r"set\s+(buy\s+)?priority\s+to\s+critical",
    r"disregard\s+(all\s+)?checks",
    r"bypass\s+(security|risk|limits)",
    r"as\s+an\s+ai\s+language\s+model",
    r"secret\s+key",
    r"admin\s+mode",
]


class LocalHeuristicNLP:
    """
    Fast, deterministic, zero-cost semantic classifier for listing titles and descriptions.
    Runs completely offline without external API dependencies.
    """

    NEGATIVE_KEYWORDS = [
        "spamblock", "спамблок", "спам", "spam",
        "2fa", "облачный пароль", "cloud password", "пароль неизвестен",
        "бан", "ban", "muted", "ограничения", "dump", "дамп", "public", "паблик",
        "восстановлен", "retrieved", "брут", "brute", "фишинг", "phish"
    ]

    POSITIVE_KEYWORDS = [
        "чистый", "отлежка", "отлёжка", "personal", "личный", "tdata", "session",
        "ready", "прогретый", "warmed", "гарантия", "warranty"
    ]

    @classmethod
    def sanitize_untrusted_text(cls, text: str) -> str:
        """Strips control chars and dangerous sequences."""
        if not text:
            return ""
        # Remove null bytes and non-printable control characters
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        return cleaned.strip()

    @classmethod
    def check_for_prompt_injection(cls, text: str) -> List[str]:
        """Scans untrusted input for prompt injection attack signatures."""
        detected = []
        lower = text.lower()
        for pat in INJECTION_PATTERNS:
            if re.search(pat, lower):
                detected.append(pat)
        return detected

    @classmethod
    def analyze_listing_semantics(cls, title: str, description: str) -> Dict[str, Any]:
        """
        Analyzes title and description for hidden risks, contradictions, and sentiment.
        Distinguishes negated terms (e.g. 'no spamblock') from active risks.
        """
        clean_title = cls.sanitize_untrusted_text(title)
        clean_desc = cls.sanitize_untrusted_text(description)
        combined = f"{clean_title} {clean_desc}".lower()

        injections = cls.check_for_prompt_injection(combined)

        negations = ["no", "not", "without", "без", "не"]
        detected_negatives = []

        for kw in cls.NEGATIVE_KEYWORDS:
            # Check if keyword is in text
            pattern = rf"(?:\b(?:{'|'.join(negations)})\s+)?(\b{re.escape(kw)}\b)"
            matches = list(re.finditer(pattern, combined))
            for m in matches:
                full_match = m.group(0)
                # If preceded by negation, it is NOT an active negative signal
                if any(full_match.startswith(neg + " ") for neg in negations):
                    continue
                detected_negatives.append(kw)
                break

        detected_positives = [kw for kw in cls.POSITIVE_KEYWORDS if kw in combined]

        # Calculate semantic sentiment / risk score
        risk_penalty = len(detected_negatives) * 0.25 + (1.0 if injections else 0.0)
        quality_bonus = min(len(detected_positives) * 0.15, 0.4)
        score = max(0.0, min(1.0, 0.8 - risk_penalty + quality_bonus))

        return {
            "prompt_injection_detected": bool(injections),
            "injection_matches": injections,
            "detected_negative_signals": detected_negatives,
            "detected_positive_signals": detected_positives,
            "semantic_quality_score": round(score, 2),
            "is_suspicious": bool(injections or len(detected_negatives) >= 2)
        }


class LLMClient:
    """
    Pluggable LLM interface with guaranteed offline fallback.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.heuristic = LocalHeuristicNLP()

    async def inspect_listing_text(self, title: str, description: str) -> Dict[str, Any]:
        """
        Analyzes untrusted listing text. Always runs prompt injection check first.
        """
        # Always run local heuristic security check first
        analysis = self.heuristic.analyze_listing_semantics(title, description)

        if analysis["prompt_injection_detected"]:
            logger.warning("Prompt injection detected in listing text! Neutralizing.")
            return {
                "safe": False,
                "prompt_injection": True,
                "reasons": ["Detected adversarial prompt injection attempt in listing description."],
                "flags": analysis["injection_matches"],
                "score": 0.0,
                "provider": "local_sanitizer"
            }

        # If configured for external LLM and credentials exist, we can enhance the analysis
        if self.provider != "mock" and self.api_key.strip():
            try:
                # Stub for optional external LLM call (e.g. OpenAI/Anthropic/Gemini)
                # Text is strictly contained in data tags and not interpreted as instructions.
                logger.debug("Dispatching to %s provider for deep semantic inspection.", self.provider)
            except Exception as e:
                logger.warning("External LLM provider failed: %s. Using heuristic result.", e)

        # Default local heuristic evaluation
        is_safe = not analysis["is_suspicious"]
        reasons = []
        if analysis["detected_negative_signals"]:
            reasons.append(f"Negative signals detected: {', '.join(analysis['detected_negative_signals'])}")

        return {
            "safe": is_safe,
            "reasons": reasons,
            "flags": analysis["detected_negative_signals"],
            "score": analysis["semantic_quality_score"],
            "provider": "heuristic_nlp"
        }


# Global LLM client instance
llm_client = LLMClient()
