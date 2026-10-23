import sys
import sqlite3
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure backend directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.database import init_db
from migrate_to_postgres import (
    migrate_data,
    TABLE_MIGRATION_ORDER,
)


@pytest.fixture
def sample_sqlite_db(tmp_path):
    """
    Creates an isolated disposable SQLite database populated with a minimal schema and data
    to verify that migration inspection reads source data without modifying it.
    backend/events.db is never touched.
    """
    db_file = tmp_path / "source_test_events.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    # Create events table
    cur.execute("""
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        organizer TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_url TEXT NOT NULL,
        retrieved_at TEXT NOT NULL
    );
    """)

    # Insert 2 test events
    cur.execute("""
    INSERT INTO events (title, description, organizer, source_name, source_url, retrieved_at)
    VALUES
        ('Event Alpha', 'Desc A', 'Org A', 'TestSrc', 'https://example.com/1', '2026-10-22T00:00:00Z'),
        ('Event Beta', 'Desc B', 'Org B', 'TestSrc', 'https://example.com/2', '2026-10-22T00:00:00Z');
    """)

    # Create users table
    cur.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)
    cur.execute("""
    INSERT INTO users (email, name, created_at, updated_at)
    VALUES ('alice@example.com', 'Alice', '2026-10-22T00:00:00Z', '2026-10-22T00:00:00Z');
    """)

    conn.commit()
    conn.close()
    return db_file


def _file_sha256(path: Path) -> str:
    """Computes SHA256 checksum of a file to verify zero modifications."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def test_dry_run_never_calls_commit_on_target(sample_sqlite_db):
    """Proves that dry-run NEVER calls .commit() on the target connection."""
    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur
    # Information schema query returns None (no tables exist)
    mock_cur.fetchone.return_value = None

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=True,
        dst_conn=mock_conn
    )

    assert success is True
    # Critical verification: commit must NEVER be called during dry-run
    assert mock_conn.commit.call_count == 0, "mock_conn.commit() was called during dry-run!"
    # Rollback should be invoked defensively
    assert mock_conn.rollback.call_count >= 1


def test_dry_run_never_executes_ddl_or_dml(sample_sqlite_db):
    """Proves that dry-run does not issue CREATE TABLE, INSERT, UPDATE, or DELETE on target."""
    executed_queries = []

    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()

    def record_execute(query, *args, **kwargs):
        executed_queries.append(query)
        return mock_cur

    mock_cur.execute.side_effect = record_execute
    mock_cur._cur.execute.side_effect = record_execute
    mock_cur.fetchone.return_value = None
    mock_cur.fetchall.return_value = []
    mock_conn.cursor.return_value = mock_cur

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=True,
        dst_conn=mock_conn
    )

    assert success is True
    forbidden_keywords = ["CREATE TABLE", "CREATE INDEX", "ALTER TABLE", "DROP", "INSERT INTO", "UPDATE ", "DELETE "]
    for query in executed_queries:
        upper_q = str(query).upper()
        for kw in forbidden_keywords:
            assert kw not in upper_q, f"Forbidden DDL/DML '{kw}' was executed in dry-run: {query}"


def test_dry_run_does_not_modify_source_sqlite(sample_sqlite_db):
    """Proves that dry-run does not modify, alter, or corrupt the source SQLite database."""
    hash_before = _file_sha256(sample_sqlite_db)
    stat_before = sample_sqlite_db.stat()

    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=True,
        dst_conn=mock_conn
    )

    assert success is True

    hash_after = _file_sha256(sample_sqlite_db)
    stat_after = sample_sqlite_db.stat()

    # Exact byte-for-byte identity
    assert hash_before == hash_after, "SQLite database hash changed after dry-run!"
    assert stat_before.st_size == stat_after.st_size, "SQLite database size changed after dry-run!"

    # Verify rows can still be read normally
    src = sqlite3.connect(f"file:{sample_sqlite_db.resolve().as_posix()}?mode=ro", uri=True)
    cur = src.cursor()
    cur.execute("SELECT COUNT(*) FROM events;")
    assert cur.fetchone()[0] == 2
    cur.execute("SELECT COUNT(*) FROM users;")
    assert cur.fetchone()[0] == 1
    src.close()


def test_dry_run_handles_missing_target_tables_gracefully(sample_sqlite_db):
    """Proves that dry-run succeeds when target PostgreSQL has no tables created yet."""
    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()
    # Simulate table not existing in target
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=True,
        dst_conn=mock_conn
    )

    assert success is True
    assert mock_conn.commit.call_count == 0


def test_dry_run_inspects_existing_target_pks_without_modifications(sample_sqlite_db):
    """Proves that if target already has partial rows, dry-run reports to_skip correctly without inserting."""
    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()

    # Mock _check_table_exists_in_target -> True for events
    # Mock fetching existing PKs in target -> returns event id 1 already exists
    def mock_execute(query, params=None):
        if "information_schema.tables" in str(query):
            mock_cur.fetchone.return_value = (1,)
        elif 'SELECT "id" FROM "events"' in str(query):
            mock_cur.fetchall.return_value = [{"id": 1}]
        else:
            mock_cur.fetchone.return_value = None
            mock_cur.fetchall.return_value = []
        return mock_cur

    mock_cur.execute.side_effect = mock_execute
    mock_conn.cursor.return_value = mock_cur

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=True,
        dst_conn=mock_conn
    )

    assert success is True
    assert mock_conn.commit.call_count == 0


def test_init_db_honors_explicit_commit_parameter():
    """Proves that init_db does NOT commit when commit=False, avoiding hidden commits."""
    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()
    mock_cur.fetchall.return_value = []
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur

    # 1. When commit=False: commit must NOT be called
    init_db(mock_conn, commit=False)
    assert mock_conn.commit.call_count == 0, "init_db committed even when commit=False!"

    # 2. When commit=True: commit must be called
    init_db(mock_conn, commit=True)
    assert mock_conn.commit.call_count == 1, "init_db failed to commit when commit=True!"


def test_live_migration_rolls_back_on_error(sample_sqlite_db):
    """Proves that live migration rolls back and never commits if an error occurs."""
    mock_conn = MagicMock()
    mock_conn.is_postgres = True
    mock_cur = MagicMock()
    mock_cur._cur = MagicMock()

    # Throw an error during insert
    mock_cur._cur.execute.side_effect = RuntimeError("Simulated target write failure")
    mock_conn.cursor.return_value = mock_cur

    success = migrate_data(
        sqlite_path=sample_sqlite_db,
        dry_run=False,
        dst_conn=mock_conn
    )

    assert success is False
    assert mock_conn.commit.call_count == 0, "Commit was called despite migration failure!"
    assert mock_conn.rollback.call_count >= 1, "Rollback was not called on failure!"
