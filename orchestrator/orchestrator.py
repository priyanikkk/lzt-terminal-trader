"""
Central AI Orchestrator Agent.
Acts as the central mission controller, task dispatcher, and supervisor.
Coordinates all specialized agents, monitors errors, and controls system loops.
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from config import settings
from agents.base import BaseAgent
from agents.market_scanner import MarketScannerAgent
from agents.listing_inspector import ListingInspectorAgent
from agents.pricing import PricingAgent
from agents.risk_assessment import RiskAssessmentAgent
from agents.purchase_workflow import PurchaseWorkflowAgent
from agents.resale import ResaleAgent
from agents.telegram_integration import TelegramIntegrationAgent
from agents.finance import FinanceAgent
from agents.system_monitor import SystemMonitorAgent
from agents.qa import QAAgent

from orchestrator.registry import agent_registry
from orchestrator.workflow import workflow_pipeline, WorkflowExecutionSummary
from models.messages import AgentMessage
from models.listings import MarketScanResult
from database.repository import repository

logger = logging.getLogger("Orchestrator")


class OrchestratorAgent:
    """
    Master Dispatcher and Coordinator.
    Initializes standard agents, coordinates periodic scanning,
    dispatches pipeline execution, and enforces budget/safety invariants.
    """

    def __init__(self):
        self.is_running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self.last_cycle_time: Optional[datetime] = None
        self.cycle_count: int = 0
        self.active_items_in_flight: int = 0
        self.recent_summaries: List[WorkflowExecutionSummary] = []

    def initialize_system(self):
        """Bootstraps standard agent team and registers them."""
        logger.info("Initializing multi-agent arbitrage system...")

        # Instantiate all standard 10 agents
        agents = [
            MarketScannerAgent(),
            ListingInspectorAgent(),
            PricingAgent(),
            RiskAssessmentAgent(),
            PurchaseWorkflowAgent(),
            ResaleAgent(),
            TelegramIntegrationAgent(),
            FinanceAgent(),
            SystemMonitorAgent(),
            QAAgent(),
        ]

        for agent in agents:
            agent_registry.register(agent)

        logger.info("All 10 core agents successfully initialized and registered.")

    async def run_single_arbitrage_cycle(self) -> Dict[str, Any]:
        """
        Executes one full iteration:
        1. System health check
        2. Market scan
        3. Lot inspection, pricing, risk assessment, purchase, resale
        4. Financial update
        """
        self.cycle_count += 1
        self.last_cycle_time = datetime.now(timezone.utc)
        logger.info("=== Starting Arbitrage Cycle #%d ===", self.cycle_count)

        monitor: Optional[SystemMonitorAgent] = agent_registry.get("system_monitor")
        scanner: Optional[MarketScannerAgent] = agent_registry.get("market_scanner")
        financer: Optional[FinanceAgent] = agent_registry.get("finance_agent")

        # 1. Health & Watchdog Check
        if monitor:
            health_msg = await monitor.execute(AgentMessage(
                agent_id=monitor.agent_id,
                task_type="HEALTH_CHECK",
                input_data={}
            ))
            health_report = health_msg.output_data or {}
            if health_report.get("circuit_broken", False):
                logger.critical("Cycle paused: System circuit breaker is tripped!")
                return {"status": "PAUSED", "reason": "Circuit breaker active"}

        # 2. Market Scanning
        if not scanner:
            logger.error("MarketScannerAgent is missing!")
            return {"status": "ERROR", "reason": "MarketScanner missing"}

        scan_msg = await scanner.execute(AgentMessage(
            agent_id=scanner.agent_id,
            task_type="SCAN_MARKET",
            input_data={
                "min_price": settings.MIN_NET_PROFIT,
                "max_price": settings.MAX_PURCHASE_PRICE,
                "order_by": "price_to_up"
            }
        ))
        scan_result: MarketScanResult = scan_msg.output_data

        if not scan_result or not scan_result.candidates:
            logger.info("Scan completed: No new candidate lots found.")
            return {"status": "SUCCESS", "candidates_processed": 0, "deals_listed": 0}

        # 3. Process candidate listings sequentially through the workflow
        processed_count = 0
        listed_count = 0

        for candidate in scan_result.candidates:
            self.active_items_in_flight += 1
            try:
                summary = await workflow_pipeline.process_listing(candidate)
                self.recent_summaries.append(summary)
                if len(self.recent_summaries) > 50:
                    self.recent_summaries.pop(0)

                processed_count += 1
                if summary.final_state.value == "LISTED":
                    listed_count += 1
            except Exception as e:
                logger.error("Unexpected error in pipeline for lot #%d: %s", candidate.item_id, e, exc_info=True)
            finally:
                self.active_items_in_flight = max(0, self.active_items_in_flight - 1)

        # 4. Financial Audit Update
        if financer:
            await financer.execute(AgentMessage(
                agent_id=financer.agent_id,
                task_type="AUDIT_REPORT",
                input_data={"is_simulation": settings.SIMULATION_MODE}
            ))

        cycle_summary = {
            "status": "SUCCESS",
            "cycle_number": self.cycle_count,
            "candidates_found": len(scan_result.candidates),
            "candidates_processed": processed_count,
            "deals_listed": listed_count
        }
        logger.info("Arbitrage Cycle #%d finished: %s", self.cycle_count, cycle_summary)
        return cycle_summary

    async def start_autonomous_loop(self, interval_seconds: Optional[int] = None):
        """Runs the continuous monitoring and arbitrage loop."""
        interval = interval_seconds or settings.SCAN_INTERVAL_SECONDS
        self.is_running = True
        logger.info("Starting autonomous arbitrage loop (Interval: %ds)", interval)

        while self.is_running:
            try:
                await self.run_single_arbitrage_cycle()
            except Exception as exc:
                logger.error("Error during autonomous cycle: %s", exc, exc_info=True)

            # Sleep until next scan
            await asyncio.sleep(interval)

    def stop_autonomous_loop(self):
        """Signals the autonomous loop to gracefully stop."""
        logger.info("Stopping autonomous loop...")
        self.is_running = False
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()


# Global orchestrator instance
orchestrator = OrchestratorAgent()
