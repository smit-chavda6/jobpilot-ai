"""Tests verifying Alembic migrations upgrade and downgrade cleanly."""

from alembic import command
from alembic.config import Config


def test_alembic_migrations_up_and_down_clean():
    """Validates that Alembic can apply migrations and rollback without schema errors."""
    alembic_cfg = Config("apps/api/alembic.ini")
    alembic_cfg.set_main_option("script_location", "apps/api/alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///test_migration.db")

    # Run upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Run downgrade back to base
    command.downgrade(alembic_cfg, "base")

    # Re-apply upgrade to ensure full idempotency
    command.upgrade(alembic_cfg, "head")
    command.downgrade(alembic_cfg, "base")

    import os

    if os.path.exists("test_migration.db"):
        os.remove("test_migration.db")
