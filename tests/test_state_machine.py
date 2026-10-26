"""
Tests for the Finite State Machine (ListingStateMachine).
Verifies valid progression, blocks illegal state skips, and enforces terminal rules.
"""

import pytest
from core.state_machine import ListingStateMachine, ListingState, InvalidStateTransitionError


def test_valid_state_machine_flow():
    fsm = ListingStateMachine(ListingState.DISCOVERED)
    assert fsm.current_state == ListingState.DISCOVERED

    fsm.transition_to(ListingState.INSPECTED, "inspector", "inspected")
    assert fsm.current_state == ListingState.INSPECTED

    fsm.transition_to(ListingState.PRICED, "pricer", "priced")
    assert fsm.current_state == ListingState.PRICED

    fsm.transition_to(ListingState.RISK_APPROVED, "risk", "risk ok")
    assert fsm.current_state == ListingState.RISK_APPROVED

    fsm.transition_to(ListingState.PURCHASE_PENDING, "buyer", "lock acquired")
    assert fsm.current_state == ListingState.PURCHASE_PENDING

    fsm.transition_to(ListingState.PURCHASE_CONFIRMED, "buyer", "bought")
    assert fsm.current_state == ListingState.PURCHASE_CONFIRMED

    fsm.transition_to(ListingState.RESALE_PREPARED, "reseller", "prepared")
    assert fsm.current_state == ListingState.RESALE_PREPARED

    fsm.transition_to(ListingState.LISTED, "reseller", "listed")
    assert fsm.current_state == ListingState.LISTED

    fsm.transition_to(ListingState.SOLD, "reseller", "sold")
    assert fsm.current_state == ListingState.SOLD
    assert fsm.is_terminal() is True
    assert len(fsm.history) == 8


def test_illegal_state_transition_skip():
    fsm = ListingStateMachine(ListingState.DISCOVERED)
    # Direct jump to PURCHASE_CONFIRMED is strictly forbidden
    with pytest.raises(InvalidStateTransitionError):
        fsm.transition_to(ListingState.PURCHASE_CONFIRMED, "hacker", "cheat")


def test_terminal_state_cannot_transition():
    fsm = ListingStateMachine(ListingState.REJECTED)
    assert fsm.is_terminal() is True
    with pytest.raises(InvalidStateTransitionError):
        fsm.transition_to(ListingState.INSPECTED, "agent", "revive")


def test_unknown_transaction_recovery():
    fsm = ListingStateMachine(ListingState.PURCHASE_PENDING)
    # Network timeout moves to UNKNOWN_TRANSACTION_STATUS
    fsm.transition_to(ListingState.UNKNOWN_TRANSACTION_STATUS, "buyer", "timeout")
    assert fsm.current_state == ListingState.UNKNOWN_TRANSACTION_STATUS

    # Verified offline and confirmed
    fsm.transition_to(ListingState.PURCHASE_CONFIRMED, "operator", "manually verified on site")
    assert fsm.current_state == ListingState.PURCHASE_CONFIRMED
