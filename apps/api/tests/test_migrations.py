"""Alembic migrations apply cleanly up and down, and match the ORM metadata (no drift)."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import Base

API_DIR = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    return cfg


def _run(fn, *args):  # type: ignore[no-untyped-def]
    # env.py calls asyncio.run(), which cannot nest inside pytest-asyncio's loop: run in a thread.
    import threading

    err: list[BaseException] = []

    def target() -> None:
        try:
            fn(*args)
        except BaseException as e:  # noqa: BLE001
            err.append(e)

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if err:
        raise err[0]


def test_upgrade_downgrade_and_no_drift(tmp_path: Path) -> None:
    db = tmp_path / "mig.db"
    url = f"sqlite+aiosqlite:///{db.as_posix()}"
    cfg = _cfg(url)
    _run(command.upgrade, cfg, "head")
    sync = create_engine(f"sqlite:///{db.as_posix()}")
    tables = set(inspect(sync).get_table_names())
    assert set(Base.metadata.tables) <= tables
    uniques = {tuple(u["column_names"]) for u in inspect(sync).get_unique_constraints("jobs")}
    assert ("user_id", "fingerprint") in uniques
    assert ("user_id", "job_id") in {
        tuple(u["column_names"]) for u in inspect(sync).get_unique_constraints("applications")
    }
    with sync.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    _run(command.downgrade, cfg, "base")
    assert set(inspect(sync).get_table_names()) <= {"alembic_version"}
    _run(command.upgrade, cfg, "head")
    sync.dispose()


def test_asyncio_available() -> None:
    assert asyncio.get_event_loop_policy() is not None
