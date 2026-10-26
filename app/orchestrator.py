"""
Central Orchestrator for LZT Terminal Trader.
Coordinates specialized agents into a unified, reliable arbitrage workflow pipeline.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from config import settings
from app.agents import agent_registry
from app.database import db

logger = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self):
        self.registry = agent_registry
        self.is_running_cycle = False

    async def run_pipeline_cycle(
        self,
        auto_purchase: bool = False,
        scan_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a complete end-to-end multi-agent arbitrage cycle:
        1. Scanner -> 2. Inspector -> 3. Pricing -> 4. Optional Purchase -> 5. Resale Draft -> 6. Finance Audit.
        """
        if self.is_running_cycle:
            return {"status": "error", "message": "A pipeline cycle is already executing."}

        self.is_running_cycle = True
        summary: Dict[str, Any] = {
            "scanned_candidates": 0,
            "inspected_passed": 0,
            "pricing_approved": 0,
            "purchases_executed": 0,
            "resales_drafted": 0,
            "items_approved": [],
            "errors": [],
        }

        try:
            await db.add_log("INFO", "Starting automated arbitrage pipeline cycle...", "orchestrator")

            # 1. Market Scanner
            candidates = await self.registry.scanner.execute(scan_params)
            summary["scanned_candidates"] = len(candidates)

            # 2. Inspector & 3. Pricing are run per candidate
            approved_items = []
            for item in candidates:
                if item.get("is_approved"):
                    approved_items.append(item)

            summary["pricing_approved"] = len(approved_items)
            summary["items_approved"] = approved_items

            # 4. Optional Purchase Execution
            if auto_purchase and approved_items:
                for app_item in approved_items:
                    item_id = int(app_item["item_id"])
                    price = Decimal(str(app_item["price"]))
                    title = app_item["title"]

                    # Execute purchase (will respect confirmation flag and budget)
                    res = await self.registry.purchase.execute(
                        item_id=item_id,
                        title=title,
                        price=price,
                        operator_confirmed=not settings.MANUAL_PURCHASE_CONFIRMATION,
                    )

                    if res.get("success"):
                        summary["purchases_executed"] += 1
                        purchase_id = res["receipt"].get("purchase_id", 0)

                        # 5. Draft Resale
                        target_price = Decimal(str(app_item.get("target_resale_price", price * Decimal("1.4"))))
                        resale_res = await self.registry.resale.execute(
                            purchase_id=purchase_id,
                            item_id=item_id,
                            target_price=target_price,
                            original_price=price,
                        )
                        summary["resales_drafted"] += 1

            # 6. Finance Audit
            finance_report = await self.registry.finance.execute()
            summary["financial_snapshot"] = finance_report
            summary["status"] = "success"

            await db.add_log(
                "INFO",
                f"Pipeline cycle finished: {summary['scanned_candidates']} scanned, {summary['pricing_approved']} approved, {summary['purchases_executed']} bought.",
                "orchestrator"
            )
            return summary

        except Exception as e:
            err_msg = f"Pipeline cycle error: {str(e)}"
            summary["status"] = "error"
            summary["errors"].append(err_msg)
            await db.add_log("ERROR", err_msg, "orchestrator")
            return summary
        finally:
            self.is_running_cycle = False


orchestrator = Orchestrator()
