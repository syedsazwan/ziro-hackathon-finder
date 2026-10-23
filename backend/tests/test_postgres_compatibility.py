import os
import subprocess
import pytest
from app.config import get_masked_database_url, IS_POSTGRES
from app.database import (
    translate_sql_for_postgres,
    DbRow,
    get_connection,
    init_db,
    HAS_PSYCOPG,
)


def test_translate_sql_parameter_placeholders():
    """Verify that translate_sql_for_postgres replaces '?' outside quotes with '%s'."""
    raw = "SELECT id, title FROM events WHERE title = ? AND organizer = ?;"
    translated = translate_sql_for_postgres(raw)
    assert translated == "SELECT id, title FROM events WHERE title = %s AND organizer = %s;"


def test_translate_sql_preserves_question_marks_inside_quotes():
    """Verify that '?' inside string literals is preserved verbatim."""
    raw = "SELECT * FROM events WHERE title = 'Who will win?' AND status = ?;"
    translated = translate_sql_for_postgres(raw)
    assert translated == "SELECT * FROM events WHERE title = 'Who will win?' AND status = %s;"


def test_translate_sql_insert_or_ignore():
    """Verify that INSERT OR IGNORE is translated to standard ON CONFLICT DO NOTHING."""
    raw = "INSERT OR IGNORE INTO notifications (user_email, dedup_key) VALUES (?, ?);"
    translated = translate_sql_for_postgres(raw)
    assert "INSERT INTO notifications" in translated
    assert "ON CONFLICT (dedup_key) DO NOTHING" in translated
    assert "%s, %s" in translated


def test_dbrow_dual_access():
    """Verify that DbRow supports both dictionary key access and tuple/index unpacking."""
    row = DbRow({"id": 42, "title": "AI Innovation Hack", "deadline": "2026-11-15"})

    # Dictionary key access
    assert row["id"] == 42
    assert row["title"] == "AI Innovation Hack"
    assert row["deadline"] == "2026-11-15"
    assert row.get("nonexistent", "fallback") == "fallback"
    assert "title" in row

    # Index access
    assert row[0] == 42
    assert row[1] == "AI Innovation Hack"
    assert row[2] == "2026-11-15"

    # Tuple unpacking
    val_id, val_title, val_dl = row
    assert val_id == 42
    assert val_title == "AI Innovation Hack"
    assert val_dl == "2026-11-15"

    # Length and keys
    assert len(row) == 3
    assert list(row.keys()) == ["id", "title", "deadline"]


def test_get_masked_database_url_masks_passwords():
    """Verify that database connection strings mask user passwords completely."""
    raw_url = "postgresql://myuser:supersecretpass123@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    masked = get_masked_database_url(raw_url)

    assert "supersecretpass123" not in masked
    assert "myuser:***@" in masked
    assert "ep-sample-pooler.us-east-2.aws.neon.tech" in masked
    assert "neondb" in masked


def test_get_masked_database_url_empty_or_plain():
    """Verify handling of empty or passwordless connection strings."""
    assert get_masked_database_url("") == ""
    assert get_masked_database_url(None) == ""
    assert "sqlite" in get_masked_database_url("sqlite:///events.db") or "events.db" in get_masked_database_url("sqlite:///events.db")


def test_sqlite_fallback_and_integrity():
    """Verify that default local development retains full SQLite functionality."""
    conn = get_connection(":memory:")
    try:
        init_db(conn)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events;")
        res = cur.fetchone()
        assert res is not None
        assert res[0] >= 0
    finally:
        conn.close()


def test_has_psycopg_driver():
    """Verify that psycopg library is installed and available in backend virtual environment."""
    assert HAS_PSYCOPG is True


def test_migrate_script_help():
    """Verify that the migration CLI script loads without syntax errors."""
    import sys
    res = subprocess.run(
        [sys.executable, "migrate_to_postgres.py", "--help"],
        cwd="D:/Ziro/backend",
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Migrate Ziro database from SQLite to Neon PostgreSQL" in res.stdout


def test_production_disallows_sqlite_fallback(monkeypatch):
    """Verify that in production mode, missing DATABASE_URL raises RuntimeError rather than falling back to SQLite."""
    import app.database as db_mod
    monkeypatch.setattr(db_mod, "IS_PRODUCTION", True)
    monkeypatch.setattr(db_mod, "IS_POSTGRES", False)
    monkeypatch.setattr(db_mod, "DATABASE_URL", "")

    with pytest.raises(RuntimeError) as exc_info:
        db_mod.get_connection()
    assert "Production environment requires DATABASE_URL" in str(exc_info.value)
    assert "Silent fallback to local SQLite is strictly disallowed" in str(exc_info.value)

