"""Convert PickleType profile columns to JSON.

Pre-migration backup:
    Copies the SQLite database file to ``<database>.pre-migration.bak`` before
    any schema or data changes are applied.

Rollback instructions:
    1. Stop the Hacklog application.
    2. Run ``alembic downgrade -1`` to convert JSON profiles back to pickle blobs.
    3. If downgrade data conversion fails, restore from ``<database>.pre-migration.bak``.

Revision ID: 001_pickle_json
Revises:
Create Date: 2026-08-07
"""

import json
import pickle
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import sqlalchemy as sa
from alembic import op

revision = "001_pickle_json"
down_revision = None
branch_labels = None
depends_on = None

PROFILE_TABLES = ("days", "hours", "servers", "ipAddress")

def _sqlite_path_from_url(url: str) -> Path | None:
    parsed = urlparse(url)
    if parsed.scheme != "sqlite":
        return None
    database = unquote(parsed.path or "")
    if not database or database == ":memory:":
        return None
    if database.startswith("/"):
        return Path(database)
    return Path(database)

def _backup_sqlite_database(connection: sa.Connection) -> Path | None:
    db_path = _sqlite_path_from_url(str(connection.engine.url))
    if db_path is None:
        return None
    backup_path = db_path.with_suffix(db_path.suffix + ".pre-migration.bak")
    shutil.copy2(db_path, backup_path)
    return backup_path

def _deserialize_pickle_profile(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    try:
        loaded = pickle.loads(raw, encoding="latin1")
    except Exception:
        loaded = pickle.loads(raw)
    if not isinstance(loaded, dict):
        raise TypeError(f"Expected profile dict, got {type(loaded)!r}")
    return loaded

def _snapshot_profiles(connection: sa.Connection) -> dict[str, list[dict[str, Any]]]:
    snapshots: dict[str, list[dict[str, Any]]] = {}
    for table in PROFILE_TABLES:
        rows = connection.execute(
            sa.text(
                f"SELECT date, username, profile, totalCount FROM {table}"  # noqa: S608
            )
        ).mappings()
        snapshots[table] = [
            {
                "date": row["date"],
                "username": row["username"],
                "profile": _deserialize_pickle_profile(row["profile"]),
                "totalCount": row["totalCount"],
            }
            for row in rows
        ]
    return snapshots

def _alter_profile_column_to_json(table: str) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            "profile",
            existing_type=sa.LargeBinary(),
            type_=sa.JSON(),
            existing_nullable=True,
        )

def _write_json_profiles(
    connection: sa.Connection, snapshots: dict[str, list[dict[str, Any]]]
) -> None:
    for table, rows in snapshots.items():
        for row in rows:
            connection.execute(
                sa.text(f"""
                    UPDATE {table}
                    SET profile = :profile
                    WHERE date = :date AND username = :username
                    """),  # noqa: S608
                {
                    "profile": json.dumps(row["profile"]),
                    "date": row["date"],
                    "username": row["username"],
                },
            )

def upgrade() -> None:
    bind = op.get_bind()
    _backup_sqlite_database(bind)
    snapshots = _snapshot_profiles(bind)

    for table in PROFILE_TABLES:
        _alter_profile_column_to_json(table)

    _write_json_profiles(bind, snapshots)

def _alter_profile_column_to_pickle(table: str) -> None:
    with op.batch_alter_table(table) as batch_op:
        batch_op.alter_column(
            "profile",
            existing_type=sa.JSON(),
            type_=sa.LargeBinary(),
            existing_nullable=True,
        )

def _serialize_profile_to_pickle(profile: Any) -> bytes:
    if profile is None:
        return pickle.dumps({})
    if isinstance(profile, (bytes, bytearray, memoryview)):
        return bytes(profile)
    if isinstance(profile, str):
        profile = json.loads(profile)
    return pickle.dumps(profile)

def downgrade() -> None:
    bind = op.get_bind()
    snapshots: dict[str, list[dict[str, Any]]] = {}

    for table in PROFILE_TABLES:
        rows = bind.execute(
            sa.text(
                f"SELECT date, username, profile, totalCount FROM {table}"  # noqa: S608
            )
        ).mappings()
        snapshots[table] = [
            {
                "date": row["date"],
                "username": row["username"],
                "profile": row["profile"],
                "totalCount": row["totalCount"],
            }
            for row in rows
        ]

    for table in PROFILE_TABLES:
        _alter_profile_column_to_pickle(table)

    for table, rows in snapshots.items():
        for row in rows:
            bind.execute(
                sa.text(f"""
                    UPDATE {table}
                    SET profile = :profile
                    WHERE date = :date AND username = :username
                    """),  # noqa: S608
                {
                    "profile": _serialize_profile_to_pickle(row["profile"]),
                    "date": row["date"],
                    "username": row["username"],
                },
            )
