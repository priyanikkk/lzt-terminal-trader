"""
SQLite Database Layer for LZT Terminal Trader using aiosqlite.
Manages listings, purchases, resale drafts, financial ledger, and system logs in data/trader.db.
"""

from contextlib import asynccontextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
import aiosqlite

from config import settings

DB_DIR = Path("data")
DB_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_PATH = Path(settings.DATABASE_PATH)


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init_db(self) -> None:
        """Creates tables if they do not exist and populates initial simulation balance if empty."""
        async with self.get_connection() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER UNIQUE,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT DEFAULT 'rub',
                    country TEXT DEFAULT 'UNKNOWN',
                    has_2fa INTEGER DEFAULT 0,
                    spamblock INTEGER DEFAULT 0,
                    format_type TEXT DEFAULT 'session+json',
                    risk_level TEXT DEFAULT 'LOW',
                    confidence REAL DEFAULT 0.85,
                    status TEXT DEFAULT 'candidate',
                    raw_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS purchases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER UNIQUE,
                    title TEXT NOT NULL,
                    buy_price REAL NOT NULL,
                    fee REAL NOT NULL,
                    status TEXT DEFAULT 'completed',
                    credentials TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS resale_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    purchase_id INTEGER,
                    item_id INTEGER,
                    target_price REAL NOT NULL,
                    original_price REAL NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'draft',
                    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tx_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    description TEXT NOT NULL,
                    reference_id TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            await conn.commit()

            # Seed initial balance if ledger is brand new
            cursor = await conn.execute("SELECT COUNT(*) FROM ledger_entries")
            row = await cursor.fetchone()
            if row and row[0] == 0:
                await conn.execute(
                    """
                    INSERT INTO ledger_entries (tx_type, amount, balance_after, description, reference_id)
                    VALUES ('deposit', 10000.0, 10000.0, 'Initial Sandbox Balance', 'INIT-DEPOSIT')
                    """
                )
                await conn.commit()

    # --- Listings Operations ---
    async def save_listing(self, item: Dict[str, Any]) -> None:
        async with self.get_connection() as conn:
            raw_str = json.dumps(item.get("raw_data", {}), default=str)
            await conn.execute(
                """
                INSERT INTO listings (item_id, title, price, currency, country, has_2fa, spamblock, format_type, risk_level, confidence, status, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    title=excluded.title,
                    price=excluded.price,
                    risk_level=excluded.risk_level,
                    confidence=excluded.confidence,
                    status=excluded.status
                """,
                (
                    int(item.get("item_id", 0)),
                    item.get("title", "Untitled"),
                    float(item.get("price", 0.0)),
                    item.get("currency", "rub"),
                    item.get("country", "UNKNOWN"),
                    1 if item.get("has_2fa") else 0,
                    1 if item.get("spamblock") else 0,
                    item.get("format_type", "session+json"),
                    item.get("risk_level", "LOW"),
                    float(item.get("confidence", 0.85)),
                    item.get("status", "candidate"),
                    raw_str,
                )
            )
            await conn.commit()

    async def get_listings(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            if status:
                cursor = await conn.execute(
                    "SELECT * FROM listings WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor = await conn.execute(
                    "SELECT * FROM listings ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_listing_by_item_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT * FROM listings WHERE item_id = ?", (item_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    # --- Purchases Operations ---
    async def record_purchase(
        self,
        item_id: int,
        title: str,
        price: Decimal,
        fee: Decimal,
        status: str = "completed",
        credentials: str = ""
    ) -> int:
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO purchases (item_id, title, buy_price, fee, status, credentials)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item_id, title, float(price), float(fee), status, credentials)
            )
            purchase_id = cursor.lastrowid
            # Update listing status if exists
            await conn.execute("UPDATE listings SET status = 'purchased' WHERE item_id = ?", (item_id,))
            await conn.commit()

            # Record in ledger
            total_spent = price + fee
            current_bal = await self.get_current_balance()
            new_bal = current_bal - total_spent
            await conn.execute(
                """
                INSERT INTO ledger_entries (tx_type, amount, balance_after, description, reference_id)
                VALUES ('purchase', ?, ?, ?, ?)
                """,
                (float(-total_spent), float(new_bal), f"Purchase lot #{item_id}: {title}", f"BUY-{item_id}")
            )
            await conn.commit()
            return purchase_id

    async def get_purchases(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT * FROM purchases ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def is_item_purchased(self, item_id: int) -> bool:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT id FROM purchases WHERE item_id = ?", (item_id,))
            row = await cursor.fetchone()
            return bool(row)

    # --- Resale Operations ---
    async def record_resale(
        self,
        purchase_id: int,
        item_id: int,
        target_price: Decimal,
        original_price: Decimal,
        title: str,
        description: str,
        status: str = "draft"
    ) -> int:
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO resale_items (purchase_id, item_id, target_price, original_price, title, description, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (purchase_id, item_id, float(target_price), float(original_price), title, description, status)
            )
            resale_id = cursor.lastrowid
            await conn.commit()
            return resale_id

    async def get_resale_items(self, status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            if status:
                cursor = await conn.execute(
                    "SELECT * FROM resale_items WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor = await conn.execute("SELECT * FROM resale_items ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_resale_status(self, resale_id: int, status: str) -> None:
        async with self.get_connection() as conn:
            await conn.execute("UPDATE resale_items SET status = ? WHERE id = ?", (status, resale_id))
            await conn.commit()

    # --- Ledger & Financial Operations ---
    async def get_current_balance(self) -> Decimal:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT balance_after FROM ledger_entries ORDER BY id DESC LIMIT 1")
            row = await cursor.fetchone()
            if row:
                return Decimal(str(row[0]))
            return Decimal("10000.0")

    async def get_spent_today(self) -> Decimal:
        async with self.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT SUM(ABS(amount)) FROM ledger_entries
                WHERE tx_type = 'purchase'
                AND DATE(created_at) = DATE('now')
                """
            )
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return Decimal(str(row[0]))
            return Decimal("0.0")

    async def get_ledger_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            cursor = await conn.execute("SELECT * FROM ledger_entries ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def add_ledger_entry(self, tx_type: str, amount: Decimal, description: str, reference_id: str = "") -> Decimal:
        async with self.get_connection() as conn:
            current_bal = await self.get_current_balance()
            new_bal = current_bal + amount
            await conn.execute(
                """
                INSERT INTO ledger_entries (tx_type, amount, balance_after, description, reference_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tx_type, float(amount), float(new_bal), description, reference_id)
            )
            await conn.commit()
            return new_bal

    # --- Logging Operations ---
    async def add_log(self, level: str, message: str, module: str = "") -> None:
        async with self.get_connection() as conn:
            await conn.execute(
                "INSERT INTO logs (level, message, module) VALUES (?, ?, ?)",
                (level.upper(), message, module)
            )
            await conn.commit()

    async def get_recent_logs(self, level: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            if level:
                cursor = await conn.execute(
                    "SELECT * FROM logs WHERE level = ? ORDER BY id DESC LIMIT ?",
                    (level.upper(), limit)
                )
            else:
                cursor = await conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


db = Database()
