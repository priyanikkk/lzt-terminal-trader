"""
Unit tests for LZTMarketClient in app/api_client.py.
"""

import pytest

from app.api_client import api_client


@pytest.mark.asyncio
async def test_api_client_simulation_connection():
    success, msg, data = await api_client.test_connection()
    assert success is True
    assert "SIMULATION MODE" in msg
    assert data["mode"] == "simulation"
    assert "user" in data


@pytest.mark.asyncio
async def test_api_client_simulation_profile():
    profile = await api_client.get_profile()
    assert profile["mode"] == "simulation"
    assert profile["balance"] == 10000.0


@pytest.mark.asyncio
async def test_api_client_simulation_search():
    results = await api_client.search_listings(country="DE")
    assert len(results) > 0
    assert all(r["country"] == "DE" for r in results)


@pytest.mark.asyncio
async def test_api_client_check_item():
    ok, msg = await api_client.check_item(9812401)
    assert ok is True

    # Bad item with 2FA + spamblock in sandbox
    bad_ok, bad_msg = await api_client.check_item(9812406)
    assert bad_ok is False
    assert "failed" in bad_msg.lower()
