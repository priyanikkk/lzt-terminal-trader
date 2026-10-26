"""
Configuration module for the LZT Market AI Multi-Agent Arbitrage System.
Loads settings from environment variables and provides strict typing and validation.
"""

from decimal import Decimal
from typing import Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Operating Modes & Safety Controls ---
    SIMULATION_MODE: bool = Field(
        default=True,
        description="When true, all purchases and listings are executed in a sandbox simulation."
    )
    LIVE_PURCHASE_ENABLED: bool = Field(
        default=False,
        description="Global master switch. If false, live purchases are strictly forbidden."
    )
    MANUAL_PURCHASE_CONFIRMATION: bool = Field(
        default=True,
        description="Requires explicit human operator confirmation before committing purchases in live mode."
    )
    MANUAL_RESALE_CONFIRMATION: bool = Field(
        default=False,
        description="Requires operator approval before publishing an account for resale."
    )

    # --- LZT Market API Credentials ---
    LZT_API_KEY: str = Field(
        default="",
        description="Official LZT Market Bearer API key. If empty, mock simulation data is used."
    )
    LZT_API_BASE_URL: str = Field(
        default="https://api.lzt.market",
        description="Base URL for LZT Market REST API."
    )
    LZT_REQUEST_TIMEOUT: float = Field(
        default=15.0,
        description="HTTP request timeout in seconds."
    )
    LZT_RATE_LIMIT_RPS: float = Field(
        default=3.0,
        description="Allowed requests per second to avoid HTTP 429 Too Many Requests."
    )

    # --- Telegram Integration ---
    TELEGRAM_BOT_TOKEN: str = Field(
        default="",
        description="Telegram bot token for operations alert and monitoring."
    )
    TELEGRAM_ADMIN_CHAT_ID: str = Field(
        default="",
        description="Telegram chat ID for system admin notifications."
    )

    # --- Financial Thresholds (Calculated using Decimal) ---
    MIN_NET_PROFIT: Decimal = Field(
        default=Decimal("50.0"),
        description="Minimum net profit in RUB required to consider an arbitrage opportunity."
    )
    MIN_ROI_PERCENT: Decimal = Field(
        default=Decimal("25.0"),
        description="Minimum ROI percentage (net profit / buy price * 100) required."
    )
    MAX_PURCHASE_PRICE: Decimal = Field(
        default=Decimal("350.0"),
        description="Maximum cost allowed for a single item purchase."
    )
    MAX_DAILY_BUDGET: Decimal = Field(
        default=Decimal("3000.0"),
        description="Maximum total spending limit allowed within a single 24-hour cycle."
    )
    MAX_ACTIVE_PURCHASES_PER_DAY: int = Field(
        default=10,
        description="Maximum number of successful purchases allowed per day."
    )
    MIN_CONFIDENCE_SCORE: float = Field(
        default=0.70,
        description="Minimum algorithmic / inspection confidence score (0.0 to 1.0) to proceed."
    )

    # --- Fee Rates ---
    BUY_FEE_PERCENT: Decimal = Field(
        default=Decimal("2.0"),
        description="Estimated buyer commission on purchase."
    )
    RESALE_FEE_PERCENT: Decimal = Field(
        default=Decimal("4.0"),
        description="Estimated seller commission on resale listing."
    )

    # --- Pluggable LLM Provider ---
    LLM_PROVIDER: Literal["mock", "openai", "anthropic", "gemini"] = Field(
        default="mock",
        description="LLM provider for advanced text analysis. Defaults to local heuristic mock."
    )
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL: str = Field(default="gpt-4o-mini")

    # --- System & DB ---
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///lzt_arbitrage.db",
        description="Async SQLite database connection string."
    )
    LOG_LEVEL: str = Field(default="INFO")
    SCAN_INTERVAL_SECONDS: int = Field(default=30)
    SYSTEM_HEALTH_CHECK_INTERVAL: int = Field(default=60)

    @field_validator("MIN_ROI_PERCENT", "MIN_NET_PROFIT", "MAX_PURCHASE_PRICE", "MAX_DAILY_BUDGET", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    def is_live_execution_allowed(self) -> bool:
        """Determines if real financial actions can be taken."""
        return self.LIVE_PURCHASE_ENABLED and not self.SIMULATION_MODE and bool(self.LZT_API_KEY.strip())


# Global singleton instance
settings = Settings()
