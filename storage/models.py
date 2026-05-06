from sqlalchemy import Column, Integer, String, DateTime, JSON, UniqueConstraint
from datetime import datetime, timezone
from storage.database import Base

class RawFile(Base):
    __tablename__ = "raw_files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String, index=True)
    file_hash = Column(String, unique=True, index=True) # SHA-256 hash for file-level deduplication
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String, default="manual")
    status = Column(String, default="uploaded") # uploaded, processing, completed, failed

class RawData(Base):
    __tablename__ = "raw_data"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True) # Foreign key conceptually
    row_hash = Column(String, index=True) # SHA-256 hash for row-level deduplication
    json_data = Column(JSON) # Store unstructured data to protect against schema changes

    __table_args__ = (
        UniqueConstraint('file_id', 'row_hash', name='uix_file_row_hash'),
    )
