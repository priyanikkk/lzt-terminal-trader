"""
Finite State Machine (FSM) for Arbitrage Listings.
Strictly governs the lifecycle of every scanned listing and enforces transition rules.
"""

from enum import Enum
from typing import Dict, Set, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ListingState(str, Enum):
    DISCOVERED = "DISCOVERED"
    INSPECTED = "INSPECTED"
    PRICED = "PRICED"
    RISK_APPROVED = "RISK_APPROVED"
    PURCHASE_PENDING = "PURCHASE_PENDING"
    PURCHASE_CONFIRMED = "PURCHASE_CONFIRMED"
    RESALE_PREPARED = "RESALE_PREPARED"
    LISTED = "LISTED"
    SOLD = "SOLD"

    # Terminal / Exception states
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    UNKNOWN_TRANSACTION_STATUS = "UNKNOWN_TRANSACTION_STATUS"
    CANCELLED = "CANCELLED"


class StateTransitionRecord(BaseModel):
    from_state: ListingState
    to_state: ListingState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str
    triggered_by_agent: str


class InvalidStateTransitionError(Exception):
    """Raised when an illegal transition between states is attempted."""
    pass


class ListingStateMachine:
    """
    Manages and validates transitions for a listing's lifecycle.
    """

    ALLOWED_TRANSITIONS: Dict[ListingState, Set[ListingState]] = {
        ListingState.DISCOVERED: {
            ListingState.INSPECTED,
            ListingState.REJECTED,
            ListingState.FAILED
        },
        ListingState.INSPECTED: {
            ListingState.PRICED,
            ListingState.REJECTED,
            ListingState.REQUIRES_REVIEW,
            ListingState.FAILED
        },
        ListingState.PRICED: {
            ListingState.RISK_APPROVED,
            ListingState.REJECTED,
            ListingState.REQUIRES_REVIEW,
            ListingState.FAILED
        },
        ListingState.RISK_APPROVED: {
            ListingState.PURCHASE_PENDING,
            ListingState.REJECTED,
            ListingState.REQUIRES_REVIEW,
            ListingState.CANCELLED
        },
        ListingState.PURCHASE_PENDING: {
            ListingState.PURCHASE_CONFIRMED,
            ListingState.UNKNOWN_TRANSACTION_STATUS,
            ListingState.FAILED,
            ListingState.CANCELLED
        },
        ListingState.UNKNOWN_TRANSACTION_STATUS: {
            ListingState.PURCHASE_CONFIRMED,
            ListingState.FAILED,
            ListingState.REQUIRES_REVIEW
        },
        ListingState.PURCHASE_CONFIRMED: {
            ListingState.RESALE_PREPARED,
            ListingState.FAILED
        },
        ListingState.RESALE_PREPARED: {
            ListingState.LISTED,
            ListingState.REQUIRES_REVIEW,
            ListingState.FAILED
        },
        ListingState.LISTED: {
            ListingState.SOLD,
            ListingState.CANCELLED,
            ListingState.FAILED
        },
        ListingState.REQUIRES_REVIEW: {
            ListingState.DISCOVERED,
            ListingState.INSPECTED,
            ListingState.PRICED,
            ListingState.RISK_APPROVED,
            ListingState.PURCHASE_PENDING,
            ListingState.RESALE_PREPARED,
            ListingState.REJECTED,
            ListingState.FAILED
        },
        ListingState.REJECTED: set(),  # Terminal
        ListingState.SOLD: set(),      # Terminal
        ListingState.FAILED: set(),    # Terminal
        ListingState.CANCELLED: set(), # Terminal
    }

    def __init__(self, initial_state: ListingState = ListingState.DISCOVERED):
        self._current_state = initial_state
        self._history: List[StateTransitionRecord] = []

    @property
    def current_state(self) -> ListingState:
        return self._current_state

    @property
    def history(self) -> List[StateTransitionRecord]:
        return list(self._history)

    def is_terminal(self) -> bool:
        return len(self.ALLOWED_TRANSITIONS.get(self._current_state, set())) == 0

    def can_transition_to(self, new_state: ListingState) -> bool:
        allowed = self.ALLOWED_TRANSITIONS.get(self._current_state, set())
        return new_state in allowed

    def transition_to(
        self,
        new_state: ListingState,
        agent_id: str,
        reason: str
    ) -> StateTransitionRecord:
        """
        Executes a transition if allowed by state rules.
        """
        if not self.can_transition_to(new_state):
            raise InvalidStateTransitionError(
                f"Illegal transition from '{self._current_state.value}' to '{new_state.value}'. "
                f"Allowed destinations: {[s.value for s in self.ALLOWED_TRANSITIONS.get(self._current_state, set())]}. "
                f"Attempted by agent '{agent_id}' with reason: {reason}"
            )

        record = StateTransitionRecord(
            from_state=self._current_state,
            to_state=new_state,
            reason=reason,
            triggered_by_agent=agent_id
        )
        self._history.append(record)
        self._current_state = new_state
        return record
