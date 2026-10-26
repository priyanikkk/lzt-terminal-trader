"""
Deterministic tests for Decimal pricing, fees, margins, and financial reports.
"""

import pytest
from decimal import Decimal
from services.pricing_service import PricingService
from models.listings import TelegramAccountListing
from config import settings


def test_pricing_service_exact_math():
    service = PricingService()
    listing = TelegramAccountListing(
        item_id=7701,
        title="TG RU Account",
        price=Decimal("100.00"),
        country_code="RU",
        channels_count=0,
        age_days=0,
        format="session_json",
        origin="autoreg"
    )

    metrics = service.calculate_arbitrage_metrics(listing)

    # Buy price: 100.00
    assert metrics.buy_price == Decimal("100.00")
    # Buyer fee: 2% of 100 = 2.00
    assert metrics.buyer_fee == Decimal("2.00")
    # Total expenses: buyer_fee + seller_fee
    assert metrics.total_expenses == metrics.buyer_fee + metrics.seller_fee
    # Net profit: target_resale - seller_fee - (buy_price + buyer_fee)
    expected_profit = metrics.estimated_resale_price - metrics.seller_fee - (metrics.buy_price + metrics.buyer_fee)
    assert metrics.net_profit == expected_profit


def test_pricing_rejection_low_profit():
    service = PricingService()
    # High buy price near median
    listing = TelegramAccountListing(
        item_id=7702,
        title="TG RU Account Barely Profitable",
        price=Decimal("155.00"),
        country_code="RU",
        channels_count=0,
        age_days=0,
        format="session_json",
        origin="autoreg"
    )
    metrics = service.calculate_arbitrage_metrics(listing)
    # Target resale is ~165.60, net profit < 50 RUB
    assert metrics.is_profitable is False
    assert "below minimum required" in metrics.rejection_reason
