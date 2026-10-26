"""
Market Scanner for LZT Terminal Trader.
Searches Telegram account lots, applies safety filters, runs inspection & pricing,
and persists candidates to the local SQLite database.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from config import settings
from app.api_client import api_client
from app.database import db
from app.listing_inspector import inspector
from app.pricing import calculate_profit, estimate_fair_resale_price, evaluate_arbitrage_opportunity

logger = logging.getLogger("market_scanner")


class MarketScanner:
    def __init__(self):
        self.last_scan_results: List[Dict[str, Any]] = []

    async def scan_market(
        self,
        query: str = "",
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        country: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Executes a scan over Telegram accounts.
        Evaluates each candidate through ListingInspector and PricingEngine.
        """
        raw_items = await api_client.search_listings(
            query=query,
            min_price=min_price,
            max_price=max_price or float(settings.MAX_PURCHASE_PRICE),
            country=country,
        )

        evaluated_candidates = []

        for item in raw_items[:limit]:
            item_id = int(item["item_id"])

            # Check if already purchased
            if await db.is_item_purchased(item_id):
                continue

            # Run safety inspection
            inspection = inspector.inspect_listing(item)

            # Run pricing & ROI evaluation
            pricing = evaluate_arbitrage_opportunity(item)

            candidate = {
                "item_id": item_id,
                "title": item["title"],
                "price": item["price"],
                "currency": item.get("currency", "rub"),
                "country": item.get("country", "UNKNOWN"),
                "has_2fa": item.get("has_2fa", False),
                "spamblock": item.get("spamblock", False),
                "format_type": item.get("format_type", "session+json"),
                "age_days": item.get("age_days", 0),
                "seller": item.get("seller", "Unknown"),
                "description": item.get("description", ""),
                "risk_level": inspection.risk_level,
                "confidence": inspection.confidence_score,
                "inspection_recommendation": inspection.recommendation,
                "explanation": inspection.explanation,
                "flags": inspection.flags,
                "contradictions": inspection.contradictions,
                "target_resale_price": float(pricing["target_resale_price"]),
                "net_profit": float(pricing["net_profit"]),
                "roi_percent": float(pricing["roi_percent"]),
                "is_approved": pricing["is_approved"] and inspection.is_safe,
                "rejection_reasons": pricing["rejection_reasons"],
                "raw_data": item,
            }

            status = "approved" if candidate["is_approved"] else "rejected"
            candidate["status"] = status

            # Persist to DB
            await db.save_listing({
                "item_id": item_id,
                "title": candidate["title"],
                "price": candidate["price"],
                "currency": candidate["currency"],
                "country": candidate["country"],
                "has_2fa": candidate["has_2fa"],
                "spamblock": candidate["spamblock"],
                "format_type": candidate["format_type"],
                "risk_level": candidate["risk_level"],
                "confidence": candidate["confidence"],
                "status": status,
                "raw_data": item,
            })

            evaluated_candidates.append(candidate)

        self.last_scan_results = evaluated_candidates
        await db.add_log("INFO", f"Market scan completed: found {len(evaluated_candidates)} candidates.", "market_scanner")
        return evaluated_candidates


scanner = MarketScanner()
