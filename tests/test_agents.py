"""
Unit tests for all specialized agents.
"""

import pytest
from decimal import Decimal
from models.messages import AgentMessage, TaskStatus
from agents.market_scanner import MarketScannerAgent
from agents.listing_inspector import ListingInspectorAgent
from agents.pricing import PricingAgent
from agents.risk_assessment import RiskAssessmentAgent
from agents.purchase_workflow import PurchaseWorkflowAgent
from agents.resale import ResaleAgent
from agents.telegram_integration import TelegramIntegrationAgent
from agents.finance import FinanceAgent
from agents.system_monitor import SystemMonitorAgent
from agents.qa import QAAgent
from config import settings


@pytest.mark.asyncio
async def test_market_scanner_agent():
    scanner = MarketScannerAgent()
    msg = AgentMessage(
        agent_id=scanner.agent_id,
        task_type="SCAN",
        input_data={"min_price": Decimal("10.0"), "max_price": Decimal("500.0")}
    )
    res_msg = await scanner.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data is not None
    assert res_msg.output_data.total_found > 0
    assert len(res_msg.output_data.candidates) > 0


@pytest.mark.asyncio
async def test_listing_inspector_clean(clean_profitable_listing):
    inspector = ListingInspectorAgent()
    msg = AgentMessage(
        agent_id=inspector.agent_id,
        task_type="INSPECT",
        input_data=clean_profitable_listing
    )
    res_msg = await inspector.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.is_valid is True
    assert res_msg.output_data.mandatory_traits_ok is True


@pytest.mark.asyncio
async def test_listing_inspector_rejects_spamblock(spamblock_listing):
    inspector = ListingInspectorAgent()
    msg = AgentMessage(
        agent_id=inspector.agent_id,
        task_type="INSPECT",
        input_data=spamblock_listing
    )
    res_msg = await inspector.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.is_valid is False
    assert any("SpamBlock" in r for r in res_msg.output_data.rejection_reasons)


@pytest.mark.asyncio
async def test_listing_inspector_rejects_prompt_injection(prompt_injection_listing):
    inspector = ListingInspectorAgent()
    msg = AgentMessage(
        agent_id=inspector.agent_id,
        task_type="INSPECT",
        input_data=prompt_injection_listing
    )
    res_msg = await inspector.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.is_valid is False
    assert any("prompt injection" in r.lower() for r in res_msg.output_data.rejection_reasons)


@pytest.mark.asyncio
async def test_pricing_agent_profitable(clean_profitable_listing):
    pricer = PricingAgent()
    msg = AgentMessage(
        agent_id=pricer.agent_id,
        task_type="PRICE",
        input_data=clean_profitable_listing
    )
    res_msg = await pricer.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    res = res_msg.output_data
    assert res.is_profitable is True
    assert res.net_profit >= settings.MIN_NET_PROFIT
    assert res.roi_percent >= settings.MIN_ROI_PERCENT
    assert res.buyer_fee > Decimal("0.0")
    assert res.seller_fee > Decimal("0.0")


@pytest.mark.asyncio
async def test_pricing_agent_unprofitable(overpriced_listing):
    pricer = PricingAgent()
    msg = AgentMessage(
        agent_id=pricer.agent_id,
        task_type="PRICE",
        input_data=overpriced_listing
    )
    res_msg = await pricer.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    res = res_msg.output_data
    assert res.is_profitable is False
    assert res.rejection_reason is not None


@pytest.mark.asyncio
async def test_risk_assessment_agent(clean_profitable_listing):
    inspector = ListingInspectorAgent()
    pricer = PricingAgent()
    risk_agent = RiskAssessmentAgent()

    insp_out = (await inspector.execute(AgentMessage(agent_id=inspector.agent_id, task_type="INSPECT", input_data=clean_profitable_listing))).output_data
    price_out = (await pricer.execute(AgentMessage(agent_id=pricer.agent_id, task_type="PRICE", input_data=clean_profitable_listing))).output_data

    risk_msg = AgentMessage(
        agent_id=risk_agent.agent_id,
        task_type="RISK",
        input_data=(clean_profitable_listing, insp_out, price_out)
    )
    res_msg = await risk_agent.execute(risk_msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.can_proceed is True
    assert res_msg.output_data.risk_level in ["LOW", "MEDIUM"]


@pytest.mark.asyncio
async def test_purchase_workflow_simulated(clean_profitable_listing):
    inspector = ListingInspectorAgent()
    pricer = PricingAgent()
    risk_agent = RiskAssessmentAgent()
    buyer = PurchaseWorkflowAgent()

    insp_out = (await inspector.execute(AgentMessage(agent_id=inspector.agent_id, task_type="INSPECT", input_data=clean_profitable_listing))).output_data
    price_out = (await pricer.execute(AgentMessage(agent_id=pricer.agent_id, task_type="PRICE", input_data=clean_profitable_listing))).output_data
    risk_out = (await risk_agent.execute(AgentMessage(agent_id=risk_agent.agent_id, task_type="RISK", input_data=(clean_profitable_listing, insp_out, price_out)))).output_data

    buy_msg = AgentMessage(
        agent_id=buyer.agent_id,
        task_type="BUY",
        input_data=(clean_profitable_listing, price_out, risk_out)
    )
    res_msg = await buyer.execute(buy_msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.status == "SIMULATED"
    assert res_msg.output_data.price_paid == clean_profitable_listing.price


@pytest.mark.asyncio
async def test_resale_agent(clean_profitable_listing):
    pricer = PricingAgent()
    buyer = PurchaseWorkflowAgent()
    reseller = ResaleAgent()

    price_out = (await pricer.execute(AgentMessage(agent_id=pricer.agent_id, task_type="PRICE", input_data=clean_profitable_listing))).output_data
    from models.transactions import PurchaseResult
    fake_purchase = PurchaseResult(
        item_id=clean_profitable_listing.item_id,
        order_id="test_ord_123",
        status="SIMULATED",
        price_paid=clean_profitable_listing.price,
        is_simulation=True
    )

    resale_msg = AgentMessage(
        agent_id=reseller.agent_id,
        task_type="RESALE",
        input_data=(clean_profitable_listing, fake_purchase, price_out)
    )
    res_msg = await reseller.execute(resale_msg)
    assert res_msg.status == TaskStatus.SUCCESS
    assert res_msg.output_data.status == "LISTED"
    assert "Telegram RU" in res_msg.output_data.title
    assert res_msg.output_data.listed_price == price_out.estimated_resale_price


@pytest.mark.asyncio
async def test_finance_agent():
    financer = FinanceAgent()
    await financer.record_purchase(
        item_id=9901,
        amount=Decimal("100.0"),
        buyer_fee=Decimal("2.0"),
        is_simulation=True
    )
    await financer.record_sale(
        item_id=9901,
        amount=Decimal("180.0"),
        seller_fee=Decimal("7.2"),
        is_simulation=True
    )

    msg = AgentMessage(agent_id=financer.agent_id, task_type="AUDIT", input_data={"is_simulation": True})
    res_msg = await financer.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    rep = res_msg.output_data
    assert rep.total_purchases_count == 1
    assert rep.total_sales_count == 1
    assert rep.total_invested == Decimal("100.0")
    assert rep.total_revenue == Decimal("180.0")
    # Net profit: 180 - 100 - 2.0 - 7.2 = 70.80
    assert rep.net_profit == Decimal("70.80")
    assert rep.roi_total_percent == Decimal("70.80")


@pytest.mark.asyncio
async def test_system_monitor_agent():
    monitor = SystemMonitorAgent()
    msg = AgentMessage(agent_id=monitor.agent_id, task_type="HEALTH", input_data={})
    res_msg = await monitor.execute(msg)
    assert res_msg.status == TaskStatus.SUCCESS
    rep = res_msg.output_data
    assert rep["api_status"] == "HEALTHY"
    assert rep["database_status"] == "HEALTHY"
    assert rep["circuit_broken"] is False
