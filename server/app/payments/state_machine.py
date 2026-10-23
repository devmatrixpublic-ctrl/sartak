"""Payment state machines.

Two independent flows, selected by `Payment.method`. Only the `checkout`
flow can reach `paid`, and only from a verified Razorpay webhook. The
`upi_intent` flow never reaches `paid` because the outcome is app-reported,
not verified.
"""

from app.core.errors import ApiError

CHECKOUT_TRANSITIONS: dict[str, set[str]] = {
    "created": {"held", "allowed"},
    # Dual custody: only a linked trusted contact moves a held payment on (service.decide_held_payment).
    "held": {"approved", "blocked", "allowed_by_user"},
    "approved": {"paid", "failed"},
    "allowed_by_user": {"paid", "failed"},
    "blocked": set(),
    "allowed": {"paid", "failed"},
    "paid": set(),
    "failed": set(),
}

UPI_INTENT_TRANSITIONS: dict[str, set[str]] = {
    "created": {"held", "allowed"},
    "held": {"approved", "blocked", "allowed_by_user"},
    "approved": {"handed_off"},
    "allowed_by_user": {"handed_off"},
    "blocked": set(),
    "allowed": {"handed_off"},
    "handed_off": {"reported_success", "reported_failure", "no_result"},
    "reported_success": set(),
    "reported_failure": set(),
    "no_result": set(),
}

TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "checkout": CHECKOUT_TRANSITIONS,
    "upi_intent": UPI_INTENT_TRANSITIONS,
}


class InvalidTransition(ApiError):
    def __init__(self, method: str, current: str, target: str):
        super().__init__(
            status_code=409,
            code="invalid_transition",
            message=f"{method}: cannot move from {current!r} to {target!r}",
        )


def can_transition(method: str, current: str, target: str) -> bool:
    return target in TRANSITIONS[method].get(current, set())


def require_transition(method: str, current: str, target: str) -> None:
    if not can_transition(method, current, target):
        raise InvalidTransition(method, current, target)
