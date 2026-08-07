"""Rename servers table to server for singular entity naming.

Revision ID: 002_rename_servers
Revises: 001_pickle_json
Create Date: 2026-08-07
"""

from __future__ import annotations

from alembic import op

revision = "002_rename_servers"
down_revision = "001_pickle_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("servers", "server")


def downgrade() -> None:
    op.rename_table("server", "servers")
