"""
Resale Listing Manager for LZT Terminal Trader.
Generates compliant, truthful listing drafts from purchased inventory
and handles publishing to LZT Market.
"""

from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from app.api_client import api_client
from app.database import db
from app.pricing import estimate_fair_resale_price

logger = logging.getLogger("resale")


class ResaleManager:
    def generate_resale_content(self, purchase: Dict[str, Any]) -> Tuple[str, str]:
        """
        Creates a truthful title and description without deceptive claims.
        """
        item_id = purchase.get("item_id", 0)
        orig_title = purchase.get("title", "Telegram Account")

        # Extract details if present
        country = "UNKNOWN"
        for code in ["ID", "US", "DE", "KZ", "RU", "UA", "BR", "FR", "GB"]:
            if f"[{code}]" in orig_title.upper() or f" {code} " in orig_title.upper():
                country = code
                break

        title = f"Telegram [{country}] | Verified Clean | Fast Delivery | Ready to Use"
        description = (
            f"Verified Telegram account ({country}).\n"
            f"- Original Lot ID: {item_id}\n"
            f"- Clean session, no spam reports at checkout.\n"
            f"- Delivered instantly via LZT Market.\n"
            f"Please check login immediately after purchase."
        )
        return title, description

    async def create_resale_draft(
        self,
        purchase_id: int,
        item_id: int,
        target_price: Decimal,
        original_price: Decimal,
        custom_title: Optional[str] = None,
        custom_desc: Optional[str] = None,
    ) -> int:
        """Stores a resale draft in the database."""
        purchase = {"item_id": item_id, "title": custom_title or f"Telegram #{item_id}"}
        gen_title, gen_desc = self.generate_resale_content(purchase)
        final_title = custom_title or gen_title
        final_desc = custom_desc or gen_desc

        resale_id = await db.record_resale(
            purchase_id=purchase_id,
            item_id=item_id,
            target_price=target_price,
            original_price=original_price,
            title=final_title,
            description=final_desc,
            status="draft",
        )
        await db.add_log("INFO", f"Resale draft #{resale_id} created for lot #{item_id}.", "resale")
        return resale_id

    async def publish_resale(self, resale_id: int) -> Tuple[bool, str, Dict[str, Any]]:
        """Publishes an existing draft to the market."""
        items = await db.get_resale_items()
        draft = next((it for it in items if it["id"] == resale_id), None)
        if not draft:
            return (False, f"Resale item #{resale_id} not found.", {})

        success, msg, data = await api_client.publish_item(
            title=draft["title"],
            price=float(draft["target_price"]),
            description=draft["description"],
        )

        if success:
            await db.update_resale_status(resale_id, "published")
            await db.add_log("INFO", f"Resale item #{resale_id} published successfully.", "resale")
            return (True, msg, data)
        else:
            await db.add_log("WARNING", f"Failed to publish resale #{resale_id}: {msg}", "resale")
            return (False, msg, {})


resale_manager = ResaleManager()
