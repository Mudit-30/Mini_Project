"""
gridmind_server.app.db.database
=================================
Async SQLite engine, session factory, ORM base, and the TelemetryRecord model.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, event, text
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


class TaskRecord(Base):
    """
    A compute task submitted by the user or an external client.
    The Dispatcher AI picks tasks from here and assigns them to idle nodes.

    Status lifecycle:  pending → dispatched → completed | failed
    """

    __tablename__ = "tasks"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    submitted_at   = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        index=True,
    )
    name           = Column(String(256), nullable=False)          # human-readable label
    command        = Column(Text,        nullable=True)            # shell command to run
    priority       = Column(Integer,     nullable=False, default=5) # 1 (high) – 10 (low)
    status         = Column(String(32),  nullable=False, default="pending", index=True)
    assigned_node  = Column(String(128), nullable=True)            # set when dispatched
    dispatched_at  = Column(DateTime(timezone=True), nullable=True)
    completed_at   = Column(DateTime(timezone=True), nullable=True)
    result_summary = Column(Text,        nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "name":           self.name,
            "command":        self.command,
            "priority":       self.priority,
            "status":         self.status,
            "assigned_node":  self.assigned_node,
            "submitted_at":   self.submitted_at.isoformat() if self.submitted_at else None,
            "dispatched_at":  self.dispatched_at.isoformat() if self.dispatched_at else None,
            "completed_at":   self.completed_at.isoformat() if self.completed_at else None,
            "result_summary": self.result_summary,
        }

    def __repr__(self) -> str:
        return f"<TaskRecord id={self.id} name={self.name!r} status={self.status!r}>"


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


