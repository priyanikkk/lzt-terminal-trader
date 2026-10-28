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
        await conn.execute("DELETE FROM ledger_entries")
        await conn.execute(
            """
            INSERT INTO ledger_entries (tx_type, amount, balance_after, description, reference_id)
            VALUES ('deposit', 10000.0, 10000.0, 'Initial Sandbox Balance', 'INIT-DEPOSIT')
            """
        )
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


@pytest.mark.asyncio
async def test_purchase_rejects_negative_or_zero_price():
    success, msg, _ = await purchase_manager.execute_purchase(
        item_id=9812402,
        title="Negative Price Lot",
        price=Decimal("-50.0"),
        operator_confirmed=True,
    )
    assert success is False
    assert "Price must be positive" in msg

    succ_zero, msg_zero, _ = await purchase_manager.execute_purchase(
        item_id=9812402,
        title="Zero Price Lot",
        price=Decimal("0.0"),
        operator_confirmed=True,
    )
    assert succ_zero is False
    assert "Price must be positive" in msg_zero


@pytest.mark.asyncio
async def test_concurrent_purchases_block_duplicate_toctou():
    import asyncio
    item_id = 9812405
    results = await asyncio.gather(
        purchase_manager.execute_purchase(
            item_id=item_id,
            title="Concurrent Test Lot",
            price=Decimal("85.0"),
            operator_confirmed=True,
        ),
        purchase_manager.execute_purchase(
            item_id=item_id,
            title="Concurrent Test Lot Duplicate",
            price=Decimal("85.0"),
            operator_confirmed=True,
        ),
    )
    # Exactly one must succeed and one must fail (either already in-flight or already purchased)
    successes = [r for r in results if r[0] is True]
    failures = [r for r in results if r[0] is False]
    assert len(successes) == 1
    assert len(failures) == 1
    assert ("already in-flight" in failures[0][1] or "already been purchased" in failures[0][1])
