"""
Agent 5 — PurchaseWorkflowAgent.
Coordinates the execution of lot purchases.
Enforces idempotent locking, budget quotas, price confirmation, and status resolution.
"""

from decimal import Decimal
from typing import Tuple, Dict, Any
import logging
from config import settings
from agents.base import BaseAgent
from core.permissions import Permission, permission_controller, PermissionDeniedError
from models.listings import TelegramAccountListing, PricingResult, RiskAssessmentResult
from models.transactions import PurchaseResult
from api.lzt_client import lzt_client
from database.repository import repository
from services.transaction_service import transaction_service

logger = logging.getLogger("PurchaseWorkflowAgent")


class PurchaseWorkflowAgent(BaseAgent[Tuple[TelegramAccountListing, PricingResult, RiskAssessmentResult], PurchaseResult]):
    """
    Manages purchase transactions with strict duplicate prevention and budget gating.
    """

    def __init__(self, agent_id: str = "purchase_workflow"):
        super().__init__(
            agent_id=agent_id,
            name="Purchase Workflow Agent",
            role="Purchase Execution & Order Gating",
            allowed_permissions={Permission.EXECUTE_PURCHASE},
            tools=[
                "permission_controller.validate_purchase_execution",
                "lzt_client.check_item_status",
                "lzt_client.fast_buy",
                "transaction_service.acquire_item_lock",
                "repository.save_purchase_transaction"
            ]
        )

    async def _run_task(
        self,
        input_data: Tuple[TelegramAccountListing, PricingResult, RiskAssessmentResult]
    ) -> PurchaseResult:
        self.verify_permission(Permission.EXECUTE_PURCHASE)

        item, pricing, risk = input_data
        logger.info("Initiating purchase workflow for lot #%d", item.item_id)

        # 1. Verify prior analysis outcomes
        if not risk.can_proceed:
            return PurchaseResult(
                item_id=item.item_id,
                status="FAILED",
                price_paid=Decimal("0.0"),
                is_simulation=settings.SIMULATION_MODE,
                error_message=f"Purchase blocked: Risk assessment rejected lot ({'; '.join(risk.reasons)})"
            )

        if not pricing.is_profitable:
            return PurchaseResult(
                item_id=item.item_id,
                status="FAILED",
                price_paid=Decimal("0.0"),
                is_simulation=settings.SIMULATION_MODE,
                error_message=f"Purchase blocked: Economically unviable ({pricing.rejection_reason})"
            )

        # 2. Acquire concurrency lock to prevent duplicate parallel operations
        lock_token = transaction_service.acquire_item_lock(item.item_id)
        if not lock_token:
            return PurchaseResult(
                item_id=item.item_id,
                status="FAILED",
                price_paid=Decimal("0.0"),
                is_simulation=settings.SIMULATION_MODE,
                error_message=f"Purchase blocked: Concurrent operation already in progress for item #{item.item_id}"
            )

        try:
            # 3. Check daily budget headroom via repository
            daily_spent = await repository.get_daily_spent(is_simulation=settings.SIMULATION_MODE)

            # 4. Mandatory Permission & Financial Invariant Check
            permission_controller.validate_purchase_execution(
                agent_id=self.agent_id,
                item_price=item.price,
                is_simulation=settings.SIMULATION_MODE,
                is_live_enabled=settings.LIVE_PURCHASE_ENABLED,
                daily_spent=daily_spent,
                max_daily_budget=settings.MAX_DAILY_BUDGET,
                max_purchase_price=settings.MAX_PURCHASE_PRICE,
                risk_approved=risk.can_proceed
            )

            # 5. Live Marketplace Re-verification (Verify item is still available and price has not jumped)
            status_check = await lzt_client.check_item_status(item.item_id)
            if not status_check.get("available", False):
                return PurchaseResult(
                    item_id=item.item_id,
                    status="FAILED",
                    price_paid=Decimal("0.0"),
                    is_simulation=settings.SIMULATION_MODE,
                    error_message="Item is no longer available on marketplace."
                )

            current_price = status_check.get("price", item.price)
            if current_price > item.price:
                return PurchaseResult(
                    item_id=item.item_id,
                    status="FAILED",
                    price_paid=Decimal("0.0"),
                    is_simulation=settings.SIMULATION_MODE,
                    error_message=f"Price increased from {item.price} to {current_price} RUB. Aborting purchase."
                )

            # 6. Execute Purchase (Sandbox or Live)
            logger.info("Executing purchase order for lot #%d at %s RUB (Simulation=%s)", item.item_id, current_price, settings.SIMULATION_MODE)
            purchase_res = await lzt_client.fast_buy(item.item_id, current_price)

            # 7. Record transaction in database
            await repository.save_purchase_transaction(purchase_res)

            return purchase_res

        finally:
            transaction_service.release_item_lock(item.item_id, lock_token)
