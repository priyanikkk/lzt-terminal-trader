"""
Configuration module for LZT Market AI Multi-Agent Arbitrage System (LZT Terminal Trader).
Loads settings from .env file, supports environment variables, and provides strict validation.
"""

from decimal import Decimal
import os
from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Mode & Safety ---
    APP_MODE: Literal["simulation", "live"] = Field(
        default="simulation",
        description="Operating mode: 'simulation' (sandbox) or 'live' (real API transactions)."
    )
    SIMULATION_MODE: bool = Field(
        default=True,
        description="Compatibility flag. Set to True if APP_MODE == 'simulation'."
    )
    LIVE_PURCHASE_ENABLED: bool = Field(
        default=False,
        description="Global kill-switch for live purchases. Must be True and APP_MODE == 'live' to buy."
    )
    MANUAL_PURCHASE_CONFIRMATION: bool = Field(
        default=True,
        description="Require explicit confirmation from the operator before purchasing."
    )
    MANUAL_RESALE_CONFIRMATION: bool = Field(
        default=False,
        description="Require operator confirmation before publishing a resale listing."
    )

    # --- LZT Market API Credentials ---
    LZT_API_TOKEN: str = Field(
        default="",
        description="Official LZT Market Bearer API token."
    )
    LZT_API_KEY: str = Field(
        default="",
        description="Alias for LZT_API_TOKEN."
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
        description="Allowed requests per second."
    )

    # --- Telegram Notification Settings (Optional) ---
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_ADMIN_CHAT_ID: str = Field(default="")

    # --- Financial Thresholds (Calculated using Decimal) ---
    MIN_NET_PROFIT: Decimal = Field(
        default=Decimal("50.0"),
        description="Minimum net profit in RUB required for an arbitrage opportunity."
    )
    MIN_ROI_PERCENT: Decimal = Field(
        default=Decimal("25.0"),
        description="Minimum ROI percentage required (net profit / investment * 100)."
    )
    MAX_PURCHASE_PRICE: Decimal = Field(
        default=Decimal("350.0"),
        description="Maximum allowed price in RUB for a single account purchase."
    )
    MAX_DAILY_BUDGET: Decimal = Field(
        default=Decimal("3000.0"),
        description="Maximum daily spending limit in RUB across all purchases."
    )
    MAX_ACTIVE_PURCHASES_PER_DAY: int = Field(
        default=10,
        description="Maximum number of purchases allowed per 24 hours."
    )
    MIN_CONFIDENCE_SCORE: float = Field(
        default=0.70,
        description="Minimum confidence score (0.0 to 1.0) to approve an opportunity."
    )

    # --- Fee Rates ---
    BUY_FEE_PERCENT: Decimal = Field(
        default=Decimal("2.0"),
        description="Estimated buyer commission percentage on purchase."
    )
    RESALE_FEE_PERCENT: Decimal = Field(
        default=Decimal("4.0"),
        description="Estimated seller commission percentage on resale listing."
    )

    # --- AI / LLM Configuration ---
    LLM_PROVIDER: Literal["local", "openai", "anthropic", "gemini", "mock"] = Field(
        default="local",
        description="AI text analysis provider: 'local' (built-in rule/heuristic engine), 'openai', 'gemini', 'anthropic'."
    )
    LLM_API_KEY: str = Field(default="")
    LLM_MODEL: str = Field(default="gpt-4o-mini")

    # --- Storage & Paths ---
    DATABASE_PATH: str = Field(default="data/trader.db")
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///lzt_arbitrage.db")
    LOGS_PATH: str = Field(default="logs/trader.log")
    LOG_LEVEL: str = Field(default="INFO")

    @field_validator("MIN_ROI_PERCENT", "MIN_NET_PROFIT", "MAX_PURCHASE_PRICE", "MAX_DAILY_BUDGET", "BUY_FEE_PERCENT", "RESALE_FEE_PERCENT", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    def get_token(self) -> str:
        """Returns the configured API token (checking LZT_API_TOKEN or LZT_API_KEY)."""
        return (self.LZT_API_TOKEN or self.LZT_API_KEY).strip()

    def is_configured(self) -> bool:
        """Returns True if .env exists and has been configured."""
        return ENV_PATH.exists()

    def is_live_allowed(self) -> bool:
        """Determines if real financial actions can be taken via the live API."""
        return (
            self.APP_MODE == "live"
            and not self.SIMULATION_MODE
            and self.LIVE_PURCHASE_ENABLED
            and bool(self.get_token())
        )


def load_settings() -> Settings:
    """Loads settings instance from environment or .env file."""
    s = Settings()
    # Synchronize simulation mode flags
    if s.APP_MODE == "simulation":
        s.SIMULATION_MODE = True
        s.LIVE_PURCHASE_ENABLED = False
    elif s.APP_MODE == "live":
        s.SIMULATION_MODE = False
    return s


settings = load_settings()


def save_env_file(config_dict: dict) -> None:
    """
    Writes or updates the .env file with given key-value pairs.
    Preserves other entries if present.
    """
    current_lines = []
    if ENV_PATH.exists():
        current_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    existing_keys = {}
    updated_lines = []

    for line in current_lines:
        line_clean = line.strip()
        if line_clean and not line_clean.startswith("#") and "=" in line_clean:
            key, val = line_clean.split("=", 1)
            key = key.strip()
            if key in config_dict:
                updated_lines.append(f"{key}={config_dict[key]}")
                existing_keys[key] = True
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    for k, v in config_dict.items():
        if k not in existing_keys:
            updated_lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    # Reload global settings
    global settings
    settings = load_settings()
