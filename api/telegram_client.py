"""
Telegram Bot API client for administrator alerts, deal notifications,
and operational metrics. Strictly respects privacy and security rules.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import httpx
import logging
from config import settings

logger = logging.getLogger("TelegramClient")


class TelegramClient:
    """
    Manages notifications to the operator's private Telegram bot.
    Never attempts 2FA interception, code extraction, or unauthorized API actions.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        admin_chat_id: Optional[str] = None
    ):
        self.bot_token = bot_token if bot_token is not None else settings.TELEGRAM_BOT_TOKEN
        self.admin_chat_id = admin_chat_id if admin_chat_id is not None else settings.TELEGRAM_ADMIN_CHAT_ID
        self.is_configured = bool(self.bot_token.strip() and self.admin_chat_id.strip())
        self.notification_history: List[Dict[str, Any]] = []

    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Sends an administrative text message to the configured admin chat."""
        record = {
            "timestamp": datetime.now(timezone.utc),
            "text": text,
            "status": "DELIVERED" if self.is_configured else "LOGGED_LOCAL"
        }
        self.notification_history.append(record)

        if not self.is_configured:
            logger.info("[Telegram Disabled/Not Configured] Alert: %s", text.replace("\n", " "))
            return True

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.admin_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.debug("Telegram alert delivered successfully.")
                    return True
                else:
                    logger.error("Telegram API error (%d): %s", resp.status_code, resp.text)
                    return False
        except Exception as e:
            logger.error("Failed to connect to Telegram Bot API: %s", e)
            return False

    async def notify_new_deal(
        self,
        item_id: int,
        title: str,
        buy_price: str,
        resale_price: str,
        net_profit: str,
        roi: str
    ) -> bool:
        text = (
            f"🎯 *New Arbitrage Deal Found!*\n\n"
            f"• *Item ID:* `{item_id}`\n"
            f"• *Title:* {title}\n"
            f"• *Buy Price:* `{buy_price} RUB`\n"
            f"• *Target Resale:* `{resale_price} RUB`\n"
            f"• *Expected Profit:* `+{net_profit} RUB` ({roi}% ROI)\n"
        )
        return await self.send_message(text)

    async def notify_purchase_success(
        self,
        item_id: int,
        price: str,
        is_simulation: bool,
        order_id: Optional[str]
    ) -> bool:
        mode = "🧪 [SIMULATION]" if is_simulation else "💳 [LIVE]"
        text = (
            f"✅ *Purchase Executed Successfully* {mode}\n\n"
            f"• *Item ID:* `{item_id}`\n"
            f"• *Order ID:* `{order_id or 'N/A'}`\n"
            f"• *Cost:* `{price} RUB`\n"
        )
        return await self.send_message(text)

    async def notify_risk_blocked(
        self,
        item_id: int,
        risk_level: str,
        reasons: List[str]
    ) -> bool:
        reasons_str = "\n".join([f"  - {r}" for r in reasons])
        text = (
            f"🛡️ *Deal Blocked by Risk Controller*\n\n"
            f"• *Item ID:* `{item_id}`\n"
            f"• *Risk Level:* `{risk_level}`\n"
            f"• *Reasons:*\n{reasons_str}\n"
        )
        return await self.send_message(text)

    async def notify_system_alert(self, title: str, details: str, severity: str = "WARNING") -> bool:
        icon = "⚠️" if severity == "WARNING" else "🚨"
        text = f"{icon} *SYSTEM {severity}: {title}*\n\n{details}"
        return await self.send_message(text)


# Global telegram client instance
telegram_client = TelegramClient()
