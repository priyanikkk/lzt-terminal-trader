"""
Transaction models for purchase and resale operations.
"""

from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid
from pydantic import BaseModel, Field


class PurchaseResult(BaseModel):
    item_id: int
    order_id: Optional[str] = Field(default=None, description="LZT transaction or order ID")
    status: str = Field(description="SIMULATED, SUCCESS, PENDING_VERIFICATION, FAILED, UNKNOWN")
    price_paid: Decimal
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_simulation: bool = Field(default=True)
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ResaleResult(BaseModel):
    resale_item_id: Optional[str] = Field(default=None, description="New item ID created on LZT Market")
    source_item_id: int = Field(description="Original purchased lot item_id")
    status: str = Field(description="DRAFT, LISTED, SOLD, FAILED")
    listed_price: Decimal
    title: str
    description: str
    listed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_simulation: bool = Field(default=True)
    error_message: Optional[str] = None
