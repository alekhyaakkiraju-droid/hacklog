"""Create audit_records table for immutable scoring and alerting audit trail.

Revision ID: 003_create_audit
Revises: 002_rename_servers
Create Date: 2026-08-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_create_audit"
down_revision = "002_rename_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("source_ip", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_records_timestamp",
        "audit_records",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_records_timestamp", table_name="audit_records")
    op.drop_table("audit_records")
