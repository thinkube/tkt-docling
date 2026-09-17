"""A PDF conversion and the workflow that runs it."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Float, Integer, String, Text

from app.db.session import Base


class ConversionStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL = {ConversionStatus.SUCCEEDED, ConversionStatus.FAILED}


class Conversion(Base):
    __tablename__ = "conversions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    pipeline = Column(String(32), nullable=False)
    formats = Column(JSON, nullable=False)
    status = Column(Enum(ConversionStatus), default=ConversionStatus.QUEUED, nullable=False)
    workflow_name = Column(String(253), nullable=True)
    error = Column(Text, nullable=True)
    pages = Column(Integer, nullable=True)
    seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Conversion {self.id}: {self.filename} {self.status}>"
