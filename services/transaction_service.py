"""
Transaction integrity service ensuring idempotent execution,
duplicate purchase prevention, and verification before retry.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
import uuid
import logging

from database.repository import repository
from models.transactions import PurchaseResult
from core.permissions import permission_controller, Permission

logger = logging.getLogger("TransactionService")


class TransactionService:
    """
    Guarantees that no item is purchased more than once and handles ambiguous states.
    """

    def __init__(self):
        self._active_locks: Dict[int, str] = {}  # item_id -> lock_id

    def generate_idempotency_key(self, item_id: int, operation: str = "BUY") -> str:
        return f"{operation}_{item_id}_{uuid.uuid4().hex[:12]}"

    def acquire_item_lock(self, item_id: int) -> Optional[str]:
        """Locks an item for purchase execution to prevent concurrent duplicate buys."""
        if item_id in self._active_locks:
            return None
        lock_token = uuid.uuid4().hex
        self._active_locks[item_id] = lock_token
        return lock_token

    def release_item_lock(self, item_id: int, lock_token: str) -> bool:
        if self._active_locks.get(item_id) == lock_token:
            del self._active_locks[item_id]
            return True
        return False

    async def is_item_already_processed(self, item_id: int) -> bool:
        """Checks DB for prior purchase transactions."""
        listing = await repository.get_listing(item_id)
        if not listing:
            return False
        # If item has reached or passed PURCHASE_PENDING or PURCHASE_CONFIRMED
        if listing.state in ["PURCHASE_PENDING", "PURCHASE_CONFIRMED", "RESALE_PREPARED", "LISTED", "SOLD"]:
            return True
        return False

    async def verify_transaction_status_before_retry(self, item_id: int) -> Dict[str, Any]:
        """
        In case of an uncertain transaction status, checks with repository/marketplace
        before attempting any repeated action.
        """
        listing = await repository.get_listing(item_id)
        if not listing:
            return {"can_retry": False, "reason": "Listing record not found in database."}

        if listing.state == "UNKNOWN_TRANSACTION_STATUS":
            logger.warning("Item %d is in UNKNOWN_TRANSACTION_STATUS. Requiring manual status check.", item_id)
            return {
                "can_retry": False,
                "reason": "Transaction status is ambiguous. Automated duplicate purchase forbidden."
            }

        return {"can_retry": True}


# Global transaction service instance
transaction_service = TransactionService()
