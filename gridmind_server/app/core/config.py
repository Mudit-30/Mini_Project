from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "GridMind"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # SQLite Database Configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///./gridmind.db"
    
    # WattTime API credentials (register for free at watttime.org)
    WATTTIME_USERNAME: str = ""
    WATTTIME_PASSWORD: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
