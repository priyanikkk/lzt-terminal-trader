"""
Async repository providing clean data access for listings, transactions, ledger, and logs.
"""

from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.db import AsyncSessionLocal, init_db
from database.models import ListingRecord, TransactionRecord, LedgerRecord, AgentLogRecord, SystemMetricRecord
from models.listings import TelegramAccountListing
from models.transactions import PurchaseResult, ResaleResult
from models.finance import FinanceEntry


class Repository:
    """Async database repository for persistence."""

    async def init(self):
        await init_db()

    async def upsert_listing(self, item: TelegramAccountListing) -> ListingRecord:
        async with AsyncSessionLocal() as session:
            stmt = select(ListingRecord).where(ListingRecord.item_id == item.item_id)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()

            if not record:
                record = ListingRecord(
                    item_id=item.item_id,
                    title=item.title,
                    description=item.description,
                    price=item.price,
                    currency=item.currency,
                    seller_id=item.seller_id,
                    seller_username=item.seller_username,
                    seller_rating=item.seller_rating,
                    origin=item.origin,
                    country_code=item.country_code,
                    spam_block=item.spam_block,
                    two_step_auth=item.two_step_auth,
                    channels_count=item.channels_count,
                    age_days=item.age_days,
                    format=item.format,
                    url=item.url,
                    raw_payload=item.raw_data,
                    state="DISCOVERED"
                )
                session.add(record)
            else:
                record.price = item.price
                record.title = item.title
                record.description = item.description
                record.raw_payload = item.raw_data

            await session.commit()
            await session.refresh(record)
            return record

    async def get_listing(self, item_id: int) -> Optional[ListingRecord]:
        async with AsyncSessionLocal() as session:
            stmt = select(ListingRecord).where(ListingRecord.item_id == item_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def get_listings_by_state(self, state: str, limit: int = 50) -> List[ListingRecord]:
        async with AsyncSessionLocal() as session:
            stmt = select(ListingRecord).where(ListingRecord.state == state).limit(limit)
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def update_listing_state(
        self,
        item_id: int,
        state: str,
        is_valid: Optional[bool] = None,
        inspection_reasons: Optional[List[str]] = None,
        estimated_resale_price: Optional[Decimal] = None,
        estimated_net_profit: Optional[Decimal] = None,
        estimated_roi: Optional[Decimal] = None,
        risk_level: Optional[str] = None,
        risk_reasons: Optional[List[str]] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(ListingRecord).where(ListingRecord.item_id == item_id)
            res = await session.execute(stmt)
            record = res.scalar_one_or_none()
            if record:
                record.state = state
                if is_valid is not None:
                    record.is_valid = is_valid
                if inspection_reasons is not None:
                    record.inspection_reasons = inspection_reasons
                if estimated_resale_price is not None:
                    record.estimated_resale_price = estimated_resale_price
                if estimated_net_profit is not None:
                    record.estimated_net_profit = estimated_net_profit
                if estimated_roi is not None:
                    record.estimated_roi = estimated_roi
                if risk_level is not None:
                    record.risk_level = risk_level
                if risk_reasons is not None:
                    record.risk_reasons = risk_reasons
                await session.commit()

    async def save_purchase_transaction(self, result: PurchaseResult) -> TransactionRecord:
        async with AsyncSessionLocal() as session:
            record = TransactionRecord(
                item_id=result.item_id,
                order_id=result.order_id,
                idempotency_key=result.idempotency_key,
                transaction_type="PURCHASE",
                status=result.status,
                price=result.price_paid,
                is_simulation=result.is_simulation,
                details=result.details,
                error_message=result.error_message
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def save_resale_transaction(self, result: ResaleResult) -> TransactionRecord:
        async with AsyncSessionLocal() as session:
            record = TransactionRecord(
                item_id=result.source_item_id,
                order_id=result.resale_item_id,
                idempotency_key=result.idempotency_key,
                transaction_type="RESALE",
                status=result.status,
                price=result.listed_price,
                is_simulation=result.is_simulation,
                details={"title": result.title, "description": result.description},
                error_message=result.error_message
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def find_transaction_by_idempotency(self, idempotency_key: str) -> Optional[TransactionRecord]:
        async with AsyncSessionLocal() as session:
            stmt = select(TransactionRecord).where(TransactionRecord.idempotency_key == idempotency_key)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def record_ledger_entry(self, entry: FinanceEntry) -> LedgerRecord:
        async with AsyncSessionLocal() as session:
            record = LedgerRecord(
                entry_id=entry.entry_id,
                entry_type=entry.entry_type.value,
                amount=entry.amount,
                currency=entry.currency,
                item_id=entry.item_id,
                is_simulation=entry.is_simulation,
                description=entry.description
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_daily_spent(self, is_simulation: bool = True) -> Decimal:
        """Calculates total spend in last 24 hours."""
        since = datetime.now(timezone.utc) - timedelta(days=1)
        async with AsyncSessionLocal() as session:
            stmt = select(func.sum(LedgerRecord.amount)).where(
                LedgerRecord.entry_type == "PURCHASE",
                LedgerRecord.is_simulation == is_simulation,
                LedgerRecord.created_at >= since
            )
            res = await session.execute(stmt)
            total = res.scalar()
            return Decimal(str(total)) if total is not None else Decimal("0.0")

    async def get_all_ledger_entries(self, is_simulation: bool = True) -> List[LedgerRecord]:
        async with AsyncSessionLocal() as session:
            stmt = select(LedgerRecord).where(
                LedgerRecord.is_simulation == is_simulation
            ).order_by(LedgerRecord.created_at.asc())
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def log_agent_action(
        self,
        task_id: str,
        agent_id: str,
        task_type: str,
        status: str,
        execution_time_ms: float,
        errors: List[str]
    ) -> None:
        async with AsyncSessionLocal() as session:
            record = AgentLogRecord(
                task_id=task_id,
                agent_id=agent_id,
                task_type=task_type,
                status=status,
                execution_time_ms=execution_time_ms,
                errors=errors
            )
            session.add(record)
            await session.commit()

    async def get_recent_agent_logs(self, limit: int = 50) -> List[AgentLogRecord]:
        async with AsyncSessionLocal() as session:
            stmt = select(AgentLogRecord).order_by(AgentLogRecord.created_at.desc()).limit(limit)
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def record_system_metric(self, name: str, value: float, status: str, details: Dict[str, Any]) -> None:
        async with AsyncSessionLocal() as session:
            metric = SystemMetricRecord(
                metric_name=name,
                metric_value=value,
                status=status,
                details=details
            )
            session.add(metric)
            await session.commit()


# Global repository instance
repository = Repository()
