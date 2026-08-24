"""Who from Extravis is working a POC.

An opportunity has one named sales rep (Opportunity.sales_rep_id) who owns the
deal. A POC needs more than that: a presales lead scoping it, a solution
architect designing it, a deployment engineer building it, and so on. This
table is that roster.

Membership is not decoration — it grants access. A team member can open the
parent opportunity and drive the POC even when they are not the named rep and
do not channel-manage the company (deps.assert_can_work_on_poc). It stops
there: approving or rejecting the opportunity, editing it, and everything
commercial still go through the strict per-record check, which membership does
not satisfy.

People come and go over the life of a POC, so removal is soft: `removed_at` is
stamped and the row stays. A POC that went badly is a thing people ask
questions about months later, and "who was on it in March" is one of the
questions.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base


class PocTeamRole(str, enum.Enum):
    """What a person does on the POC.

    Deliberately about the POC and not about the person: the same engineer can
    be the deployment engineer on one POC and the solution architect on
    another, so this lives on the membership row rather than on the user.
    """
    PRESALES_LEAD = "presales_lead"
    SOLUTION_ARCHITECT = "solution_architect"
    DEPLOYMENT_ENGINEER = "deployment_engineer"
    PROJECT_MANAGER = "project_manager"
    QA = "qa"
    SUPPORT = "support"


# Display labels, kept next to the enum so the API, the exports and the
# frontend all read one source rather than each inventing title-casing. "QA"
# is why this exists — .title() would render it "Qa".
POC_TEAM_ROLE_LABELS: dict[PocTeamRole, str] = {
    PocTeamRole.PRESALES_LEAD: "Presales Lead",
    PocTeamRole.SOLUTION_ARCHITECT: "Solution Architect",
    PocTeamRole.DEPLOYMENT_ENGINEER: "Deployment Engineer",
    PocTeamRole.PROJECT_MANAGER: "Project Manager",
    PocTeamRole.QA: "QA",
    PocTeamRole.SUPPORT: "Support",
}


class PocTeamMember(Base):
    __tablename__ = "poc_team_members"

    id = Column(Integer, primary_key=True, autoincrement=True)

    poc_id = Column(
        Integer,
        ForeignKey("pocs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(
        Enum(PocTeamRole, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Who put them on the team, kept for the audit trail. SET NULL rather than
    # CASCADE: losing the assigner must never delete the assignment.
    assigned_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Soft removal. Null means currently on the team — every access check and
    # every roster read filters on `removed_at IS NULL`, and the partial
    # unique index below only constrains live rows, so the same person can be
    # taken off a POC and put back on later.
    removed_at = Column(DateTime(timezone=True), nullable=True)
    removed_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    poc = relationship("Poc", back_populates="team_members")
    user = relationship("User", foreign_keys=[user_id])
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])

    __table_args__ = (
        # One live membership per person per POC: a role change updates the
        # row rather than stacking a second one, so "what is Sam's role on
        # this POC" always has exactly one answer. Partial, so the historical
        # rows left behind by a removal don't block a re-add.
        Index(
            "uq_poc_team_members_active",
            "poc_id",
            "user_id",
            unique=True,
            postgresql_where=removed_at.is_(None),
        ),
        # The access check runs on every POC request a team member makes:
        # "is this user live on this POC?".
        Index("ix_poc_team_members_user_active", "user_id", "poc_id"),
    )
