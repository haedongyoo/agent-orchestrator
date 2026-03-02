import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)
