"""
SQLAlchemy ORM models for persistent storage.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, Numeric
)
from database.db import Base


class ListingRecord(Base):
    __tablename__ = "listings"

    item_id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="RUB")
    seller_id = Column(Integer, default=0, index=True)
    seller_username = Column(String(100), default="")
    seller_rating = Column(Float, default=0.0)
    origin = Column(String(50), default="autoreg")
    country_code = Column(String(10), default="RU")
    spam_block = Column(Boolean, default=False)
    two_step_auth = Column(Boolean, default=False)
    channels_count = Column(Integer, default=0)
    age_days = Column(Integer, default=0)
    format = Column(String(30), default="tdata")
    url = Column(String(500), default="")

    # Arbitrage State Machine
    state = Column(String(50), default="DISCOVERED", index=True)
    is_valid = Column(Boolean, default=False)
    inspection_reasons = Column(JSON, default=list)
    estimated_resale_price = Column(Numeric(12, 2), nullable=True)
    estimated_net_profit = Column(Numeric(12, 2), nullable=True)
    estimated_roi = Column(Numeric(12, 2), nullable=True)
    risk_level = Column(String(20), default="UNKNOWN")
    risk_reasons = Column(JSON, default=list)

    first_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    raw_payload = Column(JSON, default=dict)


class TransactionRecord(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, index=True, nullable=False)
    order_id = Column(String(100), nullable=True, index=True)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=False)
    transaction_type = Column(String(20), default="PURCHASE")  # PURCHASE or RESALE
    status = Column(String(50), nullable=False, index=True)
    price = Column(Numeric(12, 2), nullable=False)
    is_simulation = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    details = Column(JSON, default=dict)
    error_message = Column(Text, nullable=True)


class LedgerRecord(Base):
    __tablename__ = "ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_id = Column(String(100), unique=True, index=True, nullable=False)
    entry_type = Column(String(30), nullable=False, index=True)  # PURCHASE, SALE, BUY_FEE, etc.
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(10), default="RUB")
    item_id = Column(Integer, nullable=True, index=True)
    is_simulation = Column(Boolean, default=True)
    description = Column(String(255), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AgentLogRecord(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), index=True, nullable=False)
    agent_id = Column(String(100), index=True, nullable=False)
    task_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    execution_time_ms = Column(Float, default=0.0)
    errors = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class SystemMetricRecord(Base):
    __tablename__ = "system_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    status = Column(String(30), default="HEALTHY")
    details = Column(JSON, default=dict)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
