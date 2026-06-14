from __future__ import annotations

import datetime
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger("gridmind.db")

# Absolute path — never depends on CWD
import os
DATABASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "gridmind.db"))

class ColumnExpr:
    def __init__(self, name, op, value):
        self.name = name
        self.op = op
        self.value = value

class OrderExpr:
    """An ORDER BY term carrying an explicit direction (ASC/DESC)."""
    def __init__(self, col_name, direction="ASC"):
        self.col_name = col_name
        self.direction = direction

class MockColumn:
    def __init__(self, col_name):
        self.col_name = col_name

    def __eq__(self, other):
        return ColumnExpr(self.col_name, "=", other)

    # A bare MockColumn in order_by() means ASC; .desc()/.asc() carry direction.
    def desc(self):
        return OrderExpr(self.col_name, "DESC")

    def asc(self):
        return OrderExpr(self.col_name, "ASC")

class BaseMeta(type):
    def __getattr__(cls, name):
        return MockColumn(name)

class Base(metaclass=BaseMeta):
    def __init__(self, **kwargs):
        self.id = None
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if not k.startswith("_"):
                d[k] = v
        # Ensure dates are serialized correctly
        for k, v in d.items():
            if isinstance(v, datetime.datetime):
                d[k] = v.isoformat()
        if "has_artifact" in d:
            d["has_artifact"] = bool(d["has_artifact"])
        return d

class TelemetryRecord(Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(self, "recorded_at"):
            self.recorded_at = datetime.datetime.now(datetime.timezone.utc)
        if not hasattr(self, "carbon_intensity_gco2"):
            self.carbon_intensity_gco2 = 0.0

class TaskRecord(Base):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(self, "submitted_at"):
            self.submitted_at = datetime.datetime.now(datetime.timezone.utc)
        if not hasattr(self, "has_artifact"):
            self.has_artifact = 0
        if not hasattr(self, "status"):
            self.status = "pending"

class MockSelect:
    def __init__(self, *args):
        self.columns = list(args)
        self.where_clauses = []
        self._order_by = []
        self._limit = None
        self._group_by = None

    def where(self, clause):
        if clause is not None:
            self.where_clauses.append(clause)
        return self

    def order_by(self, *clauses):
        self._order_by.extend(clauses)
        return self

    def limit(self, val):
        self._limit = val
        return self

    def group_by(self, clause):
        self._group_by = clause
        return self

def select(*args):
    return MockSelect(*args)

class MockUpdate:
    def __init__(self, table_class):
        self.table_class = table_class
        self.where_clauses = []
        self._values = {}

    def where(self, clause):
        self.where_clauses.append(clause)
        return self

    def values(self, **kwargs):
        self._values.update(kwargs)
        return self

def update(table_class):
    return MockUpdate(table_class)

class MockFunc:
    def count(self, col):
        return "COUNT"

func = MockFunc()

class MockResult:
    def __init__(self, rows, orm_class=None):
        self._rows = rows
        self._orm_class = orm_class

    def scalars(self):
        return MockScalars([self._to_orm(r) for r in self._rows])

    def scalar_one(self):
        if not self._rows:
            raise ValueError("No rows returned")
        # ORM row → hydrate; aggregate/count row → first scalar value.
        if self._orm_class is not None:
            return self._to_orm(self._rows[0])
        return self._rows[0][0]

    def scalar_one_or_none(self):
        if not self._rows:
            return None
        return self._to_orm(self._rows[0])

    def __iter__(self):
        return iter(self._rows)

    def _to_orm(self, row):
        if self._orm_class is None:
            return row
        obj = self._orm_class()
        for k in row.keys():
            setattr(obj, k, row[k])
        return obj

class MockScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items

class AsyncSession:
    def __init__(self):
        self.db = None
        self._added_records = []

    async def __aenter__(self):
        self.db = await aiosqlite.connect(DATABASE_PATH)
        self.db.row_factory = aiosqlite.Row
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            await self.db.close()

    def add(self, record):
        # IMPORTANT: commit() only persists rows added here (always via INSERT).
        # A row LOADED via select(...).scalar_one_or_none() and then mutated will
        # NOT be flushed by commit() — persist those with update(...).values(...).
        if getattr(record, "id", None) is not None:
            logger.warning(
                "session.add() called on a row that already has id=%s; commit() will "
                "attempt an INSERT, not an UPDATE. Use update().values() to persist "
                "changes to an existing row.", record.id,
            )
        self._added_records.append(record)

    def add_all(self, records):
        self._added_records.extend(records)

    async def refresh(self, record):
        if isinstance(record, TaskRecord) and hasattr(record, "task_id"):
            async with self.db.execute("SELECT id FROM tasks WHERE task_id = ?", (record.task_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    record.id = row["id"]
        # NOTE: telemetry rows are inserted via add_all()+commit() which already sets
        # record.id from cursor.lastrowid; a MAX(id) lookup here would be racy, so the
        # TelemetryRecord refresh path is intentionally omitted.

    async def commit(self):
        for record in self._added_records:
            table_name = "tasks" if isinstance(record, TaskRecord) else "telemetry_records"
            fields = {k: v for k, v in record.__dict__.items() if not k.startswith("_") and k != "id"}
            
            # Format datetime
            for k, v in fields.items():
                if isinstance(v, datetime.datetime):
                    fields[k] = v.isoformat()
                    
            if record.id is None:
                keys = list(fields.keys())
                placeholders = ", ".join(["?"] * len(keys))
                sql = f"INSERT INTO {table_name} ({', '.join(keys)}) VALUES ({placeholders})"
                cursor = await self.db.execute(sql, tuple(fields[k] for k in keys))
                record.id = cursor.lastrowid
            else:
                keys = list(fields.keys())
                set_clause = ", ".join(f"{k} = ?" for k in keys)
                sql = f"UPDATE {table_name} SET {set_clause} WHERE id = ?"
                params = tuple(fields[k] for k in keys) + (record.id,)
                await self.db.execute(sql, params)
                
        await self.db.commit()
        self._added_records.clear()

    async def execute(self, query, params=None):
        if isinstance(query, str):
            cursor = await self.db.execute(query, params or ())
            await self.db.commit()
            return cursor
            
        if isinstance(query, MockUpdate):
            table_name = "tasks" if query.table_class == TaskRecord else "telemetry_records"
            fields = query._values
            for k, v in fields.items():
                if isinstance(v, datetime.datetime):
                    fields[k] = v.isoformat()
            keys = list(fields.keys())
            set_clause = ", ".join(f"{k} = ?" for k in keys)
            sql = f"UPDATE {table_name} SET {set_clause}"
            query_params = [fields[k] for k in keys]
            if query.where_clauses:
                sql += " WHERE " + " AND ".join(f"{c.name} {c.op} ?" for c in query.where_clauses)
                query_params.extend(c.value for c in query.where_clauses)
            cursor = await self.db.execute(sql, tuple(query_params))
            await self.db.commit()
            return cursor
            
        elif isinstance(query, MockSelect):
            is_count = False
            select_cols = "*"
            
            if len(query.columns) == 1 and query.columns[0] == "COUNT":
                is_count = True
                select_cols = "COUNT(*)"
            elif len(query.columns) == 2 and "COUNT" in query.columns:
                is_count = True
                non_count = [c.col_name for c in query.columns if isinstance(c, MockColumn)][0]
                select_cols = f"{non_count}, COUNT(*)"
            elif query.columns:
                cols = []
                for c in query.columns:
                    if isinstance(c, MockColumn):
                        cols.append(c.col_name)
                if cols:
                    select_cols = ", ".join(cols)
                    
            TASK_FIELDS = {"task_id", "submitted_at", "name", "script", "priority_str", "status", "assigned_node", "dispatched_at", "completed_at", "stdout", "stderr", "exit_code", "duration_secs", "has_artifact", "artifact_path", "output_artifact_path", "script_md5", "submit_carbon_gco2", "retry_count", "parent_job_id", "chunk_index", "chunk_count"}
            table_name = "telemetry_records"
            orm_class = TelemetryRecord
            
            is_tasks = False
            if query.columns:
                first = query.columns[0]
                # Direct class reference: select(TaskRecord)
                if first is TaskRecord or (isinstance(first, type) and first.__name__ == "TaskRecord"):
                    is_tasks = True
                # MockColumn with task-specific field name
                elif any(isinstance(c, MockColumn) and c.col_name in TASK_FIELDS for c in query.columns):
                    is_tasks = True
            if not is_tasks and query.where_clauses and any(c.name in TASK_FIELDS for c in query.where_clauses):
                is_tasks = True
                
            if is_tasks:
                table_name = "tasks"
                orm_class = TaskRecord

            sql = f"SELECT {select_cols} FROM {table_name}"
            params = []
            
            if query.where_clauses:
                sql += " WHERE " + " AND ".join(f"{c.name} {c.op} ?" for c in query.where_clauses)
                params.extend(c.value for c in query.where_clauses)
                
            if query._group_by:
                col_name = query._group_by.col_name if isinstance(query._group_by, MockColumn) else str(query._group_by)
                sql += f" GROUP BY {col_name}"
                
            if query._order_by:
                order_clauses = []
                for c in query._order_by:
                    if isinstance(c, OrderExpr):
                        order_clauses.append(f"{c.col_name} {c.direction}")
                    elif isinstance(c, MockColumn):
                        order_clauses.append(f"{c.col_name} ASC")   # bare column = ASC
                    else:
                        order_clauses.append(str(c))
                sql += " ORDER BY " + ", ".join(order_clauses)
                    
            if query._limit is not None:
                sql += f" LIMIT {query._limit}"
                
            cursor = await self.db.execute(sql, tuple(params))
            rows = await cursor.fetchall()
            
            mapped_rows = []
            for r in rows:
                if is_count:
                    mapped_rows.append(tuple(r))
                else:
                    mapped_rows.append(dict(r))
                    
            return MockResult(mapped_rows, None if is_count else orm_class)

class AsyncSessionLocal:
    def __init__(self):
        self.session = AsyncSession()

    async def __aenter__(self):
        return await self.session.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.__aexit__(exc_type, exc_val, exc_tb)

async def get_db():
    async with AsyncSession() as session:
        yield session

async def create_tables() -> None:
    """Create all ORM tables + indexes if they do not already exist (idempotent)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # ── Performance pragmas (applied every connection) ─────────────────────
        # WAL mode: readers don't block writers; ~3-5× faster for mixed workloads
        await db.execute("PRAGMA journal_mode=WAL")
        # NORMAL is safe for WAL — no fsync on every commit; OS crash-safe
        await db.execute("PRAGMA synchronous=NORMAL")
        # Larger page cache = fewer I/O round-trips
        await db.execute("PRAGMA cache_size=-8000")   # 8 MB

        await db.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT NOT NULL,
                node_id TEXT NOT NULL,
                cpu_usage_pct REAL NOT NULL,
                ram_usage_pct REAL NOT NULL,
                kb_events_per_min INTEGER NOT NULL,
                mouse_events_per_min INTEGER NOT NULL,
                net_io_bytes INTEGER NOT NULL,
                process_count INTEGER NOT NULL,
                carbon_intensity_gco2 REAL NOT NULL DEFAULT 0.0,
                predicted_label INTEGER,
                predicted_state TEXT,
                prediction_confidence REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                submitted_at TEXT NOT NULL,
                name TEXT NOT NULL,
                script TEXT NOT NULL,
                priority_str TEXT NOT NULL DEFAULT 'deferrable',
                status TEXT NOT NULL DEFAULT 'pending',
                assigned_node TEXT,
                dispatched_at TEXT,
                completed_at TEXT,
                stdout TEXT,
                stderr TEXT,
                exit_code INTEGER,
                duration_secs REAL,
                has_artifact INTEGER NOT NULL DEFAULT 0,
                artifact_path TEXT,
                output_artifact_path TEXT,
                script_md5 TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                parent_job_id TEXT,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 1
            )
        """)
        
        # Add new columns to existing tables in case the schema evolved
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN script_md5 TEXT")
        except aiosqlite.OperationalError:
            pass # Column already exists
        
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN has_artifact INTEGER NOT NULL DEFAULT 0")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN artifact_path TEXT")
        except aiosqlite.OperationalError:
            pass
            
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN output_artifact_path TEXT")
        except aiosqlite.OperationalError:
            pass

        # Grid carbon intensity (g CO2/kWh) at the moment the task was submitted.
        # Used by the carbon ledger as the naive "run-now" baseline.
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN submit_carbon_gco2 REAL")
        except aiosqlite.OperationalError:
            pass

        # Number of times a task has been re-queued after a node failure.
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
        except aiosqlite.OperationalError:
            pass

        # Data-parallel job columns: a parallel job is a set of tasks sharing a
        # parent_job_id, each running the same script over its own chunk slice.
        for _stmt in (
            "ALTER TABLE tasks ADD COLUMN parent_job_id TEXT",
            "ALTER TABLE tasks ADD COLUMN chunk_index INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 1",
        ):
            try:
                await db.execute(_stmt)
            except aiosqlite.OperationalError:
                pass
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dispatch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                action TEXT,
                reason TEXT,
                carbon REAL,
                q_values TEXT,
                ts TEXT
            )
        """)
        # ── Indexes for hot query paths ──────────────────────────────────────
        # Dispatcher polls pending tasks every 2s — this index is critical
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
        )
        # task_id lookups from REST API and dispatcher
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks(task_id)"
        )
        # Priority-ordered dispatch queries
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority_status "
            "ON tasks(status, priority_str, submitted_at)"
        )
        # Telemetry queries ordered by time per node
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_telemetry_node_time "
            "ON telemetry_records(node_id, recorded_at)"
        )
        await db.commit()
