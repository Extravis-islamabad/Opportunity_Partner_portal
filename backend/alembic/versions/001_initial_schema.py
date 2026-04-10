"""Initial schema - all tables

Revision ID: 001
Revises: None
Create Date: 2026-04-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === USERS ===
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum("admin", "partner", name="userrole"), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", "pending_activation", "locked", name="userstatus"), nullable=False),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activation_token", sa.String(255), nullable=True),
        sa.Column("activation_token_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_token", sa.String(255), nullable=True),
        sa.Column("reset_token_expires", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_company_id", "users", ["company_id"])

    # === COMPANIES ===
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("industry", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("active", "inactive", name="companystatus"), nullable=False, server_default="active"),
        sa.Column("tier", sa.Enum("silver", "gold", "platinum", name="partnertier"), nullable=False, server_default="silver"),
        sa.Column("channel_manager_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["channel_manager_id"], ["users.id"]),
    )
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_channel_manager_id", "companies", ["channel_manager_id"])

    # Add FK from users.company_id -> companies.id
    op.create_foreign_key("fk_users_company_id", "users", "companies", ["company_id"], ["id"])

    # === OPPORTUNITIES ===
    op.create_table(
        "opportunities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(100), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("worth", sa.Numeric(15, 2), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("draft", "pending_review", "under_review", "approved", "rejected", "removed", "multi_partner_flagged", name="opportunitystatus"), nullable=False, server_default="draft"),
        sa.Column("preferred_partner", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("multi_partner_alert", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
    )
    op.create_index("ix_opportunities_name", "opportunities", ["name"])
    op.create_index("ix_opportunities_customer_name", "opportunities", ["customer_name"])
    op.create_index("ix_opportunities_submitted_by", "opportunities", ["submitted_by"])
    op.create_index("ix_opportunities_company_id", "opportunities", ["company_id"])

    # === OPP_DOCUMENTS ===
    op.create_table(
        "opp_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_url", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
    )
    op.create_index("ix_opp_documents_opportunity_id", "opp_documents", ["opportunity_id"])

    # === KB_DOCUMENTS ===
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_url", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("previous_version_id", sa.Integer(), nullable=True),
        sa.Column("is_archived", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_version_id"], ["kb_documents.id"]),
    )
    op.create_index("ix_kb_documents_title", "kb_documents", ["title"])
    op.create_index("ix_kb_documents_category", "kb_documents", ["category"])

    # === KB_DOWNLOAD_LOGS ===
    op.create_table(
        "kb_download_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["document_id"], ["kb_documents.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_kb_download_logs_document_id", "kb_download_logs", ["document_id"])
    op.create_index("ix_kb_download_logs_user_id", "kb_download_logs", ["user_id"])

    # === COURSES ===
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Enum("draft", "published", name="coursestatus"), nullable=False, server_default="draft"),
        sa.Column("modules_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("thumbnail_url", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_courses_title", "courses", ["title"])

    # === ENROLLMENTS ===
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("enrolled", "in_progress", "completed", name="enrollmentstatus"), nullable=False, server_default="enrolled"),
        sa.Column("progress_json", sa.String(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("certificate_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_url", sa.String(1000), nullable=True),
        sa.Column("certificate_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
    )
    op.create_index("ix_enrollments_user_id", "enrollments", ["user_id"])
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])

    # === DOC_REQUESTS ===
    op.create_table(
        "doc_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Enum("low", "medium", "high", name="docrequesturgency"), nullable=False, server_default="medium"),
        sa.Column("status", sa.Enum("pending", "fulfilled", "declined", name="docrequeststatus"), nullable=False, server_default="pending"),
        sa.Column("fulfilled_by", sa.Integer(), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_file_url", sa.String(1000), nullable=True),
        sa.Column("fulfilled_file_name", sa.String(500), nullable=True),
        sa.Column("decline_reason", sa.Text(), nullable=True),
        sa.Column("add_to_kb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["fulfilled_by"], ["users.id"]),
    )
    op.create_index("ix_doc_requests_company_id", "doc_requests", ["company_id"])
    op.create_index("ix_doc_requests_requested_by", "doc_requests", ["requested_by"])

    # === NOTIFICATIONS ===
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])

    # === AUDIT_LOGS ===
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])

    # === DEAL_REGISTRATIONS ===
    op.create_table(
        "deal_registrations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("registered_by", sa.Integer(), nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("deal_description", sa.Text(), nullable=False),
        sa.Column("estimated_value", sa.Numeric(15, 2), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("pending", "approved", "rejected", "expired", name="dealstatus"), nullable=False, server_default="pending"),
        sa.Column("exclusivity_start", sa.Date(), nullable=True),
        sa.Column("exclusivity_end", sa.Date(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["registered_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
    )
    op.create_index("ix_deal_registrations_company_id", "deal_registrations", ["company_id"])
    op.create_index("ix_deal_registrations_registered_by", "deal_registrations", ["registered_by"])

    # === PARTNER_TIER_HISTORY ===
    op.create_table(
        "partner_tier_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("previous_tier", sa.String(20), nullable=True),
        sa.Column("new_tier", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
    )
    op.create_index("ix_partner_tier_history_company_id", "partner_tier_history", ["company_id"])


def downgrade() -> None:
    op.drop_table("partner_tier_history")
    op.drop_table("deal_registrations")
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("doc_requests")
    op.drop_table("enrollments")
    op.drop_table("courses")
    op.drop_table("kb_download_logs")
    op.drop_table("kb_documents")
    op.drop_table("opp_documents")
    op.drop_table("opportunities")
    op.drop_constraint("fk_users_company_id", "users", type_="foreignkey")
    op.drop_table("companies")
    op.drop_table("users")
