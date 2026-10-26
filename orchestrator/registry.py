"""
Central Agent Registry for dynamically discovering, storing, and indexing active agents.
"""

from typing import Dict, List, Optional
import logging
from agents.base import BaseAgent

logger = logging.getLogger("AgentRegistry")


class AgentRegistry:
    """
    Maintains active instances of standard and dynamically loaded agents.
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Registers an agent instance."""
        if agent.agent_id in self._agents:
            logger.warning("Overwriting existing agent with id '%s'", agent.agent_id)
        self._agents[agent.agent_id] = agent
        logger.info("Agent registered: '%s' (%s)", agent.name, agent.agent_id)

    def unregister(self, agent_id: str) -> Optional[BaseAgent]:
        """Unregisters an agent (e.g. on rollback)."""
        return self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[BaseAgent]:
        return list(self._agents.values())

    def get_by_role(self, role_keyword: str) -> List[BaseAgent]:
        kw = role_keyword.lower()
        return [a for a in self._agents.values() if kw in a.role.lower()]


# Global registry
agent_registry = AgentRegistry()
