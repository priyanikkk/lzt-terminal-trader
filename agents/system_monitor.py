"""
Agent 9 — SystemMonitorAgent.
Monitors API health, database connectivity, stuck transactions,
and operates an autonomous circuit breaker to protect funds upon errors.
"""

from typing import Dict, Any, List
import time
import logging
from agents.base import BaseAgent
from core.permissions import Permission
from api.lzt_client import lzt_client
from database.repository import repository

logger = logging.getLogger("SystemMonitorAgent")


class SystemMonitorAgent(BaseAgent[Dict[str, Any], Dict[str, Any]]):
    """
    Heartbeat and watchdog service with circuit breaker capabilities.
    """

    def __init__(self, agent_id: str = "system_monitor"):
        super().__init__(
            agent_id=agent_id,
            name="System Health & Watchdog Agent",
            role="Infrastructure Monitoring & Circuit Breaker",
            allowed_permissions={Permission.SYSTEM_MONITOR},
            tools=["lzt_client.get_balance", "database_ping", "circuit_breaker"]
        )
        self.circuit_broken: bool = False
        self.consecutive_errors: int = 0
        self.max_allowed_consecutive_errors: int = 5

    def trip_circuit_breaker(self, reason: str):
        self.circuit_broken = True
        logger.critical("CIRCUIT BREAKER TRIPPED! All purchasing frozen. Reason: %s", reason)

    def reset_circuit_breaker(self):
        self.circuit_broken = False
        self.consecutive_errors = 0
        logger.info("Circuit breaker reset. Normal operations resumed.")

    async def _run_task(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.verify_permission(Permission.SYSTEM_MONITOR)

        logger.info("Running system health check")
        health_report: Dict[str, Any] = {
            "api_status": "UNKNOWN",
            "api_latency_ms": 0.0,
            "database_status": "UNKNOWN",
            "stuck_transactions_count": 0,
            "circuit_broken": self.circuit_broken,
            "issues": []
        }

        # 1. API Health & Latency Check
        start = time.monotonic()
        try:
            balance_data = await lzt_client.get_balance()
            latency = (time.monotonic() - start) * 1000.0
            health_report["api_status"] = "HEALTHY"
            health_report["api_latency_ms"] = round(latency, 1)
            health_report["balance"] = balance_data
            self.consecutive_errors = 0
        except Exception as e:
            health_report["api_status"] = "DEGRADED"
            health_report["issues"].append(f"LZT API ping failed: {e}")
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.max_allowed_consecutive_errors:
                self.trip_circuit_breaker(f"Repeated API ping failures ({self.consecutive_errors})")

        # 2. Database Connectivity Check
        try:
            recent_logs = await repository.get_recent_agent_logs(limit=5)
            health_report["database_status"] = "HEALTHY"
        except Exception as e:
            health_report["database_status"] = "ERROR"
            health_report["issues"].append(f"Database error: {e}")
            self.trip_circuit_breaker("Database connectivity failure")

        # 3. Check for stuck transactions in UNKNOWN_TRANSACTION_STATUS
        try:
            unknown_lots = await repository.get_listings_by_state("UNKNOWN_TRANSACTION_STATUS", limit=10)
            health_report["stuck_transactions_count"] = len(unknown_lots)
            if len(unknown_lots) > 0:
                health_report["issues"].append(f"There are {len(unknown_lots)} listings with UNKNOWN status needing operator review.")
        except Exception as e:
            logger.error("Failed to query stuck listings: %s", e)

        # Record metric
        await repository.record_system_metric(
            name="system_health",
            value=1.0 if not health_report["issues"] else 0.0,
            status="CRITICAL" if self.circuit_broken else ("WARNING" if health_report["issues"] else "HEALTHY"),
            details=health_report
        )

        return health_report
