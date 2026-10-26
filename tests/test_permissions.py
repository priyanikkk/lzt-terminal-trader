"""
Tests for the Permission Controller and Security Enforcement.
"""

import pytest
from decimal import Decimal
from core.permissions import (
    Permission,
    PermissionController,
    PermissionDeniedError,
    FinancialLimitExceededError,
    DYNAMIC_AGENT_ALLOWED_PERMISSIONS
)


def test_permission_controller_basic():
    ctrl = PermissionController()
    ctrl.register_agent("scanner", "Scanner", {Permission.SCAN_MARKET})

    # Allowed
    ctrl.check_permission("scanner", Permission.SCAN_MARKET)

    # Denied
    with pytest.raises(PermissionDeniedError):
        ctrl.check_permission("scanner", Permission.EXECUTE_PURCHASE)


def test_dynamic_agent_cannot_request_sensitive_permissions():
    ctrl = PermissionController()
    # Dynamic agents cannot be granted EXECUTE_PURCHASE
    with pytest.raises(PermissionDeniedError):
        ctrl.register_agent(
            agent_id="rogue_agent",
            role="Rogue",
            permissions={Permission.EXECUTE_PURCHASE},
            is_dynamic=True
        )


def test_validate_purchase_execution_safety():
    ctrl = PermissionController()
    ctrl.register_agent("buyer", "Buyer", {Permission.EXECUTE_PURCHASE})

    # 1. Unapproved risk blocks purchase
    with pytest.raises(PermissionDeniedError):
        ctrl.validate_purchase_execution(
            agent_id="buyer",
            item_price=Decimal("100.0"),
            is_simulation=True,
            is_live_enabled=False,
            daily_spent=Decimal("0.0"),
            max_daily_budget=Decimal("1000.0"),
            max_purchase_price=Decimal("200.0"),
            risk_approved=False
        )

    # 2. Exceeding max purchase price blocks purchase
    with pytest.raises(FinancialLimitExceededError):
        ctrl.validate_purchase_execution(
            agent_id="buyer",
            item_price=Decimal("500.0"),
            is_simulation=True,
            is_live_enabled=False,
            daily_spent=Decimal("0.0"),
            max_daily_budget=Decimal("1000.0"),
            max_purchase_price=Decimal("200.0"),
            risk_approved=True
        )

    # 3. Exceeding daily budget limit blocks purchase
    with pytest.raises(FinancialLimitExceededError):
        ctrl.validate_purchase_execution(
            agent_id="buyer",
            item_price=Decimal("150.0"),
            is_simulation=True,
            is_live_enabled=False,
            daily_spent=Decimal("950.0"),
            max_daily_budget=Decimal("1000.0"),
            max_purchase_price=Decimal("200.0"),
            risk_approved=True
        )

    # 4. Live execution disabled blocks live purchase
    with pytest.raises(PermissionDeniedError):
        ctrl.validate_purchase_execution(
            agent_id="buyer",
            item_price=Decimal("100.0"),
            is_simulation=False,
            is_live_enabled=False,
            daily_spent=Decimal("0.0"),
            max_daily_budget=Decimal("1000.0"),
            max_purchase_price=Decimal("200.0"),
            risk_approved=True
        )
