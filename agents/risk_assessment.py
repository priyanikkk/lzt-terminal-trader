"""
Agent 4 — RiskAssessmentAgent.
Evaluates counterparty reliability, platform constraints, and fraud signals.
Can VETO / BLOCK any deal, but cannot approve an operation that violates system permissions.
"""

from typing import Dict, Any, List, Tuple
import logging
from agents.base import BaseAgent
from core.permissions import Permission
from models.listings import TelegramAccountListing, ListingInspectionResult, PricingResult, RiskAssessmentResult
from services.transaction_service import transaction_service

logger = logging.getLogger("RiskAssessmentAgent")


class RiskAssessmentAgent(BaseAgent[Tuple[TelegramAccountListing, ListingInspectionResult, PricingResult], RiskAssessmentResult]):
    """
    Evaluates seller trust, duplicate purchase risk, and statistical anomalies.
    """

    def __init__(self, agent_id: str = "risk_assessment"):
        super().__init__(
            agent_id=agent_id,
            name="Risk Assessment Agent",
            role="Risk Scoring & Deal Veto Authority",
            allowed_permissions={Permission.ASSESS_RISK},
            tools=["transaction_service.is_item_already_processed", "risk_rules_matrix"]
        )

    async def _run_task(
        self,
        input_data: Tuple[TelegramAccountListing, ListingInspectionResult, PricingResult]
    ) -> RiskAssessmentResult:
        self.verify_permission(Permission.ASSESS_RISK)

        item, inspection, pricing = input_data
        logger.info("Assessing risks for lot #%d", item.item_id)

        risk_reasons: List[str] = []
        risk_flags: List[str] = []
        trust_score = 1.0

        # 1. Duplicate Attempt Verification
        is_duplicate = await transaction_service.is_item_already_processed(item.item_id)
        if is_duplicate:
            risk_reasons.append(f"Item #{item.item_id} has already been purchased or is currently active.")
            risk_flags.append("DUPLICATE_PURCHASE_ATTEMPT")

        # 2. Inspection status prerequisite
        if not inspection.is_valid:
            risk_reasons.append("Listing failed prior syntactic/semantic inspection.")
            risk_flags.append("FAILED_INSPECTION")

        # 3. Seller Trust Evaluation
        if item.seller_sales_count < 5:
            risk_flags.append("NEW_SELLER_LOW_SALES")
            trust_score -= 0.3
            if item.price > 250:
                risk_reasons.append("High price lot from novice seller (< 5 sales).")

        if item.seller_rating < 3.5 and item.seller_sales_count > 0:
            risk_flags.append("LOW_SELLER_RATING")
            trust_score -= 0.4
            risk_reasons.append(f"Seller has below-average rating: {item.seller_rating}/5.0")

        # 4. Pricing Sanity Checks (Extreme Anomaly Detection)
        if pricing.buy_price <= 0:
            risk_reasons.append("Invalid or zero purchase price detected.")
            risk_flags.append("ZERO_PRICE_ERROR")

        if not pricing.is_profitable:
            risk_reasons.append(f"Economic unviability: {pricing.rejection_reason}")
            risk_flags.append("UNPROFITABLE_DEAL")

        # 5. Account Volatility Checks
        if item.age_days < 7 and item.origin != "autoreg":
            risk_flags.append("VERY_YOUNG_ACCOUNT_HIGH_REVOKE_RISK")
            risk_reasons.append("Account age is under 7 days with non-autoreg origin. Severe risk of password recovery.")

        # Classify Risk Level
        if any(f in ["DUPLICATE_PURCHASE_ATTEMPT", "FAILED_INSPECTION", "ZERO_PRICE_ERROR"] for f in risk_flags):
            risk_level = "CRITICAL"
            can_proceed = False
        elif len(risk_reasons) > 0:
            risk_level = "HIGH"
            can_proceed = False
        elif len(risk_flags) > 0:
            risk_level = "MEDIUM"
            can_proceed = True
        else:
            risk_level = "LOW"
            can_proceed = True

        logger.info(
            "Risk assessment for lot #%d finished: Level=%s, CanProceed=%s, Flags=%s",
            item.item_id,
            risk_level,
            can_proceed,
            risk_flags
        )

        return RiskAssessmentResult(
            item_id=item.item_id,
            risk_level=risk_level,
            can_proceed=can_proceed,
            reasons=risk_reasons,
            risk_flags=risk_flags,
            seller_trust_score=max(0.0, round(trust_score, 2)),
            is_duplicate_attempt=is_duplicate
        )
