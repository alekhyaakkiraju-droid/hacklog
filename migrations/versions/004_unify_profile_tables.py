"""Consolidate days/hours/server/ipAddress tables into profiles.

Revision ID: 004_unify_profiles
Revises: 003_create_audit
Create Date: 2026-08-08
"""

import sqlalchemy as sa
from alembic import op

revision = "004_unify_profiles"
down_revision = "003_create_audit"
branch_labels = None
depends_on = None

PROFILE_SOURCES = (
    ("days", "days"),
    ("hours", "hours"),
    ("server", "server"),
    ("ipAddress", "ipAddress"),
)


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("profileType", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("totalCount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("profileType", "username"),
    )

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table_name, profile_type in PROFILE_SOURCES:
        if table_name not in existing_tables:
            continue
        connection.execute(
            sa.text(
                """
                INSERT INTO profiles (profileType, username, date, profile, totalCount)
                SELECT :profile_type, username, date, profile, totalCount
                FROM """
                + table_name
            ),
            {"profile_type": profile_type},
        )
        op.drop_table(table_name)


def downgrade() -> None:
    op.create_table(
        "days",
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("totalCount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("date", "username"),
    )
    op.create_table(
        "hours",
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("totalCount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("date", "username"),
    )
    op.create_table(
        "server",
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("totalCount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("date", "username"),
    )
    op.create_table(
        "ipAddress",
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=True),
        sa.Column("totalCount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("date", "username"),
    )

    connection = op.get_bind()
    for table_name, profile_type in PROFILE_SOURCES:
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {table_name} (date, username, profile, totalCount)
                SELECT date, username, profile, totalCount
                FROM profiles
                WHERE profileType = :profile_type
                """
            ),
            {"profile_type": profile_type},
        )

    op.drop_table("profiles")
