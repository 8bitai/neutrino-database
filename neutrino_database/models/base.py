from sqlalchemy.schema import MetaData
from sqlalchemy.orm import DeclarativeBase


metadata = MetaData()

class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    metadata: MetaData = metadata
