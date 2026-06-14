from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "GridMind"
    VERSION:      str = "1.0.0"
    API_V1_STR:   str = "/api/v1"

    # NOTE: the three values below are currently informational only — the runtime
    # uses hardcoded constants, not these settings:
    #   - DB path  → app/db/database.py: DATABASE_PATH
    #   - gRPC port → app/grpc_server.py: GRPC_LISTEN_ADDR (and the bind pre-check)
    #   - telemetry interval → gridmind_node/agent.py: COLLECT_INTERVAL
    # Editing them here has no effect. Kept for documentation/future wiring.
    DATABASE_URL: str = "sqlite+aiosqlite:///./gridmind.db"
    GRPC_PORT: int = 50051
    TELEMETRY_INTERVAL_SECONDS: int = 5

    # WattTime API (register free at watttime.org)
    WATTTIME_USERNAME: str = ""
    WATTTIME_PASSWORD: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

