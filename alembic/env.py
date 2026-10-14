from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core import models as core_models  # noqa: F401  (registers all models)

# Import application metadata so autogenerate can see the models.
from app.core.config import settings
from app.core.database import Base
from app.domains.audit.audits import models as audit_models  # noqa: F401
from app.platform.approvals import models as approval_models  # noqa: F401
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.history import models as history_models  # noqa: F401
from app.platform.tasks import models as task_models  # noqa: F401
from app.platform.users import models as user_models  # noqa: F401

config = context.config

# Point Alembic at the same database the application uses.
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_is_sqlite = settings.database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL emulation, no DB connection).

    Batch mode (render_as_batch) is only meaningful for SQLite; MySQL ALTER
    operations do not need it.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
