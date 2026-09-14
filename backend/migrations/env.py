from logging.config import fileConfig

from alembic import context

# Import domain models here so Alembic autogenerate sees them.
# Later phases add their model modules above so they register on Base.metadata.
from cadence.ai_portfolio import models as _ai_portfolio_models  # noqa: F401
from cadence.assets import models as _assets_models  # noqa: F401
from cadence.config import settings
from cadence.database import Base
from cadence.paper_trading import models as _paper_trading_models  # noqa: F401
from cadence.portfolios import models as _portfolios_models  # noqa: F401
from cadence.recommendations import models as _recommendations_models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Feed the database URL from application settings (single source of truth).
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for 'autogenerate' support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import engine_from_config, pool

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
