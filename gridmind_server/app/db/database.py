"""
gridmind_server.app.db.database
=================================
Async SQLite engine, session factory, ORM base, and the TelemetryRecord model.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# ── Engine ─────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

# ── SQLite WAL + performance PRAGMAs ──────────────────────────────────────────
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """
    Enable Write-Ahead Logging (WAL) and tune SQLite for concurrent reads.
      - WAL:               multiple readers + one writer simultaneously
      - synchronous=NORMAL: safe fsync — good durability/speed balance
      - foreign_keys=ON:   enforce FK constraints (SQLite default: OFF)
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ── Session factory ────────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()


# ── ORM Models ─────────────────────────────────────────────────────────────────
class TelemetryRecord(Base):
    """
    Persisted telemetry snapshot for one node at one point in time.

    Populated by the gRPC servicer after each successful Observer AI prediction.
    Used as the training source for the Observer AI auto-retrain pipeline.
    """

    __tablename__ = "telemetry_records"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at          = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,
    )

    # Node identifier
    node_id              = Column(String(128), nullable=False, index=True)

    # Raw telemetry features (mirror the gRPC message + dataset schema)
    cpu_usage_pct        = Column(Float,   nullable=False)
    ram_usage_pct        = Column(Float,   nullable=False)
    kb_events_per_min    = Column(Integer, nullable=False)
    mouse_events_per_min = Column(Integer, nullable=False)
    net_io_bytes         = Column(Integer, nullable=False)
    process_count        = Column(Integer, nullable=False)

    # Carbon intensity — set to 0.0 when WattTime is not yet integrated
    carbon_intensity_gco2 = Column(Float, nullable=False, default=0.0)

    # Observer AI output
    predicted_label      = Column(Integer, nullable=True)   # 0=idle,1=active,2=busy
    predicted_state      = Column(String(32), nullable=True) # "idle" / "active_user" / "busy_hardware"
    prediction_confidence = Column(Float,  nullable=True)   # 0.0 – 1.0

    def __repr__(self) -> str:
        return (
            f"<TelemetryRecord id={self.id} node={self.node_id!r} "
            f"state={self.predicted_state!r} at={self.recorded_at}>"
        )


# ── Schema helpers ─────────────────────────────────────────────────────────────
async def create_tables() -> None:
    """Create all ORM tables if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── FastAPI Dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """Yields a scoped async DB session for use as a FastAPI dependency."""
    async with AsyncSessionLocal() as session:
        yield session


