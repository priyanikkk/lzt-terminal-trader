"""
Workflow Pipeline for Listing Lifecycle Processing.
Strictly governs transitions through the ListingStateMachine and coordinates agents.
"""

from typing import Dict, Any, Optional
import logging
from config import settings
from core.state_machine import ListingStateMachine, ListingState
from models.messages import AgentMessage
from models.listings import (
    TelegramAccountListing,
    ListingInspectionResult,
    PricingResult,
    RiskAssessmentResult
)
from models.transactions import PurchaseResult, ResaleResult
from database.repository import repository
from orchestrator.registry import agent_registry

logger = logging.getLogger("ArbitrageWorkflow")


class WorkflowExecutionSummary:
    def __init__(self, item_id: int):
        self.item_id = item_id
        self.final_state: ListingState = ListingState.DISCOVERED
        self.inspection: Optional[ListingInspectionResult] = None
        self.pricing: Optional[PricingResult] = None
        self.risk: Optional[RiskAssessmentResult] = None
        self.purchase: Optional[PurchaseResult] = None
        self.resale: Optional[ResaleResult] = None
        self.aborted_reason: Optional[str] = None


class ArbitrageWorkflowPipeline:
    """
    Executes an individual lot through the full arbitrage pipeline with verified transitions.
    """

    async def process_listing(self, listing: TelegramAccountListing) -> WorkflowExecutionSummary:
        summary = WorkflowExecutionSummary(listing.item_id)
        fsm = ListingStateMachine(initial_state=ListingState.DISCOVERED)

        # Retrieve agents from registry
        inspector = agent_registry.get("listing_inspector")
        pricer = agent_registry.get("pricing_agent")
        risk_agent = agent_registry.get("risk_assessment")
        buyer = agent_registry.get("purchase_workflow")
        reseller = agent_registry.get("resale_agent")
        notifier = agent_registry.get("telegram_integration")
        financer = agent_registry.get("finance_agent")

        logger.info("=== Starting Pipeline for Lot #%d ('%s') ===", listing.item_id, listing.title)
        # Check if item has already been purchased or processed
        existing = await repository.get_listing(listing.item_id)
        if existing and existing.state in ["PURCHASE_CONFIRMED", "RESALE_PREPARED", "LISTED", "SOLD"]:
            fsm.transition_to(ListingState.REJECTED, "workflow", f"Item #{listing.item_id} has already been purchased (state={existing.state})")
            summary.final_state = fsm.current_state
            summary.aborted_reason = f"Item #{listing.item_id} has already been purchased or is currently active."
            return summary

        # Ensure listing is registered in DB in DISCOVERED state
        await repository.upsert_listing(listing)

        # -------------------------------------------------------------
        # STEP 1: INSPECTION
        # -------------------------------------------------------------
        if not inspector:
            fsm.transition_to(ListingState.FAILED, "workflow", "Inspector agent missing from registry")
            summary.final_state = fsm.current_state
            return summary

        inspect_msg = AgentMessage(
            agent_id=inspector.agent_id,
            task_type="INSPECT_LISTING",
            input_data=listing
        )
        inspect_res_msg = await inspector.execute(inspect_msg)
        inspection_result: ListingInspectionResult = inspect_res_msg.output_data
        summary.inspection = inspection_result

        if not inspect_res_msg.output_data or not inspection_result.is_valid:
            reason = f"Inspection failed: {'; '.join(inspection_result.rejection_reasons if inspection_result else ['No inspection output'])}"
            fsm.transition_to(ListingState.REJECTED, inspector.agent_id, reason)
            await repository.update_listing_state(
                item_id=listing.item_id,
                state=fsm.current_state.value,
                is_valid=False,
                inspection_reasons=inspection_result.rejection_reasons if inspection_result else [reason]
            )
            summary.final_state = fsm.current_state
            summary.aborted_reason = reason
            logger.info("Lot #%d REJECTED during inspection: %s", listing.item_id, reason)
            return summary

        fsm.transition_to(ListingState.INSPECTED, inspector.agent_id, "Listing passed technical specification checks")
        await repository.update_listing_state(
            item_id=listing.item_id,
            state=fsm.current_state.value,
            is_valid=True
        )

        # -------------------------------------------------------------
        # STEP 2: PRICING & ECONOMICS
        # -------------------------------------------------------------
        if not pricer:
            fsm.transition_to(ListingState.FAILED, "workflow", "Pricing agent missing")
            summary.final_state = fsm.current_state
            return summary

        price_msg = AgentMessage(
            agent_id=pricer.agent_id,
            task_type="CALCULATE_PRICING",
            input_data=listing
        )
        price_res_msg = await pricer.execute(price_msg)
        pricing_result: PricingResult = price_res_msg.output_data
        summary.pricing = pricing_result

        if not pricing_result or not pricing_result.is_profitable:
            reason = f"Pricing unviable: {pricing_result.rejection_reason if pricing_result else 'No pricing output'}"
            fsm.transition_to(ListingState.REJECTED, pricer.agent_id, reason)
            await repository.update_listing_state(
                item_id=listing.item_id,
                state=fsm.current_state.value,
                estimated_resale_price=pricing_result.estimated_resale_price if pricing_result else None,
                estimated_net_profit=pricing_result.net_profit if pricing_result else None,
                estimated_roi=pricing_result.roi_percent if pricing_result else None
            )
            summary.final_state = fsm.current_state
            summary.aborted_reason = reason
            logger.info("Lot #%d REJECTED during pricing: %s", listing.item_id, reason)
            return summary

        fsm.transition_to(ListingState.PRICED, pricer.agent_id, f"Arbitrage yield profitable (+{pricing_result.net_profit} RUB)")
        await repository.update_listing_state(
            item_id=listing.item_id,
            state=fsm.current_state.value,
            estimated_resale_price=pricing_result.estimated_resale_price,
            estimated_net_profit=pricing_result.net_profit,
            estimated_roi=pricing_result.roi_percent
        )

        # Optional: notify admin about new profitable opportunity
        if notifier:
            await notifier.execute(AgentMessage(
                agent_id=notifier.agent_id,
                task_type="NOTIFY",
                input_data={
                    "type": "NEW_DEAL",
                    "item_id": listing.item_id,
                    "title": listing.title,
                    "buy_price": str(listing.price),
                    "resale_price": str(pricing_result.estimated_resale_price),
                    "net_profit": str(pricing_result.net_profit),
                    "roi": str(pricing_result.roi_percent)
                }
            ))

        # -------------------------------------------------------------
        # STEP 3: RISK ASSESSMENT
        # -------------------------------------------------------------
        if not risk_agent:
            fsm.transition_to(ListingState.FAILED, "workflow", "Risk agent missing")
            summary.final_state = fsm.current_state
            return summary

        risk_msg = AgentMessage(
            agent_id=risk_agent.agent_id,
            task_type="ASSESS_RISK",
            input_data=(listing, inspection_result, pricing_result)
        )
        risk_res_msg = await risk_agent.execute(risk_msg)
        risk_result: RiskAssessmentResult = risk_res_msg.output_data
        summary.risk = risk_result

        if not risk_result or not risk_result.can_proceed:
            reason = f"Risk veto: {'; '.join(risk_result.reasons if risk_result else ['Risk assessment failed'])}"
            fsm.transition_to(ListingState.REJECTED, risk_agent.agent_id, reason)
            await repository.update_listing_state(
                item_id=listing.item_id,
                state=fsm.current_state.value,
                risk_level=risk_result.risk_level if risk_result else "HIGH",
                risk_reasons=risk_result.reasons if risk_result else [reason]
            )
            if notifier:
                await notifier.execute(AgentMessage(
                    agent_id=notifier.agent_id,
                    task_type="NOTIFY",
                    input_data={
                        "type": "RISK_BLOCKED",
                        "item_id": listing.item_id,
                        "risk_level": risk_result.risk_level if risk_result else "HIGH",
                        "reasons": risk_result.reasons if risk_result else [reason]
                    }
                ))
            summary.final_state = fsm.current_state
            summary.aborted_reason = reason
            logger.info("Lot #%d BLOCKED by Risk Assessment: %s", listing.item_id, reason)
            return summary

        fsm.transition_to(ListingState.RISK_APPROVED, risk_agent.agent_id, f"Risk score acceptable (Level: {risk_result.risk_level})")
        await repository.update_listing_state(
            item_id=listing.item_id,
            state=fsm.current_state.value,
            risk_level=risk_result.risk_level,
            risk_reasons=risk_result.risk_flags
        )

        # -------------------------------------------------------------
        # STEP 4: PURCHASE WORKFLOW
        # -------------------------------------------------------------
        if not buyer:
            fsm.transition_to(ListingState.FAILED, "workflow", "Buyer agent missing")
            summary.final_state = fsm.current_state
            return summary

        fsm.transition_to(ListingState.PURCHASE_PENDING, buyer.agent_id, "Order lock acquired and parameters verified")
        await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)

        buy_msg = AgentMessage(
            agent_id=buyer.agent_id,
            task_type="EXECUTE_PURCHASE",
            input_data=(listing, pricing_result, risk_result)
        )
        buy_res_msg = await buyer.execute(buy_msg)
        purchase_result: PurchaseResult = buy_res_msg.output_data
        summary.purchase = purchase_result

        if not purchase_result or purchase_result.status not in ["SIMULATED", "SUCCESS"]:
            if purchase_result and purchase_result.status == "UNKNOWN":
                fsm.transition_to(ListingState.UNKNOWN_TRANSACTION_STATUS, buyer.agent_id, purchase_result.error_message or "Ambiguous status")
                await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)
                summary.final_state = fsm.current_state
                summary.aborted_reason = "Transaction in UNKNOWN status. Automated duplicate execution paused."
                return summary

            reason = f"Purchase failed: {purchase_result.error_message if purchase_result else 'No response from buyer'}"
            fsm.transition_to(ListingState.FAILED, buyer.agent_id, reason)
            await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)
            summary.final_state = fsm.current_state
            summary.aborted_reason = reason
            return summary

        fsm.transition_to(ListingState.PURCHASE_CONFIRMED, buyer.agent_id, f"Purchase confirmed (Order: {purchase_result.order_id})")
        await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)

        # Update financial ledger
        if financer:
            await financer.record_purchase(
                item_id=listing.item_id,
                amount=purchase_result.price_paid,
                buyer_fee=pricing_result.buyer_fee,
                is_simulation=purchase_result.is_simulation
            )

        if notifier:
            await notifier.execute(AgentMessage(
                agent_id=notifier.agent_id,
                task_type="NOTIFY",
                input_data={
                    "type": "PURCHASE_SUCCESS",
                    "item_id": listing.item_id,
                    "price": str(purchase_result.price_paid),
                    "is_simulation": purchase_result.is_simulation,
                    "order_id": purchase_result.order_id
                }
            ))

        # -------------------------------------------------------------
        # STEP 5: RESALE & LISTING
        # -------------------------------------------------------------
        if not reseller:
            fsm.transition_to(ListingState.FAILED, "workflow", "Reseller agent missing")
            summary.final_state = fsm.current_state
            return summary

        fsm.transition_to(ListingState.RESALE_PREPARED, reseller.agent_id, "Preparing verified title and description")
        await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)

        resale_msg = AgentMessage(
            agent_id=reseller.agent_id,
            task_type="PUBLISH_RESALE",
            input_data=(listing, purchase_result, pricing_result)
        )
        resale_res_msg = await reseller.execute(resale_msg)
        resale_result: ResaleResult = resale_res_msg.output_data
        summary.resale = resale_result

        if not resale_result or resale_result.status != "LISTED":
            reason = f"Resale publication failed: {resale_result.error_message if resale_result else 'No response from reseller'}"
            fsm.transition_to(ListingState.FAILED, reseller.agent_id, reason)
            await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)
            summary.final_state = fsm.current_state
            summary.aborted_reason = reason
            return summary

        fsm.transition_to(ListingState.LISTED, reseller.agent_id, f"Published on marketplace as #{resale_result.resale_item_id}")
        await repository.update_listing_state(item_id=listing.item_id, state=fsm.current_state.value)
        summary.final_state = fsm.current_state

        logger.info("=== Finished Pipeline for Lot #%d: Successfully LISTED ===", listing.item_id)
        return summary


# Global pipeline instance
workflow_pipeline = ArbitrageWorkflowPipeline()
