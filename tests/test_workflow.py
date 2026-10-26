"""
End-to-end integration tests for the Arbitrage Workflow Pipeline.
"""

import pytest
from decimal import Decimal
from orchestrator.workflow import workflow_pipeline
from core.state_machine import ListingState
from database.repository import repository
from models.listings import TelegramAccountListing


@pytest.mark.asyncio
async def test_workflow_clean_listing_success(clean_profitable_listing):
    summary = await workflow_pipeline.process_listing(clean_profitable_listing)
    assert summary.final_state == ListingState.LISTED
    assert summary.purchase is not None
    assert summary.purchase.status == "SIMULATED"
    assert summary.resale is not None
    assert summary.resale.status == "LISTED"

    # Verify database persistence
    db_record = await repository.get_listing(clean_profitable_listing.item_id)
    assert db_record is not None
    assert db_record.state == "LISTED"


@pytest.mark.asyncio
async def test_workflow_spamblock_rejected(spamblock_listing):
    summary = await workflow_pipeline.process_listing(spamblock_listing)
    assert summary.final_state == ListingState.REJECTED
    assert "SpamBlock" in summary.aborted_reason


@pytest.mark.asyncio
async def test_workflow_prompt_injection_rejected(prompt_injection_listing):
    summary = await workflow_pipeline.process_listing(prompt_injection_listing)
    assert summary.final_state == ListingState.REJECTED
    assert "prompt injection" in summary.aborted_reason.lower()


@pytest.mark.asyncio
async def test_workflow_overpriced_rejected(overpriced_listing):
    summary = await workflow_pipeline.process_listing(overpriced_listing)
    assert summary.final_state == ListingState.REJECTED
    assert "exceeds max budget cap" in summary.aborted_reason or "below minimum" in summary.aborted_reason


@pytest.mark.asyncio
async def test_workflow_prevents_duplicate_purchase(clean_profitable_listing):
    # 1. First run succeeds
    first_summary = await workflow_pipeline.process_listing(clean_profitable_listing)
    assert first_summary.final_state == ListingState.LISTED

    # 2. Second run on same item must be blocked
    second_summary = await workflow_pipeline.process_listing(clean_profitable_listing)
    assert second_summary.final_state == ListingState.REJECTED
    assert "already been purchased" in second_summary.aborted_reason
