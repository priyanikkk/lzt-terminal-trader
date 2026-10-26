"""
Agent 3 — PricingAgent.
Performs deterministic economic evaluation, fee accounting,
and ROI calculations using PricingService.
"""

import logging
from agents.base import BaseAgent
from core.permissions import Permission
from models.listings import TelegramAccountListing, PricingResult
from services.pricing_service import pricing_service

logger = logging.getLogger("PricingAgent")


class PricingAgent(BaseAgent[TelegramAccountListing, PricingResult]):
    """
    Computes fair valuation, commissions, and expected arbitrage yield.
    """

    def __init__(self, agent_id: str = "pricing_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Pricing & Economics Agent",
            role="Financial Modeling & Arbitrage Margin Calculation",
            allowed_permissions={Permission.CALCULATE_PRICING},
            tools=["pricing_service.calculate_arbitrage_metrics"]
        )

    async def _run_task(self, item: TelegramAccountListing) -> PricingResult:
        self.verify_permission(Permission.CALCULATE_PRICING)

        logger.info("Pricing listing #%d (cost=%s RUB)", item.item_id, item.price)
        pricing_result = pricing_service.calculate_arbitrage_metrics(item)

        if pricing_result.is_profitable:
            logger.info(
                "Listing #%d is PROFITABLE: Target resale %s RUB, Net profit +%s RUB (%s%% ROI)",
                item.item_id,
                pricing_result.estimated_resale_price,
                pricing_result.net_profit,
                pricing_result.roi_percent
            )
        else:
            logger.info(
                "Listing #%d rejected by pricing: %s",
                item.item_id,
                pricing_result.rejection_reason
            )

        return pricing_result
