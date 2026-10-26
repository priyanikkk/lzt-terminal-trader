"""
Abstract Base Agent class with embedded RBAC security,
metrics collection, error isolation, and typed message handling.
"""

from abc import ABC, abstractmethod
from typing import Set, List, Optional, Any, TypeVar, Generic
from datetime import datetime, timezone
import time
import logging

from models.messages import AgentMessage, TaskStatus
from core.permissions import Permission, permission_controller, PermissionDeniedError
from database.repository import repository

logger = logging.getLogger("BaseAgent")

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """
    Base class for all multi-agent components in the system.
    Enforces security context, logs lifecycle metrics, and isolates errors.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        allowed_permissions: Set[Permission],
        tools: List[str],
        is_dynamic: bool = False
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.allowed_permissions = set(allowed_permissions)
        self.tools = list(tools)
        self.is_dynamic = is_dynamic

        self.status: str = "IDLE"  # IDLE, BUSY, ERROR, PAUSED
        self.current_task: Optional[str] = None
        self.last_run: Optional[datetime] = None
        self.success_count: int = 0
        self.error_count: int = 0
        self.total_execution_time_ms: float = 0.0

        # Register security context with the central permission controller
        permission_controller.register_agent(
            agent_id=self.agent_id,
            role=self.role,
            permissions=self.allowed_permissions,
            is_dynamic=self.is_dynamic
        )

    def verify_permission(self, required_permission: Permission) -> None:
        """Verifies this agent holds the required permission."""
        permission_controller.check_permission(self.agent_id, required_permission)

    async def execute(self, message: AgentMessage[TInput, TOutput]) -> AgentMessage[TInput, TOutput]:
        """
        Template method wrapping agent execution with metrics, timing,
        security validation, and database audit logging.
        """
        self.status = "BUSY"
        self.current_task = message.task_type
        self.last_run = datetime.now(timezone.utc)
        message.mark_running()

        start_time = time.monotonic()
        try:
            # Delegate to specialized implementation
            output = await self._run_task(message.input_data)
            duration_ms = (time.monotonic() - start_time) * 1000.0

            self.success_count += 1
            self.total_execution_time_ms += duration_ms
            self.status = "IDLE"
            self.current_task = None
            message.mark_success(output)

            # Persist execution audit log
            await self._safe_log_action(message.task_id, message.task_type, TaskStatus.SUCCESS.value, duration_ms, [])

        except PermissionDeniedError as pe:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            self.error_count += 1
            self.status = "ERROR"
            self.current_task = None
            err_msg = f"Security Policy Blocked: {pe}"
            logger.error("[%s] %s", self.agent_id, err_msg)
            message.mark_blocked(err_msg)

            await self._safe_log_action(message.task_id, message.task_type, TaskStatus.BLOCKED.value, duration_ms, [err_msg])

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            self.error_count += 1
            self.status = "ERROR"
            self.current_task = None
            err_msg = f"Execution error in {self.agent_id}: {exc}"
            logger.error("[%s] %s", self.agent_id, err_msg, exc_info=True)
            message.mark_failed(err_msg)

            await self._safe_log_action(message.task_id, message.task_type, TaskStatus.FAILED.value, duration_ms, [err_msg])

        return message

    async def _safe_log_action(self, task_id: str, task_type: str, status: str, duration_ms: float, errors: List[str]):
        try:
            await repository.log_agent_action(
                task_id=task_id,
                agent_id=self.agent_id,
                task_type=task_type,
                status=status,
                execution_time_ms=duration_ms,
                errors=errors
            )
        except Exception as e:
            logger.debug("Could not record agent log: %s", e)

    @abstractmethod
    async def _run_task(self, input_data: TInput) -> TOutput:
        """Implemented by child agent classes."""
        pass
