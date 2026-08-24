"""A POC (proof of concept) tracks the technical evaluation an opportunity
goes through before a PO is issued.

Exactly one POC exists per opportunity (unique FK). It runs through five
stages, each independently completable with its own date so we can measure
how long each stage takes and cope with work done out of order:

  1. VM Provisioning     — allocating the VM. This *starts* the POC.
  2. Deployment          — product deployed onto the VM.
  3. Device Onboarding   — customer devices/nodes connected.
  4. Dashboarding        — dashboards built for the customer.
  5. Fine Tuning         — tuning and handover.

Status is derived, not hand-set (see poc_service.derive_status):

  not_started  → no VM allocated yet
  running      → VM allocated, POC in flight (whether 1/5 or 5/5 stages done)
  successful   → explicitly closed with a positive outcome
  unsuccessful → explicitly closed with a negative outcome

Completing all five stages does NOT auto-close the POC — a human closes it,
because "all the technical work is done" and "the customer accepted it" are
different facts.

Each stage also carries an owner drawn from the POC team, so "who is
responsible for device onboarding" has an answer without asking anyone.
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, ForeignKey, Text, Date
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class PocStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    SUCCESSFUL = "successful"
    UNSUCCESSFUL = "unsuccessful"


# The five stages in canonical order. The tuple is the single source of truth
# for stage identity: the model column is f"{key}_completed_at", and both the
# service and the dashboard aggregations iterate this list rather than
# hardcoding stage names.
POC_STAGES: tuple[tuple[str, str], ...] = (
    ("vm_provisioning", "VM Provisioning"),
    ("deployment", "Deployment"),
    ("device_onboarding", "Device Onboarding"),
    ("dashboarding", "Dashboarding"),
    ("fine_tuning", "Fine Tuning"),
)

POC_STAGE_KEYS: tuple[str, ...] = tuple(k for k, _ in POC_STAGES)
POC_STAGE_LABELS: dict[str, str] = {k: label for k, label in POC_STAGES}


class Poc(Base):
    __tablename__ = "pocs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Unique: one POC per opportunity. Partner / company / country / worth are
    # deliberately not duplicated here — they're read through .opportunity.
    opportunity_id = Column(
        Integer,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    status = Column(
        Enum(PocStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PocStatus.NOT_STARTED,
        index=True,
    )

    # start_date mirrors vm_provisioning_completed_at (the POC starts on VM
    # allocation) and is denormalised so date-range filters stay indexable.
    start_date = Column(Date, nullable=True, index=True)
    # Expected end date, set when the POC starts; actual close is closed_at.
    target_end_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True, index=True)

    # Per-stage completion dates — null means not yet done.
    vm_provisioning_completed_at = Column(Date, nullable=True)
    deployment_completed_at = Column(Date, nullable=True)
    device_onboarding_completed_at = Column(Date, nullable=True)
    dashboarding_completed_at = Column(Date, nullable=True)
    fine_tuning_completed_at = Column(Date, nullable=True)

    # Per-stage owner — who on the POC team is responsible for this stage.
    # Null means nobody has been named yet, which is every stage of every POC
    # predating migration 016.
    #
    # Five columns rather than a join table, mirroring the completion dates
    # above: the stage list is a fixed tuple (POC_STAGES), the accessors are
    # already generated as f"{key}_completed_at", and one owner per stage is
    # then true by construction rather than by constraint.
    #
    # SET NULL on delete: losing the account must leave the stage unowned, not
    # take the POC's history with it. An owner who leaves the *team* is
    # cleared explicitly instead — see poc_team_service.remove_member, because
    # a name still shown against a stage they are no longer on is worse than
    # no name at all.
    vm_provisioning_owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deployment_owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    device_onboarding_owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dashboarding_owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fine_tuning_owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Close-out
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    outcome_notes = Column(Text, nullable=True)
    # Free-text reason when status is unsuccessful, e.g. "lost on latency".
    failure_reason = Column(String(255), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    opportunity = relationship("Opportunity", back_populates="poc")
    closed_by_user = relationship("User", foreign_keys=[closed_by])
    # Every membership ever, including the removed ones — callers that want
    # the current roster filter on removed_at (poc_team_service.get_team).
    team_members = relationship(
        "PocTeamMember",
        back_populates="poc",
        cascade="all, delete-orphan",
    )

    def owner_id_for(self, stage_key: str) -> int | None:
        """The user id owning this stage, or None. Mirrors how the completion
        dates are read — one accessor built from the canonical stage key."""
        return getattr(self, f"{stage_key}_owner_id")

    @property
    def completed_stage_count(self) -> int:
        return sum(
            1 for key in POC_STAGE_KEYS
            if getattr(self, f"{key}_completed_at") is not None
        )

    @property
    def current_stage(self) -> str | None:
        """The first stage that isn't done yet — what the POC is working on.
        None once every stage is complete."""
        for key in POC_STAGE_KEYS:
            if getattr(self, f"{key}_completed_at") is None:
                return key
        return None
