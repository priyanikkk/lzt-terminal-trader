"""
Agent 2 — ListingInspectorAgent.
Performs syntactic and semantic inspection of Telegram account lots.
Treats all titles and descriptions as UNTRUSTED data and guards against prompt injections.
"""

from typing import List
import logging
from agents.base import BaseAgent
from core.permissions import Permission
from models.listings import TelegramAccountListing, ListingInspectionResult
from api.llm_client import llm_client

logger = logging.getLogger("ListingInspectorAgent")


class ListingInspectorAgent(BaseAgent[TelegramAccountListing, ListingInspectionResult]):
    """
    Validates account specifications, detects contradictions and hostile text injection.
    """

    def __init__(self, agent_id: str = "listing_inspector"):
        super().__init__(
            agent_id=agent_id,
            name="Listing Inspector Agent",
            role="Specification & Content Inspection",
            allowed_permissions={Permission.INSPECT_LISTING},
            tools=["llm_client.inspect_listing_text", "heuristic_analyzer"]
        )

    async def _run_task(self, item: TelegramAccountListing) -> ListingInspectionResult:
        self.verify_permission(Permission.INSPECT_LISTING)

        logger.info("Inspecting listing #%d: '%s'", item.item_id, item.title)
        rejection_reasons: List[str] = []
        detected_risks: List[str] = []
        untrusted_flags: List[str] = []

        # 1. Mandatory Technical Traits Verification
        if item.spam_block:
            rejection_reasons.append("Account is flagged with active SpamBlock.")

        if item.two_step_auth:
            rejection_reasons.append("Account has active 2FA (cloud password). Risk of lock-out.")

        if item.origin in ["phish", "brute"]:
            rejection_reasons.append(f"Disallowed account origin '{item.origin}'. High recall/ban probability.")

        valid_formats = {"tdata", "session_json", "telethon", "pyrogram"}
        if item.format.lower() not in valid_formats:
            rejection_reasons.append(f"Unsupported session format '{item.format}'.")

        # 2. Contradiction Detection between Title/Description and Metadata
        title_lower = item.title.lower()
        desc_lower = item.description.lower()

        # Check if title claims no spamblock but flag is True
        if "без спамблока" in title_lower and item.spam_block:
            detected_risks.append("Contradiction: Title claims 'no spamblock' but API flag is True.")

        # Check if seller claims 2021/2022 registration but age is under 30 days
        if any(y in title_lower for y in ["2020", "2021", "2022", "2023"]) and item.age_days < 30:
            detected_risks.append("Contradiction: Title claims aged registration year but account age is < 30 days.")

        # 3. Untrusted Text & Prompt Injection Inspection
        semantic_report = await llm_client.inspect_listing_text(item.title, item.description)
        if semantic_report.get("prompt_injection", False):
            rejection_reasons.append("Hostile prompt injection detected in description.")
            untrusted_flags.extend(semantic_report.get("flags", []))
        elif not semantic_report.get("safe", True):
            for r in semantic_report.get("reasons", []):
                detected_risks.append(r)

        # 4. Final Determination
        is_valid = len(rejection_reasons) == 0 and len(detected_risks) == 0
        mandatory_ok = len(rejection_reasons) == 0

        explanation = (
            "Listing passed all inspection checks."
            if is_valid
            else f"Rejected due to: {'; '.join(rejection_reasons + detected_risks)}"
        )

        return ListingInspectionResult(
            item_id=item.item_id,
            is_valid=is_valid,
            rejection_reasons=rejection_reasons,
            detected_risks=detected_risks,
            mandatory_traits_ok=mandatory_ok,
            untrusted_text_flags=untrusted_flags,
            explanation=explanation,
            confidence=float(semantic_report.get("score", 1.0))
        )
