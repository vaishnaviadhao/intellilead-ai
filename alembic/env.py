import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.database.registry import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
# Alembic uses the synchronous psycopg driver; the FastAPI app uses asyncpg.
db_url = os.getenv("INTELLILEAD_DATABASE_URL")
if db_url:
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1) if db_url.startswith("postgresql://") else db_url
    config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    raise RuntimeError("This bootstrap migration uses metadata.create_all; run Alembic in online mode.")


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
