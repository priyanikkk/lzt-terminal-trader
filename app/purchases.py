"""
Purchase Manager for LZT Terminal Trader.
Enforces idempotency, budget limits, manual confirmation guards,
and safe execution routing (live vs simulation).
"""

from decimal import Decimal
import logging
from typing import Any, Dict, Optional, Set, Tuple

from config import settings
from app.api_client import api_client
from app.database import db

logger = logging.getLogger("purchases")


class PurchaseManager:
    def __init__(self):
        self._in_flight_locks: Set[int] = set()

    async def execute_purchase(
        self,
        item_id: int,
        title: str,
        price: Decimal,
        operator_confirmed: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes a purchase with strict multi-layer verification.
        """
        # 1. Idempotency Lock
        if item_id in self._in_flight_locks:
            return (False, f"Purchase of lot #{item_id} is already in-flight.", {})

        if await db.is_item_purchased(item_id):
            return (False, f"Lot #{item_id} has already been purchased previously.", {})

        # 2. Operator Confirmation Check
        if settings.MANUAL_PURCHASE_CONFIRMATION and not operator_confirmed:
            return (False, f"Manual operator confirmation is required for lot #{item_id}.", {})

        # 3. Limit Verifications
        price = Decimal(str(price))
        if price > settings.MAX_PURCHASE_PRICE:
            return (False, f"Price {price:.2f} RUB exceeds MAX_PURCHASE_PRICE ({settings.MAX_PURCHASE_PRICE:.2f} RUB).", {})

        spent_today = await db.get_spent_today()
        if (spent_today + price) > settings.MAX_DAILY_BUDGET:
            return (
                False,
                f"Purchase of {price:.2f} RUB exceeds MAX_DAILY_BUDGET. (Spent today: {spent_today:.2f} RUB, Limit: {settings.MAX_DAILY_BUDGET:.2f} RUB).",
                {}
            )

        current_balance = await db.get_current_balance()
        buy_fee = price * (settings.BUY_FEE_PERCENT / Decimal("100.0"))
        total_needed = price + buy_fee
        if current_balance < total_needed:
            return (False, f"Insufficient balance ({current_balance:.2f} RUB). Required: {total_needed:.2f} RUB.", {})

        # 4. Acquire Lock & Execute
        self._in_flight_locks.add(item_id)
        try:
            # Check item status with API first
            check_ok, check_msg = await api_client.check_item(item_id)
            if not check_ok:
                return (False, f"Pre-purchase verification failed: {check_msg}", {})

            # Execute via API client
            success, msg, receipt = await api_client.fast_buy(item_id, float(price))
            if not success:
                await db.add_log("WARNING", f"Purchase failed for #{item_id}: {msg}", "purchases")
                return (False, msg, {})

            # 5. Persist to DB & Ledger
            status_str = "simulated" if receipt.get("simulated") else "completed"
            creds = receipt.get("credentials", "")
            purchase_id = await db.record_purchase(
                item_id=item_id,
                title=title,
                price=price,
                fee=buy_fee,
                status=status_str,
                credentials=creds,
            )

            await db.add_log("INFO", f"Purchase successful: Lot #{item_id} ({status_str}). ID: {purchase_id}", "purchases")

            return (
                True,
                msg,
                {
                    "purchase_id": purchase_id,
                    "item_id": item_id,
                    "title": title,
                    "price": float(price),
                    "fee": float(buy_fee),
                    "status": status_str,
                    "credentials": creds,
                }
            )
        finally:
            self._in_flight_locks.discard(item_id)


purchase_manager = PurchaseManager()
