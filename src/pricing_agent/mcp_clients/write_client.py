"""The only module that can change a price. docs/architecture.md §8.

Physically separate from every read path. Skills receive read clients; this one is
reachable only from an explicit UI confirmation handler, never from a skill, an agent, or
the explanation layer.

In-memory for the prototype — nothing is actually published anywhere.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class PublicationRefused(RuntimeError):
    """A precondition in §22 / docs/approval-policy.md §5 was not satisfied."""


@dataclass
class PricingDecision:
    pricing_decision_id: str
    vehicle_id: str
    system_recommendation: float | None
    user_selected_price: float
    override_reason: str | None
    user_id: str
    created_at: datetime
    versions: dict[str, Any]
    warning_codes: list[str]
    approval_id: str | None = None
    published_at: datetime | None = None


@dataclass
class ApprovalRequest:
    approval_id: str
    pricing_decision_id: str
    approval_type: str
    justification: str
    quantified_impact: dict[str, float]
    requesting_user: str
    status: str = "PENDING"


@dataclass
class WriteClient:
    decisions: dict[str, PricingDecision] = field(default_factory=dict)
    approvals: dict[str, ApprovalRequest] = field(default_factory=dict)
    published: dict[str, str] = field(default_factory=dict)  # idempotency_key -> decision id

    # --- §10.5 ------------------------------------------------------------------------

    def request_manager_approval(
        self,
        pricing_decision_id: str,
        approval_type: str,
        justification: str,
        quantified_impact: dict[str, float],
        requesting_user: str,
    ) -> ApprovalRequest:
        """Create an approval request. Never auto-approves.

        The quantified impact is required rather than a narrative so the approving
        manager sees both sides of the comparison: the loss taken now against the modeled
        cost of continuing to hold. The system quantifies; the manager decides.
        """
        if not justification.strip():
            raise ValueError("Approval requires a documented reason (§19.2)")

        approval = ApprovalRequest(
            approval_id=f"appr_{uuid.uuid4().hex[:12]}",
            pricing_decision_id=pricing_decision_id,
            approval_type=approval_type,
            justification=justification,
            quantified_impact=quantified_impact,
            requesting_user=requesting_user,
        )
        self.approvals[approval.approval_id] = approval
        return approval

    def approve(self, approval_id: str, manager_id: str) -> ApprovalRequest:
        """Stands in for an out-of-band manager action. Never called by a skill."""
        approval = self.approvals[approval_id]
        approval.status = "APPROVED"
        decision = self.decisions.get(approval.pricing_decision_id)
        if decision is not None:
            decision.approval_id = approval_id
        return approval

    # --- §10.6 ------------------------------------------------------------------------

    def save_pricing_decision(
        self,
        vehicle_id: str,
        system_recommendation: float | None,
        user_selected_price: float,
        user_id: str,
        versions: dict[str, Any],
        warning_codes: list[str],
        created_at: datetime,
        override_reason: str | None = None,
        confirmed_by_user: bool = False,
    ) -> PricingDecision:
        if not confirmed_by_user:
            raise PublicationRefused("Saving a pricing decision requires user confirmation (§22.3)")

        decision = PricingDecision(
            pricing_decision_id=f"pd_{uuid.uuid4().hex[:12]}",
            vehicle_id=vehicle_id,
            system_recommendation=system_recommendation,
            user_selected_price=user_selected_price,
            override_reason=override_reason,
            user_id=user_id,
            created_at=created_at,
            versions=versions,
            warning_codes=list(warning_codes),
        )
        self.decisions[decision.pricing_decision_id] = decision
        return decision

    # --- §10.7 ------------------------------------------------------------------------

    @staticmethod
    def idempotency_key(pricing_decision_id: str, final_price: float) -> str:
        raw = f"{pricing_decision_id}:{final_price:.2f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def publish_vehicle_price(
        self,
        pricing_decision_id: str,
        final_price: float,
        confirmed_by_user: bool,
        blocking_warnings: list[str],
        stale_realtime_sources: list[str],
        approval_required: bool,
        published_at: datetime,
        idempotency_key: str | None = None,
    ) -> str:
        """Publish. Every precondition is verified here, not merely by the caller.

        Ordered so the most informative refusal wins: a BLOCKING warning is a more useful
        message than a missing confirmation.
        """
        decision = self.decisions.get(pricing_decision_id)
        if decision is None:
            raise PublicationRefused(f"Unknown pricing decision {pricing_decision_id}")

        if blocking_warnings:
            raise PublicationRefused(
                "Publication refused, unresolved BLOCKING warnings: "
                + ", ".join(sorted(blocking_warnings))
            )
        if stale_realtime_sources:
            raise PublicationRefused(
                "Publication refused, stale REALTIME data (§21): "
                + ", ".join(sorted(stale_realtime_sources))
            )
        if approval_required and decision.approval_id is None:
            raise PublicationRefused("Publication refused, manager approval required (§22.2)")
        if approval_required:
            approval = self.approvals.get(decision.approval_id or "")
            if approval is None or approval.status != "APPROVED":
                raise PublicationRefused("Publication refused, approval not granted")
        if not confirmed_by_user:
            raise PublicationRefused("Publication refused, explicit user confirmation required")

        # An approval obtained for one price must not publish another.
        if abs(decision.user_selected_price - final_price) > 0.005:
            raise PublicationRefused(
                "Publication refused, final_price does not match the saved decision"
            )

        key = idempotency_key or self.idempotency_key(pricing_decision_id, final_price)
        if key in self.published:
            return self.published[key]  # retry, not a second publication

        decision.published_at = published_at
        self.published[key] = pricing_decision_id
        return pricing_decision_id
