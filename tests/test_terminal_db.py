"""
Unit tests for the SQLite Database layer in app/database.py.
"""

from decimal import Decimal
from pathlib import Path
import pytest
import tempfile

from app.database import Database


@pytest.fixture
async def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_trader.db"
        test_database = Database(db_path=db_path)
        await test_database.init_db()
        yield test_database


@pytest.mark.asyncio
async def test_db_init_and_seed(temp_db):
    bal = await temp_db.get_current_balance()
    assert bal == Decimal("10000.0")


@pytest.mark.asyncio
async def test_save_and_get_listing(temp_db):
    item = {
        "item_id": 12345,
        "title": "Test Listing",
        "price": 150.0,
        "currency": "rub",
        "country": "US",
        "has_2fa": False,
        "spamblock": False,
        "format_type": "tdata",
        "risk_level": "LOW",
        "confidence": 0.95,
        "status": "candidate",
        "raw_data": {"foo": "bar"},
    }
    await temp_db.save_listing(item)
    fetched = await temp_db.get_listing_by_item_id(12345)
    assert fetched is not None
    assert fetched["item_id"] == 12345
    assert fetched["title"] == "Test Listing"
    assert fetched["price"] == 150.0


@pytest.mark.asyncio
async def test_record_purchase_and_ledger(temp_db):
    initial_bal = await temp_db.get_current_balance()
    price = Decimal("150.0")
    fee = Decimal("3.0")

    pid = await temp_db.record_purchase(
        item_id=777,
        title="Telegram RU Account",
        price=price,
        fee=fee,
        status="simulated",
        credentials="test_session_creds",
    )
    assert pid > 0

    new_bal = await temp_db.get_current_balance()
    assert new_bal == initial_bal - (price + fee)

    spent_today = await temp_db.get_spent_today()
    assert spent_today == (price + fee)

    is_purchased = await temp_db.is_item_purchased(777)
    assert is_purchased is True


@pytest.mark.asyncio
async def test_resale_lifecycle(temp_db):
    resale_id = await temp_db.record_resale(
        purchase_id=1,
        item_id=888,
        target_price=Decimal("250.0"),
        original_price=Decimal("150.0"),
        title="Resale Title",
        description="Resale Description",
        status="draft",
    )
    assert resale_id > 0

    items = await temp_db.get_resale_items()
    assert len(items) == 1
    assert items[0]["status"] == "draft"

    await temp_db.update_resale_status(resale_id, "published")
    items_updated = await temp_db.get_resale_items()
    assert items_updated[0]["status"] == "published"
