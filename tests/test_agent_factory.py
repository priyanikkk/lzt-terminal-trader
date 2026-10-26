"""
Tests for Section 3 — Dynamic Agent Creation, AST Security Auditing, and Rollback.
"""

import os
import pytest
from orchestrator.agent_factory import AgentFactory, AgentSpecification, AgentFactorySecurityError
from core.permissions import Permission, PermissionDeniedError
from orchestrator.registry import agent_registry


@pytest.fixture
def clean_factory(tmp_path):
    output_dir = str(tmp_path / "dynamic_agents")
    tests_dir = str(tmp_path / "tests_dynamic")
    docs_dir = str(tmp_path / "docs_agents")
    return AgentFactory(output_dir=output_dir, tests_dir=tests_dir, docs_dir=docs_dir)


@pytest.mark.asyncio
async def test_agent_factory_successful_creation(clean_factory):
    spec = AgentSpecification(
        agent_id="test_analytics_agent",
        name="Test Analytics Agent",
        class_name="TestAnalyticsAgent",
        role="Market Analytics",
        description="Analyzes trend metrics safely.",
        task_type="ANALYZE_TRENDS",
        allowed_permissions=[Permission.SCAN_MARKET],
        tools=["trend_calculator"],
        logic_summary="Computes market trends"
    )

    res = await clean_factory.build_and_register_agent(spec)
    assert res["status"] == "SUCCESS"
    assert res["agent_id"] == "test_analytics_agent"

    # Verify agent is in registry
    registered = agent_registry.get("test_analytics_agent")
    assert registered is not None
    assert registered.name == "Test Analytics Agent"
    assert registered.is_dynamic is True


@pytest.mark.asyncio
async def test_agent_factory_blocks_privilege_escalation(clean_factory):
    # Dynamic agent requesting EXECUTE_PURCHASE must be immediately blocked
    spec = AgentSpecification(
        agent_id="malicious_buyer_agent",
        name="Malicious Buyer",
        class_name="MaliciousBuyerAgent",
        role="Rogue Buyer",
        description="Tries to buy accounts without permission",
        task_type="BUY",
        allowed_permissions=[Permission.EXECUTE_PURCHASE],
        tools=["lzt_client.fast_buy"]
    )

    with pytest.raises(PermissionDeniedError):
        await clean_factory.build_and_register_agent(spec)


def test_ast_security_auditor_blocks_dangerous_constructs():
    import ast
    from orchestrator.agent_factory import ASTSecurityAuditor

    malicious_code = """
import os
import subprocess

def hack():
    os.system("rm -rf /")
    eval("1+1")
"""
    tree = ast.parse(malicious_code)
    auditor = ASTSecurityAuditor()
    auditor.visit(tree)

    assert len(auditor.violations) >= 3
    assert any("os" in v for v in auditor.violations)
    assert any("subprocess" in v for v in auditor.violations)
    assert any("eval" in v for v in auditor.violations)
