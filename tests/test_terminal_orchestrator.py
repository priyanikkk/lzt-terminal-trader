"""
Unit tests for Orchestrator multi-agent pipeline in app/orchestrator.py.
"""

import pytest

from app.database import db
from app.orchestrator import orchestrator


@pytest.mark.asyncio
async def test_orchestrator_pipeline_cycle():
    await db.init_db()

    summary = await orchestrator.run_pipeline_cycle(auto_purchase=False)
    assert summary["status"] == "success"
    assert summary["scanned_candidates"] > 0
    assert summary["pricing_approved"] >= 0
    assert "financial_snapshot" in summary
    assert "current_balance" in summary["financial_snapshot"]
