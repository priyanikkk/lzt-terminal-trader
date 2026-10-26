"""
System Diagnostics Tool for LZT Terminal Trader.
Performs thorough checks of Python runtime, libraries, configuration,
SQLite storage, network latency to LZT API, and API token validity.
"""

import asyncio
from decimal import Decimal
import importlib
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any, Dict, List
import httpx

from config import settings
from app.database import db


async def run_diagnostics() -> Dict[str, Any]:
    """
    Executes a comprehensive system diagnostic check.
    Returns structured results for terminal rendering.
    """
    results: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_status": "OK",
        "checks": [],
    }

    # 1. Python Environment Check
    py_version = sys.version.split()[0]
    is_py_ok = sys.version_info >= (3, 10)
    results["checks"].append({
        "category": "Environment",
        "name": "Python Version",
        "status": "PASS" if is_py_ok else "FAIL",
        "details": f"Python {py_version} on {platform.system()} {platform.release()}",
    })

    # 2. Dependencies Check
    required_libs = ["rich", "httpx", "pydantic", "aiosqlite", "sqlalchemy"]
    missing_libs = []
    for lib in required_libs:
        try:
            importlib.import_module(lib)
        except ImportError:
            missing_libs.append(lib)

    if not missing_libs:
        results["checks"].append({
            "category": "Dependencies",
            "name": "Core Libraries",
            "status": "PASS",
            "details": f"All {len(required_libs)} core packages installed and accessible.",
        })
    else:
        results["checks"].append({
            "category": "Dependencies",
            "name": "Core Libraries",
            "status": "FAIL",
            "details": f"Missing packages: {', '.join(missing_libs)}",
        })
        results["overall_status"] = "ERROR"

    # 3. Configuration & .env Check
    env_file = Path(".env")
    if env_file.exists():
        token_len = len(settings.get_token())
        token_preview = f"{token_len} chars" if token_len > 0 else "None (Empty)"
        results["checks"].append({
            "category": "Configuration",
            "name": ".env Configuration",
            "status": "PASS",
            "details": f"Mode: {settings.APP_MODE.upper()}, Token: {token_preview}",
        })
    else:
        results["checks"].append({
            "category": "Configuration",
            "name": ".env Configuration",
            "status": "WARN",
            "details": ".env file not found. Running with default fallback configuration.",
        })

    # 4. Database Check
    try:
        await db.init_db()
        test_balance = await db.get_current_balance()
        results["checks"].append({
            "category": "Database",
            "name": "SQLite Integrity",
            "status": "PASS",
            "details": f"Database at {db.db_path} is healthy. Current balance: {test_balance:.2f} RUB.",
        })
    except Exception as e:
        results["checks"].append({
            "category": "Database",
            "name": "SQLite Integrity",
            "status": "FAIL",
            "details": f"Database error: {str(e)}",
        })
        results["overall_status"] = "ERROR"

    # 5. Network Connectivity to LZT API
    base_url = settings.LZT_API_BASE_URL.rstrip("/")
    start_t = time.perf_counter()
    network_ok = False
    ping_ms = 0.0
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(base_url)
            elapsed = (time.perf_counter() - start_t) * 1000
            ping_ms = round(elapsed, 1)
            network_ok = True
            results["checks"].append({
                "category": "Network",
                "name": "LZT API Reachability",
                "status": "PASS",
                "details": f"Connected to {base_url} ({ping_ms} ms, HTTP {resp.status_code})",
            })
    except Exception as e:
        results["checks"].append({
            "category": "Network",
            "name": "LZT API Reachability",
            "status": "WARN" if settings.APP_MODE == "simulation" else "FAIL",
            "details": f"Unable to reach {base_url}: {str(e)}",
        })
        if settings.APP_MODE != "simulation":
            results["overall_status"] = "WARNING"

    # 6. API Token Validity
    if settings.APP_MODE == "simulation":
        results["checks"].append({
            "category": "Authentication",
            "name": "LZT API Token",
            "status": "INFO",
            "details": "SIMULATION MODE: Sandbox active. Real transactions disabled.",
        })
    else:
        token = settings.get_token()
        if not token:
            results["checks"].append({
                "category": "Authentication",
                "name": "LZT API Token",
                "status": "FAIL",
                "details": "Mode is LIVE but LZT_API_TOKEN is empty. Real actions will fail.",
            })
            results["overall_status"] = "ERROR"
        else:
            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{base_url}/me", headers=headers)
                    if resp.status_code == 200:
                        results["checks"].append({
                            "category": "Authentication",
                            "name": "LZT API Token",
                            "status": "PASS",
                            "details": "Token verified valid by LZT Market API.",
                        })
                    else:
                        results["checks"].append({
                            "category": "Authentication",
                            "name": "LZT API Token",
                            "status": "FAIL",
                            "details": f"Token rejected by LZT Market (HTTP {resp.status_code}).",
                        })
                        results["overall_status"] = "ERROR"
            except Exception as e:
                results["checks"].append({
                    "category": "Authentication",
                    "name": "LZT API Token",
                    "status": "WARN",
                    "details": f"Token check network failure: {str(e)}",
                })

    return results
