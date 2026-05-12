import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AutoMerge Document Aggregator"
    VERSION: str = "0.1.0"

    # Database
    DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Upload settings
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB default
    UPLOAD_DIR: str = "temp_uploads"
    ALLOWED_EXTENSIONS: set = {".xlsx", ".csv"}

    # [A3] CORS — โหลดจาก .env แบบ List โดย parse จาก String คั่นด้วย comma
    ALLOWED_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500"

    def get_allowed_origins_list(self) -> List[str]:
        """แปลง ALLOWED_ORIGINS string เป็น list สำหรับ CORSMiddleware"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()
