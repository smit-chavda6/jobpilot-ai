"""Application status state machine - the ONLY place status transitions are defined (spec §4, §10).

`submitted_confirmed` is reachable only through the explicit user-confirmation action, and
`approved` only through an approval checkpoint bound to a payload hash. Opening the employer's
form (`handoff_opened`) never implies submission.
"""

from __future__ import annotations

from typing import Final

STATUSES: Final[tuple[str, ...]] = (
    "saved",
    "tailoring",
    "ready_for_review",
    "awaiting_approval",
    "approved",
    "handoff_opened",
    "awaiting_user_confirmation",
    "submitted_confirmed",
    "interviewing",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
    "declined",
    "ghosted",
)
TERMINAL: Final[frozenset[str]] = frozenset({"accepted", "rejected", "withdrawn", "declined"})
PRE_SUBMISSION: Final[frozenset[str]] = frozenset(
    {
        "saved",
        "tailoring",
        "ready_for_review",
        "awaiting_approval",
        "approved",
        "handoff_opened",
        "awaiting_user_confirmation",
    }
)

TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "saved": frozenset({"tailoring", "withdrawn"}),
    "tailoring": frozenset({"ready_for_review", "saved", "withdrawn"}),
    "ready_for_review": frozenset({"awaiting_approval", "tailoring", "withdrawn"}),
    "awaiting_approval": frozenset({"approved", "ready_for_review", "tailoring", "withdrawn"}),
    "approved": frozenset({"handoff_opened", "ready_for_review", "withdrawn"}),
    "handoff_opened": frozenset({"awaiting_user_confirmation", "ready_for_review", "withdrawn"}),
    "awaiting_user_confirmation": frozenset({"submitted_confirmed", "handoff_opened", "ready_for_review", "withdrawn"}),
    "submitted_confirmed": frozenset({"interviewing", "rejected", "ghosted", "offer", "withdrawn"}),
    "interviewing": frozenset({"offer", "rejected", "withdrawn", "ghosted"}),
    "ghosted": frozenset({"interviewing", "rejected", "offer", "withdrawn"}),
    "offer": frozenset({"accepted", "declined", "withdrawn"}),
    "accepted": frozenset(),
    "rejected": frozenset(),
    "withdrawn": frozenset(),
    "declined": frozenset(),
}

# Targets that can only be reached through a specific, dedicated action.
GATED: Final[dict[str, str]] = {
    "approved": "approval",
    "handoff_opened": "handoff",
    "awaiting_user_confirmation": "handoff",
    "submitted_confirmed": "user_confirmation",
}

KANBAN_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "Saved": ("saved",),
    "Preparing": ("tailoring", "ready_for_review", "awaiting_approval"),
    "Ready to submit": ("approved", "handoff_opened", "awaiting_user_confirmation"),
    "Applied": ("submitted_confirmed", "ghosted"),
    "Interviewing": ("interviewing",),
    "Offer": ("offer", "accepted"),
    "Closed": ("rejected", "withdrawn", "declined"),
}


class TransitionError(Exception):
    def __init__(self, current: str, target: str, reason: str):
        super().__init__(reason)
        self.current, self.target, self.reason = current, target, reason


def check_transition(current: str, target: str, via: str = "manual") -> None:
    """Raise TransitionError unless `current -> target` is allowed when invoked through `via`."""
    if target not in STATUSES:
        raise TransitionError(current, target, f"Unknown status '{target}'")
    if target not in TRANSITIONS.get(current, frozenset()):
        raise TransitionError(current, target, f"Cannot move from '{current}' to '{target}'")
    required = GATED.get(target)
    if required is not None and via != required:
        raise TransitionError(
            current, target, f"'{target}' can only be reached through the {required.replace('_', ' ')} step"
        )


def allowed_targets(current: str, via: str = "manual") -> list[str]:
    return sorted(t for t in TRANSITIONS.get(current, frozenset()) if GATED.get(t) in (None, via))
