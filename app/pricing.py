"""
Deterministic Economics and Pricing Engine for LZT Terminal Trader.
All financial computations strictly utilize Python's Decimal type to prevent floating-point inaccuracies.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from typing import Any, Dict, Optional

from config import settings


@dataclass
class ProfitMetrics:
    purchase_price: Decimal
    buy_fee: Decimal
    total_investment: Decimal
    resale_price: Decimal
    resale_fee: Decimal
    net_payout: Decimal
    net_profit: Decimal
    roi_percent: Decimal
    breakeven_price: Decimal
    is_profitable: bool


def round_rub(val: Decimal, rounding=ROUND_HALF_UP) -> Decimal:
    """Rounds a Decimal value to 2 decimal places."""
    return val.quantize(Decimal("0.01"), rounding=rounding)


def calculate_profit(
    purchase_price: Decimal,
    resale_price: Decimal,
    buy_fee_pct: Optional[Decimal] = None,
    resale_fee_pct: Optional[Decimal] = None,
) -> ProfitMetrics:
    """
    Computes exact profit, fees, ROI, and breakeven point using Decimal.
    """
    b_fee_pct = buy_fee_pct if buy_fee_pct is not None else settings.BUY_FEE_PERCENT
    r_fee_pct = resale_fee_pct if resale_fee_pct is not None else settings.RESALE_FEE_PERCENT

    # Convert to Decimal just in case
    purchase_price = Decimal(str(purchase_price))
    resale_price = Decimal(str(resale_price))
    b_fee_pct = Decimal(str(b_fee_pct))
    r_fee_pct = Decimal(str(r_fee_pct))

    buy_fee = round_rub(purchase_price * (b_fee_pct / Decimal("100.0")))
    total_investment = purchase_price + buy_fee

    resale_fee = round_rub(resale_price * (r_fee_pct / Decimal("100.0")))
    net_payout = resale_price - resale_fee

    net_profit = round_rub(net_payout - total_investment)

    if total_investment > Decimal("0.0"):
        roi_percent = round_rub((net_profit / total_investment) * Decimal("100.0"))
    else:
        roi_percent = Decimal("0.0")

    fee_factor = Decimal("1.0") - (r_fee_pct / Decimal("100.0"))
    if fee_factor > Decimal("0.0"):
        # Use ROUND_CEILING to guarantee breakeven covers 100% of fees and cost
        breakeven_price = round_rub(total_investment / fee_factor, rounding=ROUND_CEILING)
    else:
        breakeven_price = total_investment

    is_profitable = net_profit > Decimal("0.0")

    return ProfitMetrics(
        purchase_price=round_rub(purchase_price),
        buy_fee=buy_fee,
        total_investment=round_rub(total_investment),
        resale_price=round_rub(resale_price),
        resale_fee=resale_fee,
        net_payout=round_rub(net_payout),
        net_profit=net_profit,
        roi_percent=roi_percent,
        breakeven_price=breakeven_price,
        is_profitable=is_profitable,
    )


def estimate_fair_resale_price(account: Dict[str, Any]) -> Decimal:
    """
    Estimates a conservative resale price on LZT Market based on Telegram account characteristics.
    """
    country = str(account.get("country", "")).upper()
    age_days = int(account.get("age_days", 0))
    format_type = str(account.get("format_type", "")).lower()
    has_2fa = bool(account.get("has_2fa", False))
    spamblock = bool(account.get("spamblock", False))

    # Base pricing model by geo tier
    if country in ("US", "DE", "GB", "FR", "CA"):
        base = Decimal("280.0")
    elif country in ("ID", "KZ", "UA", "TR", "IN"):
        base = Decimal("190.0")
    else:
        base = Decimal("150.0")

    # Age multiplier
    if age_days >= 730:      # 2+ years
        base += Decimal("90.0")
    elif age_days >= 365:    # 1+ year
        base += Decimal("60.0")
    elif age_days >= 90:     # 3+ months
        base += Decimal("30.0")
    elif age_days < 14:      # Very fresh
        base -= Decimal("30.0")

    # Format premium
    if "tdata" in format_type:
        base += Decimal("20.0")

    # Penalties
    if spamblock:
        base = Decimal("40.0")  # Drastic drop
    if has_2fa:
        base = Decimal("30.0")  # Password risk

    return round_rub(max(base, Decimal("30.0")))


def evaluate_arbitrage_opportunity(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full economic evaluation of an account listing candidate with multi-scenario forecasting.
    """
    try:
        purchase_price = Decimal(str(account.get("price", 0.0)))
    except Exception:
        purchase_price = Decimal("0.0")

    target_resale = estimate_fair_resale_price(account)

    # Multi-scenario forecasting: Conservative (85%), Baseline (100%), Optimistic (120%)
    cons_resale = round_rub(target_resale * Decimal("0.85"))
    opt_resale = round_rub(target_resale * Decimal("1.20"))

    metrics_baseline = calculate_profit(purchase_price, target_resale)
    metrics_conservative = calculate_profit(purchase_price, cons_resale)
    metrics_optimistic = calculate_profit(purchase_price, opt_resale)

    # Rejection checks
    rejection_reasons = []
    if purchase_price <= Decimal("0.0") or purchase_price.is_nan() or purchase_price.is_infinite():
        rejection_reasons.append(f"Invalid non-positive purchase price {purchase_price} RUB")
    if purchase_price > settings.MAX_PURCHASE_PRICE:
        rejection_reasons.append(f"Price {purchase_price} RUB exceeds max limit {settings.MAX_PURCHASE_PRICE} RUB")
    if metrics_baseline.net_profit < settings.MIN_NET_PROFIT:
        rejection_reasons.append(f"Profit {metrics_baseline.net_profit} RUB below threshold {settings.MIN_NET_PROFIT} RUB")
    if metrics_baseline.roi_percent < settings.MIN_ROI_PERCENT:
        rejection_reasons.append(f"ROI {metrics_baseline.roi_percent}% below threshold {settings.MIN_ROI_PERCENT}%")

    is_approved = len(rejection_reasons) == 0

    # Confidence score calculation
    confidence = Decimal("0.85")
    if account.get("spamblock"):
        confidence -= Decimal("0.40")
    if account.get("has_2fa"):
        confidence -= Decimal("0.30")
    if int(account.get("age_days", 0)) > 300:
        confidence += Decimal("0.10")

    confidence_score = float(max(min(confidence, Decimal("1.0")), Decimal("0.10")))

    return {
        "is_approved": is_approved,
        "purchase_price": metrics_baseline.purchase_price,
        "target_resale_price": metrics_baseline.resale_price,
        "buy_fee": metrics_baseline.buy_fee,
        "resale_fee": metrics_baseline.resale_fee,
        "total_investment": metrics_baseline.total_investment,
        "net_profit": metrics_baseline.net_profit,
        "roi_percent": metrics_baseline.roi_percent,
        "breakeven_price": metrics_baseline.breakeven_price,
        "confidence": confidence_score,
        "rejection_reasons": rejection_reasons,
        "scenarios": {
            "conservative": {
                "resale_price": metrics_conservative.resale_price,
                "net_profit": metrics_conservative.net_profit,
                "roi_percent": metrics_conservative.roi_percent,
            },
            "baseline": {
                "resale_price": metrics_baseline.resale_price,
                "net_profit": metrics_baseline.net_profit,
                "roi_percent": metrics_baseline.roi_percent,
            },
            "optimistic": {
                "resale_price": metrics_optimistic.resale_price,
                "net_profit": metrics_optimistic.net_profit,
                "roi_percent": metrics_optimistic.roi_percent,
            },
        },
    }
