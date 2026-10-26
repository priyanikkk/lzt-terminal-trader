"""
Deterministic Financial and Pricing Engine for Telegram Arbitrage.
All calculations use Decimal for absolute precision and zero floating-point drift.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Tuple
import logging
from config import settings
from models.listings import TelegramAccountListing, PricingResult

logger = logging.getLogger("PricingService")


class PricingService:
    """
    Evaluates fair market value, calculates fees, net profit, and ROI deterministically.
    """

    # Baseline fair market values (in RUB) estimated across Telegram segments on LZT Market
    # segment: (base_median_price, age_bonus_per_month, channels_bonus)
    MARKET_BENCHMARKS: Dict[str, Tuple[Decimal, Decimal, Decimal]] = {
        # country_code -> (base_price, monthly_age_bonus, per_channel_bonus)
        "RU": (Decimal("180.0"), Decimal("15.0"), Decimal("10.0")),
        "US": (Decimal("160.0"), Decimal("12.0"), Decimal("8.0")),
        "ID": (Decimal("70.0"), Decimal("5.0"), Decimal("5.0")),
        "DEFAULT": (Decimal("140.0"), Decimal("10.0"), Decimal("7.0")),
    }

    def estimate_market_value(self, item: TelegramAccountListing) -> Decimal:
        """
        Estimates the fair resale market price for a Telegram account based on observable traits.
        """
        benchmarks = self.MARKET_BENCHMARKS.get(item.country_code.upper(), self.MARKET_BENCHMARKS["DEFAULT"])
        base_price, monthly_age_bonus, channel_bonus = benchmarks

        # Age calculation in months
        age_months = Decimal(str(item.age_days)) / Decimal("30.0")
        age_val = min(age_months, Decimal("24.0")) * monthly_age_bonus

        # Channels bonus
        channels_val = min(Decimal(str(item.channels_count)), Decimal("5.0")) * channel_bonus

        # Format modifier: tdata usually sells at +15% premium over session_json
        format_multiplier = Decimal("1.15") if item.format.lower() == "tdata" else Decimal("1.0")

        # Origin discount/premium: personal accounts sell at higher stability
        origin_multiplier = Decimal("1.20") if item.origin.lower() == "personal" else Decimal("1.0")

        estimated = (base_price + age_val + channels_val) * format_multiplier * origin_multiplier
        return estimated.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def calculate_arbitrage_metrics(self, item: TelegramAccountListing) -> PricingResult:
        """
        Calculates all fees, projected resale, net profit, and ROI.
        """
        buy_price = item.price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        comparable_median = self.estimate_market_value(item)

        # Resale strategy: Price slightly below median market (e.g. 92% of median) for fast liquidity
        target_resale = (comparable_median * Decimal("0.92")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Buyer fee (e.g. 2% on purchase)
        buyer_fee = (buy_price * (settings.BUY_FEE_PERCENT / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Seller fee (e.g. 4% on resale)
        seller_fee = (target_resale * (settings.RESALE_FEE_PERCENT / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Total invested / total expenses
        total_buy_cost = buy_price + buyer_fee
        total_expenses = buyer_fee + seller_fee

        # Net Profit = target_resale - seller_fee - buy_price - buyer_fee
        net_profit = (target_resale - seller_fee - total_buy_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # ROI = (Net Profit / Total Buy Cost) * 100
        if total_buy_cost > Decimal("0.0"):
            roi_percent = ((net_profit / total_buy_cost) * Decimal("100.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            roi_percent = Decimal("0.0")

        # Check viability against configuration thresholds
        meets_profit = net_profit >= settings.MIN_NET_PROFIT
        meets_roi = roi_percent >= settings.MIN_ROI_PERCENT
        below_max_price = buy_price <= settings.MAX_PURCHASE_PRICE

        is_profitable = meets_profit and meets_roi and below_max_price

        rejection_reason = None
        if not below_max_price:
            rejection_reason = f"Buy price {buy_price} RUB exceeds max budget cap of {settings.MAX_PURCHASE_PRICE} RUB."
        elif not meets_profit:
            rejection_reason = f"Net profit {net_profit} RUB is below minimum required {settings.MIN_NET_PROFIT} RUB."
        elif not meets_roi:
            rejection_reason = f"ROI {roi_percent}% is below minimum required {settings.MIN_ROI_PERCENT}%."

        # Confidence score based on data completeness
        confidence = 0.90 if item.age_days > 0 and item.country_code else 0.70

        return PricingResult(
            item_id=item.item_id,
            buy_price=buy_price,
            estimated_resale_price=target_resale,
            buyer_fee=buyer_fee,
            seller_fee=seller_fee,
            total_expenses=total_expenses,
            net_profit=net_profit,
            roi_percent=roi_percent,
            confidence_score=confidence,
            is_profitable=is_profitable,
            comparable_market_median=comparable_median,
            rejection_reason=rejection_reason
        )


# Global pricing service instance
pricing_service = PricingService()
