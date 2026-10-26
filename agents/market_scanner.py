"""
Agent 1 — MarketScannerAgent.
Researches the LZT Market for Telegram account lots matching search criteria,
filters duplicates and already evaluated lots, and outputs MarketScanResult.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging
from config import settings
from agents.base import BaseAgent
from core.permissions import Permission
from models.listings import TelegramAccountListing, MarketScanResult
from api.lzt_client import lzt_client
from database.repository import repository

logger = logging.getLogger("MarketScannerAgent")


class MarketScannerAgent(BaseAgent[Dict[str, Any], MarketScanResult]):
    """
    Scans the Telegram accounts category on LZT Market.
    """

    def __init__(self, agent_id: str = "market_scanner"):
        super().__init__(
            agent_id=agent_id,
            name="Market Scanner Agent",
            role="Market Discovery & Lot Ingestion",
            allowed_permissions={Permission.SCAN_MARKET},
            tools=["lzt_client.get_telegram_listings", "repository.get_listing"]
        )

    async def _run_task(self, input_data: Dict[str, Any]) -> MarketScanResult:
        self.verify_permission(Permission.SCAN_MARKET)

        min_price = input_data.get("min_price", Decimal("10.0"))
        max_price = input_data.get("max_price", settings.MAX_PURCHASE_PRICE)
        origin = input_data.get("origin", None)
        order_by = input_data.get("order_by", "price_to_up")

        logger.info("Scanning LZT Market: min_price=%s, max_price=%s, origin=%s", min_price, max_price, origin)

        # Query listings through API client
        raw_listings = await lzt_client.get_telegram_listings(
            min_price=min_price,
            max_price=max_price,
            origin=origin,
            order_by=order_by
        )

        candidates: List[TelegramAccountListing] = []
        for item in raw_listings:
            # Check DB to see if this item was already processed/bought or terminal
            existing = await repository.get_listing(item.item_id)
            if existing and existing.state in ["REJECTED", "SOLD", "PURCHASE_CONFIRMED", "LISTED"]:
                logger.debug("Skipping previously evaluated item %d (state=%s)", item.item_id, existing.state)
                continue

            # Store / update in repository
            await repository.upsert_listing(item)
            candidates.append(item)

        logger.info("Scan completed: Found %d total, %d valid candidates", len(raw_listings), len(candidates))

        return MarketScanResult(
            total_found=len(raw_listings),
            candidate_count=len(candidates),
            candidates=candidates,
            filters_applied={
                "min_price": str(min_price),
                "max_price": str(max_price),
                "origin": origin,
                "order_by": order_by
            }
        )
