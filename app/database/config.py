import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str
    sql_echo: bool = False

    @classmethod
    def from_env(cls):
        # Async SQLAlchemy driver is required by the app integration.
        url = os.getenv("INTELLILEAD_DATABASE_URL", "postgresql+asyncpg://intellilead:intellilead_dev@localhost:5432/intellilead")
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return cls(database_url=url, sql_echo=os.getenv("INTELLILEAD_SQL_ECHO", "false").lower() in {"1", "true", "yes"})
