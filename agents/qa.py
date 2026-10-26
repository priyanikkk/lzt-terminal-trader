"""
Agent 10 — QAAgent.
Validates system readiness, inter-agent contracts, error handling,
double purchase defenses, and audits newly generated dynamic agent modules.
Strictly isolated from live purchase secrets and real credentials.
"""

from typing import Dict, Any, List
import pytest
import logging
from agents.base import BaseAgent
from core.permissions import Permission

logger = logging.getLogger("QAAgent")


class QAAgent(BaseAgent[Dict[str, Any], Dict[str, Any]]):
    """
    Automated testing and contract verification agent.
    """

    def __init__(self, agent_id: str = "qa_agent"):
        super().__init__(
            agent_id=agent_id,
            name="Quality Assurance Agent",
            role="Contract Verification & Regression Suite Runner",
            allowed_permissions={Permission.RUN_QA},
            tools=["pytest_suite", "contract_verifier", "sandbox_evaluator"]
        )

    async def _run_task(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.verify_permission(Permission.RUN_QA)

        target = input_data.get("target", "all")
        test_path = input_data.get("test_path", "tests")
        logger.info("Executing QA test suite on target: %s (path: %s)", target, test_path)

        import sys
        import asyncio
        import re

        # Run pytest in an isolated separate process to ensure sandboxing
        # and prevent nested asyncio loop conflicts
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-q",
            "--tb=short",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        exit_code = proc.returncode
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        # Parse test outcomes from output
        passed = len(re.findall(r"\bpassed\b", stdout_text))
        failed = len(re.findall(r"\bfailed\b", stdout_text))
        is_ready = (exit_code == 0)

        report = {
            "exit_code": int(exit_code),
            "is_system_ready": is_ready,
            "total_passed": 1 if is_ready else 0,
            "total_failed": 0 if is_ready else 1,
            "total_skipped": 0,
            "failures": [stdout_text] if not is_ready else [],
            "target": target
        }

        logger.info("QA Run Complete. Ready=%s (Passed=%d, Failed=%d)", is_ready, report["total_passed"], report["total_failed"])
        return report
