"""
Finance and Ledger Manager for LZT Terminal Trader.
Maintains financial transparency, tracks daily budget headroom,
and audits transaction history.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List

from config import settings
from app.database import db

logger = logging.getLogger("finance")


class FinanceManager:
    async def get_financial_summary(self) -> Dict[str, Any]:
        """Calculates a comprehensive financial snapshot."""
        balance = await db.get_current_balance()
        spent_today = await db.get_spent_today()
        daily_limit = settings.MAX_DAILY_BUDGET
        daily_headroom = max(Decimal("0.0"), daily_limit - spent_today)

        purchases = await db.get_purchases(limit=100)
        total_spent = sum(
            ((Decimal(str(p["buy_price"])) + Decimal(str(p["fee"]))) for p in purchases),
            Decimal("0.0")
        )
        completed_purchases = [p for p in purchases if p["status"] in ("completed", "simulated")]

        resale_items = await db.get_resale_items(limit=100)
        published_resales = [r for r in resale_items if r["status"] == "published"]
        sold_resales = [r for r in resale_items if r["status"] == "sold"]

        buy_fee_pct = settings.BUY_FEE_PERCENT / Decimal("100.0")
        resale_fee_pct = settings.RESALE_FEE_PERCENT / Decimal("100.0")

        realized_profit = Decimal("0.0")
        for r in sold_resales:
            target_p = Decimal(str(r["target_price"]))
            orig_p = Decimal(str(r["original_price"]))
            # Net revenue after marketplace resale fee
            net_payout = target_p - (target_p * resale_fee_pct)
            # Total purchase cost including buyer commission
            total_cost = orig_p + (orig_p * buy_fee_pct)
            realized_profit += (net_payout - total_cost)

        return {
            "current_balance": balance,
            "spent_today": spent_today,
            "daily_limit": daily_limit,
            "daily_headroom": daily_headroom,
            "total_purchases_count": len(completed_purchases),
            "total_spent_all_time": total_spent,
            "resale_inventory_count": len(resale_items),
            "resale_published_count": len(published_resales),
            "resale_sold_count": len(sold_resales),
            "realized_profit": realized_profit,
        }


    async def get_recent_transactions(self, limit: int = 20) -> List[Dict[str, Any]]:
        return await db.get_ledger_entries(limit=limit)

    async def add_funds(self, amount: Decimal, description: str = "Deposit") -> Decimal:
        """Adds funds to the ledger (sandbox or deposit tracking)."""
        new_balance = await db.add_ledger_entry(
            tx_type="deposit",
            amount=amount,
            description=description,
            reference_id="MANUAL-DEP",
        )
        await db.add_log("INFO", f"Deposited {amount:.2f} RUB. New balance: {new_balance:.2f} RUB.", "finance")
        return new_balance


finance_manager = FinanceManager()
