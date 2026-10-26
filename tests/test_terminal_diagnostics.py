"""
Unit tests for Diagnostics tool in app/diagnostics.py.
"""

import pytest
from app.diagnostics import run_diagnostics


@pytest.mark.asyncio
async def test_run_diagnostics_structure():
    results = await run_diagnostics()
    assert "timestamp" in results
    assert "overall_status" in results
    assert isinstance(results["checks"], list)
    assert len(results["checks"]) >= 5

    categories = [c["category"] for c in results["checks"]]
    assert "Environment" in categories
    assert "Dependencies" in categories
    assert "Configuration" in categories
    assert "Database" in categories
