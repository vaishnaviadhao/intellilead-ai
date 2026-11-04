# Import all models so Alembic sees the complete metadata.
from .base import Base
from . import models  # noqa: F401

__all__ = ["Base"]
