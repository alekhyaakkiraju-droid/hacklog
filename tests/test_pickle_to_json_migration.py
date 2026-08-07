"""Integration tests for Alembic pickle-to-JSON migration."""

from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    create_engine,
)

PROFILE_FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "profile_fixtures.json").read_text(
        encoding="utf-8"
    )
)

PROFILE_TABLES = {
    "days": PROFILE_FIXTURES["days"],
    "hours": PROFILE_FIXTURES["hours"],
    "servers": PROFILE_FIXTURES["servers"],
    "ipAddress": PROFILE_FIXTURES["ipAddress"],
}

MIGRATED_TABLE_NAMES = {
    "days": "days",
    "hours": "hours",
    "servers": "server",
    "ipAddress": "ipAddress",
}


def _create_legacy_pickle_database(db_path: Path) -> dict[str, dict[str, dict]]:
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    tables: dict[str, Table] = {}

    for table_name in PROFILE_TABLES:
        tables[table_name] = Table(
            table_name,
            metadata,
            Column("date", DateTime, primary_key=True),
            Column("username", String, primary_key=True),
            Column("profile", LargeBinary),
            Column("totalCount", Integer),
        )

    metadata.create_all(engine)
    stamp = datetime(2026, 1, 1, 0, 0, 0)
    expected: dict[str, dict[str, dict]] = {}

    with engine.begin() as connection:
        for table_name, profile in PROFILE_TABLES.items():
            username = f"{table_name}-user"
            connection.execute(
                sa.text(f"""
                    INSERT INTO {table_name} (date, username, profile, totalCount)
                    VALUES (:date, :username, :profile, :totalCount)
                    """),
                {
                    "date": stamp,
                    "username": username,
                    "profile": pickle.dumps(profile),
                    "totalCount": sum(profile.values()),
                },
            )
            expected[table_name] = {"username": username, "profile": profile}

    engine.dispose()
    return expected


def _run_migration(db_path: Path, repo_root: Path) -> Path:
    backup_path = db_path.with_suffix(db_path.suffix + ".pre-migration.bak")
    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")
    assert backup_path.exists(), "pre-migration backup was not created"
    return backup_path


def _load_migrated_profiles(db_path: Path) -> dict[str, dict]:
    engine = create_engine(f"sqlite:///{db_path}")
    migrated: dict[str, dict] = {}

    with engine.connect() as connection:
        for table_name in PROFILE_TABLES:
            migrated_table = MIGRATED_TABLE_NAMES[table_name]
            row = (
                connection.execute(
                    sa.text(
                        f"SELECT username, profile FROM {migrated_table}"
                    )  # noqa: S608
                )
                .mappings()
                .one()
            )
            profile = row["profile"]
            if isinstance(profile, str):
                profile = json.loads(profile)
            migrated[table_name] = {"username": row["username"], "profile": profile}

    engine.dispose()
    return migrated


def test_migration_converts_pickle_profiles_to_json(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "legacy.db"
    expected = _create_legacy_pickle_database(db_path)

    _run_migration(db_path, repo_root)
    migrated = _load_migrated_profiles(db_path)

    for table_name, fixture in expected.items():
        assert migrated[table_name]["username"] == fixture["username"]
        assert migrated[table_name]["profile"] == fixture["profile"]


def test_migration_downgrade_is_best_effort_round_trip(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "legacy-downgrade.db"
    expected = _create_legacy_pickle_database(db_path)

    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        for table_name, fixture in expected.items():
            row = connection.execute(
                sa.text(f"SELECT profile FROM {table_name} WHERE username = :username"),
                {"username": fixture["username"]},
            ).one()
            restored = pickle.loads(row[0], encoding="latin1")
            assert restored == fixture["profile"]
    engine.dispose()
