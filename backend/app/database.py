import os
import re
import sqlite3
from typing import Generator, Any, Optional, Dict, List, Tuple
from pathlib import Path

from app.config import DB_PATH, DATABASE_URL, IS_POSTGRES, IS_PRODUCTION, get_masked_database_url

try:
    import psycopg
    from psycopg.rows import dict_row
    import psycopg.errors
    HAS_PSYCOPG = True
    IntegrityError = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
except ImportError:
    HAS_PSYCOPG = False
    IntegrityError = (sqlite3.IntegrityError,)

# Tables with integer auto-increment/identity IDs where INSERT statements need lastrowid
TABLES_WITH_IDENTITY_ID = {
    "events",
    "registration_audit_logs",
    "adapter_sync_logs",
    "student_profiles",
    "notification_preferences",
    "notifications",
    "users",
    "user_identities",
}


class DbRow:
    """
    Unified database row wrapper providing dual access by column name (dict-like)
    and by positional index (tuple-like) to ensure full compatibility with sqlite3.Row.
    """
    __slots__ = ("_data", "_keys", "_values")

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self._keys = list(data.keys())
        self._values = tuple(data.values())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._data[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._data

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def __repr__(self) -> str:
        return f"DbRow({self._data})"


def translate_sql_for_postgres(sql: str) -> str:
    """
    Translates SQLite-dialect SQL into PostgreSQL-compatible SQL:
    1. Translates 'INSERT OR IGNORE INTO notifications' to 'INSERT INTO notifications ... ON CONFLICT (dedup_key) DO NOTHING'
    2. Replaces unquoted '?' parameter placeholders with '%s'
    """
    s = sql.strip()
    # Normalize 'INSERT OR IGNORE' for notifications table
    if s.upper().startswith("INSERT OR IGNORE INTO NOTIFICATIONS"):
        s = "INSERT" + s[len("INSERT OR IGNORE"):]
        if "ON CONFLICT" not in s.upper():
            if s.endswith(";"):
                s = s[:-1].rstrip() + " ON CONFLICT (dedup_key) DO NOTHING;"
            else:
                s = s + " ON CONFLICT (dedup_key) DO NOTHING"

    # Replace unquoted '?' with '%s'
    out = []
    in_single = False
    in_double = False
    escaped = False
    for ch in s:
        if ch == "'" and not in_double and not escaped:
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single and not escaped:
            in_double = not in_double
            out.append(ch)
        elif ch == '?' and not in_single and not in_double:
            out.append('%s')
        else:
            out.append(ch)
        escaped = (ch == '\\' and not escaped)
    return ''.join(out)


class PostgresCursorWrapper:
    """
    Wraps a psycopg cursor to match the sqlite3 cursor API:
    - Translates '?' placeholders to '%s'
    - Wraps returned dict rows in DbRow
    - Captures lastrowid for identity inserts via automatic 'RETURNING id'
    """
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid: Optional[int] = None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def close(self):
        self._cur.close()

    def execute(self, query: str, params: Optional[Any] = None):
        # Ignore SQLite PRAGMA statements safely on Postgres
        cleaned = query.strip()
        if cleaned.upper().startswith("PRAGMA FOREIGN_KEYS"):
            return self

        # Translate PRAGMA table_info(table)
        if cleaned.upper().startswith("PRAGMA TABLE_INFO"):
            tbl_match = re.search(r"PRAGMA\s+table_info\s*\(\s*['\"]?(\w+)['\"]?\s*\)", cleaned, re.IGNORECASE)
            if tbl_match:
                table_name = tbl_match.group(1).lower()
                pg_query = (
                    "SELECT ordinal_position - 1 AS cid, column_name AS name, data_type AS type, "
                    "CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, column_default AS dflt_value, 0 AS pk "
                    "FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position;"
                )
                self._cur.execute(pg_query, (table_name,))
                return self

        pg_sql = translate_sql_for_postgres(cleaned)

        # Detect INSERT into identity tables that do not already have RETURNING
        is_insert = pg_sql.strip().upper().startswith("INSERT INTO")
        appended_returning = False
        if is_insert and "RETURNING" not in pg_sql.upper():
            # Check target table name
            match = re.search(r"INSERT\s+INTO\s+([a-zA-Z0-9_]+)", pg_sql, re.IGNORECASE)
            if match:
                table_name = match.group(1).lower()
                if table_name in TABLES_WITH_IDENTITY_ID:
                    if pg_sql.rstrip().endswith(";"):
                        pg_sql = pg_sql.rstrip()[:-1].rstrip() + " RETURNING id;"
                    else:
                        pg_sql = pg_sql + " RETURNING id"
                    appended_returning = True

        if params is not None:
            # Convert list/tuple if needed
            p_tuple = tuple(params) if isinstance(params, (list, tuple)) else params
            self._cur.execute(pg_sql, p_tuple)
        else:
            self._cur.execute(pg_sql)

        if appended_returning:
            row = self._cur.fetchone()
            if row:
                self.lastrowid = row.get("id") if isinstance(row, dict) else row[0]
            else:
                self.lastrowid = None
        else:
            self.lastrowid = None

        return self

    def executemany(self, query: str, params_seq: Any):
        pg_sql = translate_sql_for_postgres(query)
        self._cur.executemany(pg_sql, params_seq)
        return self

    def fetchone(self) -> Optional[DbRow]:
        row = self._cur.fetchone()
        if row is None:
            return None
        return DbRow(row) if isinstance(row, dict) else row

    def fetchall(self) -> List[DbRow]:
        rows = self._cur.fetchall()
        return [DbRow(r) if isinstance(r, dict) else r for r in rows]

    def fetchmany(self, size: int = 1) -> List[DbRow]:
        rows = self._cur.fetchmany(size)
        return [DbRow(r) if isinstance(r, dict) else r for r in rows]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row


class PostgresConnectionWrapper:
    """
    Wraps a psycopg Connection to match Python's sqlite3 Connection interface.
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self.is_postgres = True

    def cursor(self):
        raw_cur = self._conn.cursor(row_factory=dict_row)
        return PostgresCursorWrapper(raw_cur)

    def execute(self, query: str, params: Optional[Any] = None) -> PostgresCursorWrapper:
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_connection(db_target: Optional[str] = None):
    """
    Factory creating a database connection:
    - If DATABASE_URL is set (or db_target is a postgresql URL), returns PostgresConnectionWrapper
    - Otherwise, returns a native sqlite3.Connection with foreign keys enabled
    """
    target = db_target or (DATABASE_URL if IS_POSTGRES else DB_PATH)

    if target.startswith("postgresql://") or target.startswith("postgres://"):
        if not HAS_PSYCOPG:
            raise RuntimeError(
                "psycopg is required to connect to PostgreSQL. "
                "Please run: pip install 'psycopg[binary]>=3.1.18'"
            )
        # Ensure sslmode=require for Neon / remote connections unless already configured or disabled
        pg_url = target
        if "sslmode=" not in pg_url and ("neon.tech" in pg_url or "onrender.com" in pg_url or "render.com" in pg_url):
            sep = "&" if "?" in pg_url else "?"
            pg_url = f"{pg_url}{sep}sslmode=require"

        raw_conn = psycopg.connect(pg_url, autocommit=False)
        return PostgresConnectionWrapper(raw_conn)

    # SQLite connection
    if IS_PRODUCTION and not db_target:
        raise RuntimeError(
            "Production environment requires DATABASE_URL to be set to a valid PostgreSQL connection string. "
            "Silent fallback to local SQLite is strictly disallowed in production."
        )

    if target.startswith("file:"):
        conn = sqlite3.connect(target, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn



def get_db() -> Generator[Any, None, None]:
    """FastAPI dependency yielding an active database connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _add_column_if_not_exists(cursor, table: str, column_name: str, column_def: str) -> None:
    """Safely adds a column to an existing table if it does not already exist."""
    is_pg = getattr(cursor, "_cur", None) is not None
    if is_pg:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s;",
            (table.lower(),)
        )
        existing_columns = [
            (row[0] if isinstance(row, tuple) else row.get("column_name")).lower()
            for row in cursor.fetchall()
        ]
    else:
        cursor.execute(f"PRAGMA table_info({table});")
        existing_columns = [col[1].lower() for col in cursor.fetchall()]

    if column_name.lower() not in existing_columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def};")


def _backfill_historical_and_ended_events(cursor) -> None:
    """
    Idempotent backfill that inspects existing event rows.
    If an event's submission period, end_date, or deadline concluded in the past,
    normalizes its start_date, end_date, and marks deadline_status='closed'.
    Preserves all records and historical integrity without deleting any rows.
    """
    try:
        from app.normalization import parse_date_range_string, is_date_in_past
    except ImportError:
        return

    cursor.execute("""
    SELECT id, title, deadline_notes, deadline, start_date, end_date, deadline_status
    FROM events
    WHERE deadline_status != 'closed' OR start_date IS NULL OR end_date IS NULL;
    """)
    rows = cursor.fetchall()
    for row in rows:
        eid = row["id"]
        title = row["title"]
        notes = row["deadline_notes"] or ""
        dl = row["deadline"]
        s_date = row["start_date"]
        e_date = row["end_date"]

        parsed_s, parsed_e = None, None
        if "Submission period:" in notes:
            part = notes.split("Submission period:")[1].split(".")[0].strip().strip("'\"")
            parsed_s, parsed_e = parse_date_range_string(part)
        elif notes and not s_date and not e_date:
            parsed_s, parsed_e = parse_date_range_string(notes)

        new_s = s_date or parsed_s
        new_e = e_date or parsed_e

        is_past = False
        if new_e and is_date_in_past(new_e):
            is_past = True
        elif dl and is_date_in_past(dl):
            is_past = True

        if is_past:
            new_notes = notes
            if "Ended" not in new_notes and new_e:
                new_notes = f"Official status: Ended. Submission period concluded on {new_e}."
            cursor.execute("""
            UPDATE events
            SET deadline_status = 'closed',
                start_date = COALESCE(start_date, ?),
                end_date = COALESCE(end_date, ?),
                deadline_notes = ?
            WHERE id = ?;
            """, (new_s, new_e, new_notes, eid))
        elif (new_s and new_s != s_date) or (new_e and new_e != e_date):
            cursor.execute("""
            UPDATE events
            SET start_date = COALESCE(start_date, ?),
                end_date = COALESCE(end_date, ?)
            WHERE id = ?;
            """, (new_s, new_e, eid))


def init_db(conn: Optional[Any] = None, commit: bool = True) -> None:
    """
    Initializes database schema and runs non-destructive additive migrations.
    Supports both SQLite and PostgreSQL.

    Args:
        conn: Database connection. If None, a connection is created and closed.
        commit: Whether to commit changes at the end of initialization (default True).
                Set to False when the caller manages transaction lifecycle explicitly.
    """
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    cursor = conn.cursor()
    is_pg = getattr(conn, "is_postgres", False)

    # Dialect-specific primary key generator
    pk_id_def = (
        "id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
        if is_pg
        else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )

    # 1. Events Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS events (
        {pk_id_def},
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        organizer TEXT NOT NULL,
        source_name TEXT NOT NULL DEFAULT 'Synthetic',
        source_event_id TEXT,
        source_url TEXT NOT NULL,
        registration_url TEXT,
        retrieved_at TEXT NOT NULL,
        team_min INTEGER NOT NULL DEFAULT 1,
        team_max INTEGER NOT NULL DEFAULT 4,
        fee_amount REAL,
        fee_currency TEXT NOT NULL DEFAULT 'USD',
        fee_status TEXT NOT NULL DEFAULT 'unknown',
        deadline TEXT,
        timezone TEXT NOT NULL DEFAULT 'UTC',
        start_date TEXT,
        end_date TEXT,
        location TEXT NOT NULL DEFAULT 'Online',
        region TEXT NOT NULL DEFAULT 'Global / Online',
        country TEXT,
        format TEXT NOT NULL DEFAULT 'Online / Virtual',
        eligibility_requirements TEXT NOT NULL DEFAULT 'Open to eligible participants',
        verification_status TEXT NOT NULL DEFAULT 'verified',
        deadline_status TEXT NOT NULL DEFAULT 'verified',
        deadline_notes TEXT,
        prize_info TEXT,
        evidence_notes TEXT,
        is_synthetic INTEGER NOT NULL DEFAULT 1,
        data_source_type TEXT NOT NULL DEFAULT 'synthetic_demo_fixture',
        tags TEXT NOT NULL DEFAULT 'Hackathon'
    );
    """)

    _add_column_if_not_exists(cursor, "events", "source_name", "source_name TEXT NOT NULL DEFAULT 'Synthetic'")
    _add_column_if_not_exists(cursor, "events", "source_event_id", "source_event_id TEXT")
    _add_column_if_not_exists(cursor, "events", "registration_url", "registration_url TEXT")
    _add_column_if_not_exists(cursor, "events", "location", "location TEXT NOT NULL DEFAULT 'Online'")
    _add_column_if_not_exists(cursor, "events", "start_date", "start_date TEXT")
    _add_column_if_not_exists(cursor, "events", "end_date", "end_date TEXT")
    _add_column_if_not_exists(cursor, "events", "country", "country TEXT")
    _add_column_if_not_exists(cursor, "events", "deadline_status", "deadline_status TEXT NOT NULL DEFAULT 'verified'")
    _add_column_if_not_exists(cursor, "events", "deadline_notes", "deadline_notes TEXT")
    _add_column_if_not_exists(cursor, "events", "prize_info", "prize_info TEXT")
    _add_column_if_not_exists(cursor, "events", "eligibility_requirements", "eligibility_requirements TEXT NOT NULL DEFAULT 'Open to eligible participants'")
    _add_column_if_not_exists(cursor, "events", "verification_status", "verification_status TEXT NOT NULL DEFAULT 'verified'")
    _add_column_if_not_exists(cursor, "events", "evidence_notes", "evidence_notes TEXT")
    _add_column_if_not_exists(cursor, "events", "is_synthetic", "is_synthetic INTEGER NOT NULL DEFAULT 1")

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_source_lookup
    ON events (source_name, source_event_id);
    """)

    # Safe backfill for ended events
    _backfill_historical_and_ended_events(cursor)

    # 2. Registration Actions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registration_actions (
        id TEXT PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES events (id),
        student_email TEXT NOT NULL,
        student_name TEXT NOT NULL,
        team_size INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        approved_at TEXT,
        approved_by TEXT,
        approval_notes TEXT,
        submitted_at TEXT,
        verification_evidence TEXT,
        is_simulation INTEGER NOT NULL DEFAULT 1,
        simulation_notice TEXT NOT NULL DEFAULT 'Simulated workflow: No external registration submitted. Demo record only.',
        UNIQUE (event_id, student_email)
    );
    """)

    # 3. Registration Audit Logs Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS registration_audit_logs (
        {pk_id_def},
        action_id TEXT NOT NULL REFERENCES registration_actions (id),
        from_status TEXT,
        to_status TEXT NOT NULL,
        actor TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 4. Adapter Sync History Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS adapter_sync_logs (
        {pk_id_def},
        source_name TEXT NOT NULL,
        status TEXT NOT NULL,
        events_fetched INTEGER NOT NULL DEFAULT 0,
        events_upserted INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        error_message TEXT,
        synced_at TEXT NOT NULL
    );
    """)

    # 5. Persisted Student Profile Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS student_profiles (
        {pk_id_def},
        student_name TEXT,
        student_email TEXT,
        skills TEXT NOT NULL DEFAULT '',
        team_size INTEGER NOT NULL DEFAULT 2,
        region TEXT NOT NULL DEFAULT 'All',
        start_date TEXT,
        end_date TEXT,
        budget REAL,
        institution TEXT,
        degree TEXT,
        graduation_year TEXT,
        github_url TEXT,
        linkedin_url TEXT,
        portfolio_url TEXT,
        bio TEXT,
        collaboration_preference TEXT,
        projects_json TEXT,
        participation_mode TEXT DEFAULT 'All',
        updated_at TEXT NOT NULL
    );
    """)

    _add_column_if_not_exists(cursor, "student_profiles", "institution", "institution TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "degree", "degree TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "graduation_year", "graduation_year TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "github_url", "github_url TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "linkedin_url", "linkedin_url TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "portfolio_url", "portfolio_url TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "bio", "bio TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "collaboration_preference", "collaboration_preference TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "projects_json", "projects_json TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "participation_mode", "participation_mode TEXT DEFAULT 'All'")

    # 6. Notification Preferences Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS notification_preferences (
        {pk_id_def},
        user_email TEXT NOT NULL DEFAULT 'student@ziro.local',
        matching_events_enabled INTEGER NOT NULL DEFAULT 1,
        upcoming_deadlines_enabled INTEGER NOT NULL DEFAULT 1,
        deadline_changes_enabled INTEGER NOT NULL DEFAULT 1,
        master_reminders_enabled INTEGER NOT NULL DEFAULT 1,
        remind_7_days INTEGER NOT NULL DEFAULT 1,
        remind_48_hours INTEGER NOT NULL DEFAULT 1,
        remind_24_hours INTEGER NOT NULL DEFAULT 1,
        browser_notifications_enabled INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE (user_email)
    );
    """)

    # 7. In-App Notifications Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS notifications (
        {pk_id_def},
        user_email TEXT NOT NULL DEFAULT 'student@ziro.local',
        event_id INTEGER REFERENCES events (id),
        category TEXT NOT NULL,
        reminder_interval TEXT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        event_title TEXT NOT NULL,
        deadline_ist TEXT,
        deadline_formatted TEXT,
        remaining_time TEXT,
        official_url TEXT,
        source_name TEXT,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        dedup_key TEXT UNIQUE
    );
    """)

    # 8. User Accounts Table
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        {pk_id_def},
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        picture TEXT,
        is_profile_complete INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 9. External Provider Identity Mapping
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS user_identities (
        {pk_id_def},
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        provider TEXT NOT NULL DEFAULT 'google',
        provider_sub TEXT NOT NULL,
        email TEXT NOT NULL,
        email_verified INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (provider, provider_sub)
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_identities_sub
    ON user_identities (provider, provider_sub);
    """)

    # 10. Authenticated Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        csrf_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_active_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_sessions_lookup
    ON user_sessions (session_id, expires_at);
    """)

    # 11. Ephemeral OAuth States Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS oauth_states (
        state TEXT PRIMARY KEY,
        nonce TEXT NOT NULL,
        return_to TEXT,
        client_origin TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """)

    # Additive migrations: link existing tables to user_id without resetting data
    _add_column_if_not_exists(cursor, "oauth_states", "client_origin", "client_origin TEXT")
    _add_column_if_not_exists(cursor, "student_profiles", "user_id", "user_id INTEGER")
    _add_column_if_not_exists(cursor, "registration_actions", "user_id", "user_id INTEGER")
    _add_column_if_not_exists(cursor, "notifications", "user_id", "user_id INTEGER")

    # Safe backfill: resolve verified deadlines for active Devpost events where evidence exists
    try:
        from app.adapters.devpost import backfill_devpost_deadlines
        backfill_devpost_deadlines(conn)
    except Exception:
        pass

    if commit:
        conn.commit()
    if close_after:
        conn.close()
