"""
Financial models and ledger contracts. All calculations strictly use Decimal.
"""

from decimal import Decimal
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum
import uuid
from pydantic import BaseModel, Field


class FinanceEntryType(str, Enum):
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    BUY_FEE = "BUY_FEE"
    SALE_FEE = "SALE_FEE"
    REFUND = "REFUND"
    ADJUSTMENT = "ADJUSTMENT"


class FinanceEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entry_type: FinanceEntryType
    amount: Decimal = Field(description="Strict Decimal amount")
    currency: str = Field(default="RUB")
    item_id: Optional[int] = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = Field(default="")
    is_simulation: bool = Field(default=True)


class FinanceReportResult(BaseModel):
    period_start: datetime
    period_end: datetime
    total_purchases_count: int = Field(default=0)
    total_invested: Decimal = Field(default=Decimal("0.0"))
    total_sales_count: int = Field(default=0)
    total_revenue: Decimal = Field(default=Decimal("0.0"))
    total_fees_paid: Decimal = Field(default=Decimal("0.0"))
    net_profit: Decimal = Field(default=Decimal("0.0"))
    roi_total_percent: Decimal = Field(default=Decimal("0.0"))
    daily_budget_limit: Decimal = Field(default=Decimal("0.0"))
    budget_spent_today: Decimal = Field(default=Decimal("0.0"))
    budget_remaining_today: Decimal = Field(default=Decimal("0.0"))
    open_inventory_cost: Decimal = Field(default=Decimal("0.0"))
    discrepancies: List[str] = Field(default_factory=list)
