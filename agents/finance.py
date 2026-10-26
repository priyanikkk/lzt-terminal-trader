"""
Agent 8 — FinanceAgent.
Maintains the double-entry style financial ledger.
Performs strictly deterministic accounting calculations using Decimal.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import logging
from config import settings
from agents.base import BaseAgent
from core.permissions import Permission
from models.finance import FinanceEntry, FinanceEntryType, FinanceReportResult
from database.repository import repository

logger = logging.getLogger("FinanceAgent")


class FinanceAgent(BaseAgent[Dict[str, Any], FinanceReportResult]):
    """
    Maintains financial ledgers, tracks spending limits, and generates audit reports.
    """

    def __init__(self, agent_id: str = "finance_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Finance & Accounting Agent",
            role="Ledger Keeper & Financial Risk Auditor",
            allowed_permissions={Permission.FINANCIAL_LEDGER},
            tools=[
                "repository.record_ledger_entry",
                "repository.get_all_ledger_entries",
                "repository.get_daily_spent"
            ]
        )

    async def record_purchase(
        self,
        item_id: int,
        amount: Decimal,
        buyer_fee: Decimal,
        is_simulation: bool
    ) -> None:
        """Records purchase cost and buyer fee into ledger."""
        self.verify_permission(Permission.FINANCIAL_LEDGER)

        # 1. Purchase debit
        purchase_entry = FinanceEntry(
            entry_type=FinanceEntryType.PURCHASE,
            amount=amount,
            item_id=item_id,
            description=f"Purchase of lot #{item_id}",
            is_simulation=is_simulation
        )
        await repository.record_ledger_entry(purchase_entry)

        # 2. Buyer commission
        if buyer_fee > Decimal("0.0"):
            fee_entry = FinanceEntry(
                entry_type=FinanceEntryType.BUY_FEE,
                amount=buyer_fee,
                item_id=item_id,
                description=f"Buyer platform commission for #{item_id}",
                is_simulation=is_simulation
            )
            await repository.record_ledger_entry(fee_entry)

    async def record_sale(
        self,
        item_id: int,
        amount: Decimal,
        seller_fee: Decimal,
        is_simulation: bool
    ) -> None:
        """Records resale revenue and seller fee into ledger."""
        self.verify_permission(Permission.FINANCIAL_LEDGER)

        sale_entry = FinanceEntry(
            entry_type=FinanceEntryType.SALE,
            amount=amount,
            item_id=item_id,
            description=f"Resale of lot #{item_id}",
            is_simulation=is_simulation
        )
        await repository.record_ledger_entry(sale_entry)

        if seller_fee > Decimal("0.0"):
            fee_entry = FinanceEntry(
                entry_type=FinanceEntryType.SALE_FEE,
                amount=seller_fee,
                item_id=item_id,
                description=f"Seller platform commission for #{item_id}",
                is_simulation=is_simulation
            )
            await repository.record_ledger_entry(fee_entry)

    async def _run_task(self, input_data: Dict[str, Any]) -> FinanceReportResult:
        self.verify_permission(Permission.FINANCIAL_LEDGER)

        is_simulation = input_data.get("is_simulation", settings.SIMULATION_MODE)
        logger.info("Generating financial audit report (Simulation=%s)", is_simulation)

        entries = await repository.get_all_ledger_entries(is_simulation=is_simulation)
        spent_today = await repository.get_daily_spent(is_simulation=is_simulation)

        total_invested = Decimal("0.0")
        total_revenue = Decimal("0.0")
        total_fees = Decimal("0.0")
        purchases_count = 0
        sales_count = 0
        discrepancies: List[str] = []

        purchased_items = set()
        sold_items = set()

        for e in entries:
            amt = Decimal(str(e.amount))
            if e.entry_type == "PURCHASE":
                total_invested += amt
                purchases_count += 1
                if e.item_id:
                    purchased_items.add(e.item_id)
            elif e.entry_type == "SALE":
                total_revenue += amt
                sales_count += 1
                if e.item_id:
                    sold_items.add(e.item_id)
            elif e.entry_type in ["BUY_FEE", "SALE_FEE"]:
                total_fees += amt

        # Audit check: sales for unpurchased items
        unrecorded_sales = sold_items - purchased_items
        if unrecorded_sales:
            discrepancies.append(f"Detected sales for items without recorded purchase: {unrecorded_sales}")

        # Net Profit = Total Revenue - Total Invested - Total Fees
        net_profit = (total_revenue - total_invested - total_fees).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # ROI = (Net Profit / Total Invested) * 100
        if total_invested > Decimal("0.0"):
            roi = ((net_profit / total_invested) * Decimal("100.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            roi = Decimal("0.0")

        remaining_budget = max(Decimal("0.0"), settings.MAX_DAILY_BUDGET - spent_today)

        # Open inventory cost
        open_inventory_cost = Decimal("0.0")
        for e in entries:
            if e.entry_type == "PURCHASE" and e.item_id not in sold_items:
                open_inventory_cost += Decimal(str(e.amount))

        now = datetime.now(timezone.utc)
        return FinanceReportResult(
            period_start=entries[0].created_at if entries else now,
            period_end=now,
            total_purchases_count=purchases_count,
            total_invested=total_invested,
            total_sales_count=sales_count,
            total_revenue=total_revenue,
            total_fees_paid=total_fees,
            net_profit=net_profit,
            roi_total_percent=roi,
            daily_budget_limit=settings.MAX_DAILY_BUDGET,
            budget_spent_today=spent_today,
            budget_remaining_today=remaining_budget,
            open_inventory_cost=open_inventory_cost,
            discrepancies=discrepancies
        )
