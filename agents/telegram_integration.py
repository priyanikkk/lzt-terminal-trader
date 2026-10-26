"""
Agent 7 — TelegramIntegrationAgent.
Dispatches operational alerts, deal discoveries, risk interventions,
and financial summaries to the admin Telegram bot.
Strictly respects account privacy and never intercepts SMS / login codes.
"""

from typing import Dict, Any
import logging
from agents.base import BaseAgent
from core.permissions import Permission
from api.telegram_client import telegram_client

logger = logging.getLogger("TelegramIntegrationAgent")


class TelegramIntegrationAgent(BaseAgent[Dict[str, Any], bool]):
    """
    Operator communication gateway for telemetry, notifications, and operational oversight.
    """

    def __init__(self, agent_id: str = "telegram_integration"):
        super().__init__(
            agent_id=agent_id,
            name="Telegram Integration Agent",
            role="Admin Bot Notifications & Telemetry",
            allowed_permissions={Permission.NOTIFY_TELEGRAM},
            tools=["telegram_client.send_message", "telegram_client.notify_new_deal"]
        )

    async def _run_task(self, input_data: Dict[str, Any]) -> bool:
        self.verify_permission(Permission.NOTIFY_TELEGRAM)

        event_type = input_data.get("type", "GENERIC")
        logger.info("Dispatching Telegram notification: %s", event_type)

        if event_type == "NEW_DEAL":
            return await telegram_client.notify_new_deal(
                item_id=input_data["item_id"],
                title=input_data.get("title", ""),
                buy_price=str(input_data.get("buy_price", "0")),
                resale_price=str(input_data.get("resale_price", "0")),
                net_profit=str(input_data.get("net_profit", "0")),
                roi=str(input_data.get("roi", "0"))
            )

        elif event_type == "PURCHASE_SUCCESS":
            return await telegram_client.notify_purchase_success(
                item_id=input_data["item_id"],
                price=str(input_data.get("price", "0")),
                is_simulation=input_data.get("is_simulation", True),
                order_id=input_data.get("order_id")
            )

        elif event_type == "RISK_BLOCKED":
            return await telegram_client.notify_risk_blocked(
                item_id=input_data["item_id"],
                risk_level=input_data.get("risk_level", "HIGH"),
                reasons=input_data.get("reasons", [])
            )

        elif event_type == "ALERT":
            return await telegram_client.notify_system_alert(
                title=input_data.get("title", "Notice"),
                details=input_data.get("details", ""),
                severity=input_data.get("severity", "WARNING")
            )

        else:
            message_text = input_data.get("text", "System update.")
            return await telegram_client.send_message(message_text)
