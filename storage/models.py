from sqlalchemy import Column, Integer, String, DateTime, JSON
from datetime import datetime, timezone
from storage.database import Base

class RawFile(Base):
    __tablename__ = "raw_files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String, index=True)
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String, default="manual")
    status = Column(String, default="uploaded") # uploaded, processing, completed, failed

class RawData(Base):
    __tablename__ = "raw_data"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, index=True) # Foreign key conceptually
    json_data = Column(JSON) # Store unstructured data to protect against schema changes
