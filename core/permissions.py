"""
Permission and Security Controller.
Provides a strictly enforced, non-bypassable role-based access control (RBAC)
and financial invariant validator that operates outside of LLM control.
"""

from enum import Enum
from decimal import Decimal
from typing import Set, Dict, Optional
import logging

logger = logging.getLogger("Permissions")


class Permission(str, Enum):
    SCAN_MARKET = "SCAN_MARKET"
    INSPECT_LISTING = "INSPECT_LISTING"
    CALCULATE_PRICING = "CALCULATE_PRICING"
    ASSESS_RISK = "ASSESS_RISK"
    EXECUTE_PURCHASE = "EXECUTE_PURCHASE"
    PUBLISH_RESALE = "PUBLISH_RESALE"
    NOTIFY_TELEGRAM = "NOTIFY_TELEGRAM"
    FINANCIAL_LEDGER = "FINANCIAL_LEDGER"
    SYSTEM_MONITOR = "SYSTEM_MONITOR"
    RUN_QA = "RUN_QA"
    GENERATE_AGENT = "GENERATE_AGENT"


# Safe permissions that dynamic agents (created by AgentFactory) are allowed to have
DYNAMIC_AGENT_ALLOWED_PERMISSIONS: Set[Permission] = {
    Permission.SCAN_MARKET,
    Permission.INSPECT_LISTING,
    Permission.CALCULATE_PRICING,
    Permission.ASSESS_RISK,
    Permission.SYSTEM_MONITOR,
    Permission.RUN_QA,
}


class PermissionDeniedError(Exception):
    """Raised when an agent attempts an unauthorized action."""
    pass


class FinancialLimitExceededError(Exception):
    """Raised when an operation exceeds hard financial limits."""
    pass


class SecurityContext:
    def __init__(self, agent_id: str, role: str, permissions: Set[Permission], is_dynamic: bool = False):
        self.agent_id = agent_id
        self.role = role
        self.permissions = set(permissions)
        self.is_dynamic = is_dynamic

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions


class PermissionController:
    """
    Central authority verifying that agents and workflows strictly follow
    assigned permissions and security limits.
    """

    def __init__(self):
        self._agent_contexts: Dict[str, SecurityContext] = {}

    def register_agent(
        self,
        agent_id: str,
        role: str,
        permissions: Set[Permission],
        is_dynamic: bool = False
    ) -> SecurityContext:
        """Registers an agent with explicit permissions."""
        if is_dynamic:
            # Dynamic agents are strictly forbidden from having dangerous permissions
            forbidden = permissions - DYNAMIC_AGENT_ALLOWED_PERMISSIONS
            if forbidden:
                raise PermissionDeniedError(
                    f"Dynamic agent '{agent_id}' cannot be granted sensitive permissions: {forbidden}"
                )

        ctx = SecurityContext(agent_id=agent_id, role=role, permissions=permissions, is_dynamic=is_dynamic)
        self._agent_contexts[agent_id] = ctx
        logger.debug("Registered agent security context: %s with %s", agent_id, [p.value for p in permissions])
        return ctx

    def get_context(self, agent_id: str) -> Optional[SecurityContext]:
        return self._agent_contexts.get(agent_id)

    def check_permission(self, agent_id: str, required_permission: Permission) -> None:
        """Verifies that the agent has the required permission."""
        ctx = self.get_context(agent_id)
        if not ctx:
            raise PermissionDeniedError(f"Agent '{agent_id}' is not registered with SecurityContext.")
        if not ctx.has_permission(required_permission):
            raise PermissionDeniedError(
                f"Agent '{agent_id}' lacks required permission '{required_permission.value}'. "
                f"Current permissions: {[p.value for p in ctx.permissions]}"
            )

    def validate_purchase_execution(
        self,
        agent_id: str,
        item_price: Decimal,
        is_simulation: bool,
        is_live_enabled: bool,
        daily_spent: Decimal,
        max_daily_budget: Decimal,
        max_purchase_price: Decimal,
        risk_approved: bool
    ) -> None:
        """
        Enforces non-negotiable security rules for purchase execution.
        Must be satisfied by deterministic logic, regardless of any agent's decision.
        """
        # 1. Agent permission check
        self.check_permission(agent_id, Permission.EXECUTE_PURCHASE)

        # 2. Risk approval is mandatory
        if not risk_approved:
            raise PermissionDeniedError("Cannot execute purchase: RiskAssessment has not approved this transaction.")

        # 3. Item price check
        if item_price > max_purchase_price:
            raise FinancialLimitExceededError(
                f"Item price {item_price} RUB exceeds max purchase price limit of {max_purchase_price} RUB."
            )

        # 4. Daily budget headroom check
        if (daily_spent + item_price) > max_daily_budget:
            raise FinancialLimitExceededError(
                f"Total spend with this item ({daily_spent + item_price} RUB) would exceed "
                f"daily budget limit ({max_daily_budget} RUB)."
            )

        # 5. Live mode verification
        if not is_simulation:
            if not is_live_enabled:
                raise PermissionDeniedError("Live purchases are currently disabled in configuration.")


# Global permission controller instance
permission_controller = PermissionController()
