"""
Unit tests for the Decimal Pricing Engine in app/pricing.py.
"""

from decimal import Decimal
import pytest

from app.pricing import (
    calculate_profit,
    estimate_fair_resale_price,
    evaluate_arbitrage_opportunity,
    round_rub,
)


def test_round_rub():
    val = Decimal("123.456")
    assert round_rub(val) == Decimal("123.46")
    val2 = Decimal("100.004")
    assert round_rub(val2) == Decimal("100.00")


def test_calculate_profit_exact_math():
    # Buy for 100 RUB, sell for 200 RUB, 2% buy fee, 4% resale fee
    metrics = calculate_profit(
        purchase_price=Decimal("100.0"),
        resale_price=Decimal("200.0"),
        buy_fee_pct=Decimal("2.0"),
        resale_fee_pct=Decimal("4.0"),
    )

    # buy_fee = 100 * 0.02 = 2.0 RUB
    assert metrics.buy_fee == Decimal("2.00")
    # total_investment = 100 + 2 = 102.0 RUB
    assert metrics.total_investment == Decimal("102.00")
    # resale_fee = 200 * 0.04 = 8.0 RUB
    assert metrics.resale_fee == Decimal("8.00")
    # net_payout = 200 - 8 = 192.0 RUB
    assert metrics.net_payout == Decimal("192.00")
    # net_profit = 192 - 102 = 90.0 RUB
    assert metrics.net_profit == Decimal("90.00")
    # ROI = (90 / 102) * 100 = 88.24%
    assert metrics.roi_percent == Decimal("88.24")
    # Breakeven = 102 / (1 - 0.04) = 102 / 0.96 = 106.25 RUB
    assert metrics.breakeven_price == Decimal("106.25")
    assert metrics.is_profitable is True


def test_calculate_profit_negative():
    # Buy for 200 RUB, sell for 100 RUB -> loss
    metrics = calculate_profit(
        purchase_price=Decimal("200.0"),
        resale_price=Decimal("100.0"),
        buy_fee_pct=Decimal("2.0"),
        resale_fee_pct=Decimal("4.0"),
    )
    assert metrics.net_profit < Decimal("0.0")
    assert metrics.is_profitable is False


def test_estimate_fair_resale_price_tier1_aged():
    account = {
        "country": "US",
        "age_days": 800,
        "format_type": "tdata",
        "has_2fa": False,
        "spamblock": False,
    }
    # US base: 280, age >= 730: +90, tdata: +20 -> 390.00 RUB
    price = estimate_fair_resale_price(account)
    assert price == Decimal("390.00")


def test_estimate_fair_resale_price_spamblock_penalty():
    account = {
        "country": "RU",
        "age_days": 5,
        "format_type": "session",
        "has_2fa": True,
        "spamblock": True,
    }
    price = estimate_fair_resale_price(account)
    # Severe drop due to spamblock/2fa
    assert price <= Decimal("40.00")


def test_evaluate_arbitrage_opportunity():
    good_item = {
        "item_id": 9901,
        "price": 120.0,
        "country": "DE",
        "age_days": 400,
        "format_type": "tdata",
        "has_2fa": False,
        "spamblock": False,
    }
    verdict = evaluate_arbitrage_opportunity(good_item)
    assert verdict["is_approved"] is True
    assert verdict["net_profit"] > Decimal("50.0")
    assert verdict["roi_percent"] > Decimal("25.0")
    assert verdict["confidence"] >= 0.70
