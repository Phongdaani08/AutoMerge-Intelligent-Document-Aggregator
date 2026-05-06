from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AutoMerge Document Aggregator"
    VERSION: str = "0.1.0"
    
    # Database
    # DATABASE_URL: str = "sqlite:///./automerge_raw.db" # Fallback to sqlite for dev if postgres not ready
    DATABASE_URL :str = "postgresql://postgres:1234@localhost:5433/automerge_raw"
    # Security
    SECRET_KEY: str = "supersecretkey-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Upload settings
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024 # 10MB
    ALLOWED_EXTENSIONS: set = {".xlsx", ".csv"}

    class Config:
        env_file = ".env"

settings = Settings()
