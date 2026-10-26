"""
Unit tests for MarketScanner in app/market_scanner.py.
"""

from decimal import Decimal
import pytest

from app.database import db
from app.market_scanner import scanner


@pytest.mark.asyncio
async def test_market_scanner_evaluates_candidates():
    await db.init_db()

    candidates = await scanner.scan_market(limit=5)
    assert len(candidates) > 0

    first = candidates[0]
    assert "item_id" in first
    assert "price" in first
    assert "target_resale_price" in first
    assert "net_profit" in first
    assert "roi_percent" in first
    assert "risk_level" in first
    assert "is_approved" in first

    # Check persistence in database
    db_item = await db.get_listing_by_item_id(first["item_id"])
    assert db_item is not None
    assert db_item["title"] == first["title"]


@pytest.mark.asyncio
async def test_market_scanner_filters_by_country():
    await db.init_db()
    candidates_us = await scanner.scan_market(country="US")
    for c in candidates_us:
        assert c["country"] == "US"
