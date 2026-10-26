"""
Domain models for Telegram account market listings and stage results.
"""

from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


class TelegramAccountListing(BaseModel):
    """
    Representation of an individual Telegram account lot on LZT Market.
    """
    item_id: int = Field(description="Unique LZT item identifier")
    title: str = Field(description="Raw listing title")
    description: str = Field(default="", description="Raw listing description (treated as untrusted)")
    price: Decimal = Field(description="Listing price in RUB or primary currency")
    currency: str = Field(default="rub")
    seller_id: int = Field(default=0)
    seller_username: str = Field(default="")
    seller_rating: float = Field(default=0.0)
    seller_sales_count: int = Field(default=0)
    origin: str = Field(default="autoreg", description="e.g. autoreg, retrieval, personal, phish, brute")
    country_code: str = Field(default="RU", description="Phone number country code, e.g. RU, US, ID")
    spam_block: bool = Field(default=False, description="Whether account is currently spamblocked")
    two_step_auth: bool = Field(default=False, description="Whether 2FA / cloud password is set")
    has_active_sessions: bool = Field(default=False)
    channels_count: int = Field(default=0)
    chats_count: int = Field(default=0)
    age_days: int = Field(default=0, description="Age of the Telegram account in days")
    format: str = Field(default="tdata", description="Session format: tdata, session_json, telethon, etc.")
    url: str = Field(default="")
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class MarketScanResult(BaseModel):
    scan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_found: int = Field(default=0)
    candidate_count: int = Field(default=0)
    candidates: List[TelegramAccountListing] = Field(default_factory=list)
    filters_applied: Dict[str, Any] = Field(default_factory=dict)


class ListingInspectionResult(BaseModel):
    item_id: int
    is_valid: bool
    rejection_reasons: List[str] = Field(default_factory=list)
    detected_risks: List[str] = Field(default_factory=list)
    mandatory_traits_ok: bool
    untrusted_text_flags: List[str] = Field(default_factory=list)
    explanation: str = Field(default="")
    confidence: float = Field(default=1.0)


class PricingResult(BaseModel):
    item_id: int
    buy_price: Decimal
    estimated_resale_price: Decimal
    buyer_fee: Decimal
    seller_fee: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    roi_percent: Decimal
    confidence_score: float
    is_profitable: bool
    comparable_market_median: Decimal
    rejection_reason: Optional[str] = None


class RiskAssessmentResult(BaseModel):
    item_id: int
    risk_level: str = Field(description="LOW, MEDIUM, HIGH, CRITICAL")
    can_proceed: bool
    reasons: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    seller_trust_score: float = Field(default=1.0)
    is_duplicate_attempt: bool = Field(default=False)
