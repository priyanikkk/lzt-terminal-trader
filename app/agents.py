"""
Streamlined Multi-Agent Architecture for LZT Terminal Trader.
Each agent maintains state, role boundaries, structured inputs/outputs,
and operates within a unified single-process Python environment.
"""

from decimal import Decimal
import logging
import time
from typing import Any, Dict, List, Optional

from config import settings
from app.api_client import api_client
from app.database import db
from app.listing_inspector import inspector, InspectionResult
from app.market_scanner import scanner
from app.pricing import calculate_profit, estimate_fair_resale_price, evaluate_arbitrage_opportunity
from app.purchases import purchase_manager
from app.resale import resale_manager
from app.finance import finance_manager

logger = logging.getLogger("agents")


class BaseAgent:
    def __init__(self, agent_id: str, name: str, role: str):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.status = "IDLE"  # IDLE, RUNNING, SUCCESS, ERROR
        self.last_run: Optional[str] = None
        self.last_error: Optional[str] = None
        self.execution_count = 0

    def _mark_started(self):
        self.status = "RUNNING"
        self.last_run = time.strftime("%Y-%m-%d %H:%M:%S")
        self.execution_count += 1
        self.last_error = None

    def _mark_completed(self, success: bool = True, error: Optional[str] = None):
        self.status = "SUCCESS" if success else "ERROR"
        self.last_error = error


class MarketScannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_scanner",
            name="Market Scanner",
            role="Searches Telegram lots on LZT Market and filters initial candidates."
        )

    async def execute(self, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        self._mark_started()
        params = params or {}
        try:
            candidates = await scanner.scan_market(
                query=params.get("query", ""),
                min_price=params.get("min_price"),
                max_price=params.get("max_price"),
                country=params.get("country", ""),
                limit=params.get("limit", 20),
            )
            self._mark_completed(True)
            return candidates
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class ListingInspectorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_inspector",
            name="Listing Inspector",
            role="Inspects untrusted text, detects prompt injections, and classifies listing risks."
        )

    async def execute(self, item: Dict[str, Any]) -> InspectionResult:
        self._mark_started()
        try:
            result = inspector.inspect_listing(item)
            self._mark_completed(True)
            return result
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class PricingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_pricing",
            name="Pricing Engine",
            role="Calculates exact fees, target resale prices, net profit, and ROI using Decimal."
        )

    async def execute(self, item: Dict[str, Any]) -> Dict[str, Any]:
        self._mark_started()
        try:
            result = evaluate_arbitrage_opportunity(item)
            self._mark_completed(True)
            return result
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class PurchaseAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_purchase",
            name="Purchase Manager",
            role="Enforces safety locks, checks daily budgets, and executes purchases (simulation/live)."
        )

    async def execute(
        self,
        item_id: int,
        title: str,
        price: Decimal,
        operator_confirmed: bool = False,
    ) -> Dict[str, Any]:
        self._mark_started()
        try:
            success, msg, receipt = await purchase_manager.execute_purchase(
                item_id=item_id,
                title=title,
                price=price,
                operator_confirmed=operator_confirmed,
            )
            self._mark_completed(success, None if success else msg)
            return {"success": success, "message": msg, "receipt": receipt}
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class ResaleAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_resale",
            name="Resale Manager",
            role="Generates truthful listing drafts and manages inventory resale on the marketplace."
        )

    async def execute(
        self,
        purchase_id: int,
        item_id: int,
        target_price: Decimal,
        original_price: Decimal,
    ) -> Dict[str, Any]:
        self._mark_started()
        try:
            draft_id = await resale_manager.create_resale_draft(
                purchase_id=purchase_id,
                item_id=item_id,
                target_price=target_price,
                original_price=original_price,
            )
            self._mark_completed(True)
            return {"draft_id": draft_id, "item_id": item_id, "status": "draft"}
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class FinanceAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="agent_finance",
            name="Finance Auditor",
            role="Audits ledger entries, monitors daily budget limits, and reports financial metrics."
        )

    async def execute(self) -> Dict[str, Any]:
        self._mark_started()
        try:
            summary = await finance_manager.get_financial_summary()
            self._mark_completed(True)
            return summary
        except Exception as e:
            self._mark_completed(False, str(e))
            raise


class AgentRegistry:
    def __init__(self):
        self.scanner = MarketScannerAgent()
        self.inspector = ListingInspectorAgent()
        self.pricing = PricingAgent()
        self.purchase = PurchaseAgent()
        self.resale = ResaleAgent()
        self.finance = FinanceAgent()

    def all_agents(self) -> List[BaseAgent]:
        return [
            self.scanner,
            self.inspector,
            self.pricing,
            self.purchase,
            self.resale,
            self.finance,
        ]


agent_registry = AgentRegistry()
