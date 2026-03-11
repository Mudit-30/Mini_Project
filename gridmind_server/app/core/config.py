from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "GridMind"
    VERSION:      str = "1.0.0"
    API_V1_STR:   str = "/api/v1"

    # SQLite Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./gridmind.db"

    # gRPC
    GRPC_PORT: int = 50051

    # Node agent
    TELEMETRY_INTERVAL_SECONDS: int = 5   # how often agents sample & send data

    # WattTime API (register free at watttime.org)
    WATTTIME_USERNAME: str = ""
    WATTTIME_PASSWORD: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

