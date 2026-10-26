"""
Unit tests for PurchaseManager, limits, idempotency, and confirmation in app/purchases.py.
"""

from decimal import Decimal
from pathlib import Path
import pytest
import tempfile

from config import settings
from app.database import db
from app.purchases import purchase_manager


@pytest.fixture(autouse=True)
async def cleanup_purchases_table():
    await db.init_db()
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM purchases")
        await conn.commit()
    purchase_manager._in_flight_locks.clear()
    yield


@pytest.mark.asyncio
async def test_purchase_requires_confirmation_when_enabled():
    settings.MANUAL_PURCHASE_CONFIRMATION = True
    success, msg, _ = await purchase_manager.execute_purchase(
        item_id=9812401,
        title="Test Lot",
        price=Decimal("180.0"),
        operator_confirmed=False,
    )
    assert success is False
    assert "confirmation is required" in msg


@pytest.mark.asyncio
async def test_purchase_exceeds_max_price():
    success, msg, _ = await purchase_manager.execute_purchase(
        item_id=9812401,
        title="Expensive Lot",
        price=Decimal("500.0"),  # Exceeds default 350.0
        operator_confirmed=True,
    )
    assert success is False
    assert "exceeds MAX_PURCHASE_PRICE" in msg


@pytest.mark.asyncio
async def test_successful_simulated_purchase():
    await db.init_db()
    # Reset lock if any
    purchase_manager._in_flight_locks.clear()

    item_id = 9812401
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM purchases WHERE item_id = ?", (item_id,))
        await conn.commit()

    success, msg, receipt = await purchase_manager.execute_purchase(
        item_id=item_id,
        title="Telegram [ID] 2022 Aged account",
        price=Decimal("180.0"),
        operator_confirmed=True,
    )
    assert success is True, f"Expected success but got: {msg}"
    assert receipt["item_id"] == item_id
    assert receipt["status"] == "simulated"

    # Idempotency check: buying the same item again should fail
    succ2, msg2, _ = await purchase_manager.execute_purchase(
        item_id=item_id,
        title="Telegram [US] account",
        price=Decimal("240.0"),
        operator_confirmed=True,
    )
    assert succ2 is False
    assert "already been purchased" in msg2
