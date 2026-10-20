import sqlite3
from typing import Generator
from app.config import DB_PATH

def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    target_path = db_path or DB_PATH
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table: str, column_name: str, column_def: str) -> None:
    """Safely adds a column to an existing table if it does not already exist."""
    cursor.execute(f"PRAGMA table_info({table});")
    existing_columns = [col[1] for col in cursor.fetchall()]
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def};")

def _backfill_historical_and_ended_events(cursor: sqlite3.Cursor) -> None:
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

def init_db(conn: sqlite3.Connection | None = None) -> None:
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    cursor = conn.cursor()
    
    # 1. Events Table (Normalized schema supporting Stage 1 & Stage 3)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Safe migration for existing events table in events.db (adds missing columns without resetting data)
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

    # Index for fast deduplication on source_name + source_event_id
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_events_source_lookup
    ON events (source_name, source_event_id);
    """)

    # Safe backfill for ended events (ensures accurate metadata for past events without deleting rows)
    _backfill_historical_and_ended_events(cursor)

    # 2. Stage 2: Registration Actions Table (Persistent & Idempotent)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registration_actions (
        id TEXT PRIMARY KEY,
        event_id INTEGER NOT NULL,
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
        FOREIGN KEY (event_id) REFERENCES events (id),
        UNIQUE (event_id, student_email)
    );
    """)

    # 3. Stage 2: Append-Only Audit Trail Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS registration_audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id TEXT NOT NULL,
        from_status TEXT,
        to_status TEXT NOT NULL,
        actor TEXT NOT NULL,
        event_type TEXT NOT NULL,
        details TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (action_id) REFERENCES registration_actions (id)
    );
    """)

    # 4. Stage 4C: Adapter Sync History Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS adapter_sync_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT NOT NULL,
        status TEXT NOT NULL,
        events_fetched INTEGER NOT NULL DEFAULT 0,
        events_upserted INTEGER NOT NULL DEFAULT 0,
        notes TEXT,
        error_message TEXT,
        synced_at TEXT NOT NULL
    );
    """)

    # 5. Stage 4C & 4E: Persisted Student Profile Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_profiles (
        id INTEGER PRIMARY KEY,
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

    # Safe migrations for student_profiles table (adds missing columns without resetting data)
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notification_preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # 7. In-App Notifications Table (with unique dedup_key for duplicate suppression)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL DEFAULT 'student@ziro.local',
        event_id INTEGER,
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
        dedup_key TEXT UNIQUE,
        FOREIGN KEY (event_id) REFERENCES events (id)
    );
    """)

    # 8. User Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        picture TEXT,
        is_profile_complete INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # 9. External Provider Identity Mapping (Google OIDC sub mapping)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_identities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        provider TEXT NOT NULL DEFAULT 'google',
        provider_sub TEXT NOT NULL,
        email TEXT NOT NULL,
        email_verified INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
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
        user_id INTEGER NOT NULL,
        csrf_token TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_active_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_sessions_lookup
    ON user_sessions (session_id, expires_at);
    """)

    # 11. Ephemeral OAuth States Table (Anti-CSRF & Nonce)
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

    conn.commit()
    if close_after:
        conn.close()

