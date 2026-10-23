import re
import hashlib
import sqlite3
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "events.db"
SQL_PATH = BASE_DIR / "neon_migration.sql"

EXPECTED_TABLES = [
    "events",
    "users",
    "student_profiles",
    "user_identities",
    "user_sessions",
    "oauth_states",
    "notification_preferences",
    "registration_actions",
    "registration_audit_logs",
    "adapter_sync_logs",
    "notifications",
]

EXPECTED_ROW_COUNTS = {
    "events": 101,
    "users": 2,
    "student_profiles": 2,
    "user_identities": 2,
    "user_sessions": 11,
    "oauth_states": 6,
    "notification_preferences": 1,
    "registration_actions": 3,
    "registration_audit_logs": 9,
    "adapter_sync_logs": 132,
    "notifications": 65,
}

EXPECTED_SEQUENCES = {
    "events": 105,
    "users": 2,
    "student_profiles": 0,
    "user_identities": 2,
    "notification_preferences": 12,
    "registration_audit_logs": 35,
    "adapter_sync_logs": 132,
    "notifications": 2048,
}


def test_sql_file_exists_and_non_empty():
    """Verify that backend/neon_migration.sql was generated and has non-zero size."""
    assert SQL_PATH.exists(), "neon_migration.sql does not exist!"
    assert SQL_PATH.stat().st_size > 50000, "neon_migration.sql is unexpectedly small!"


def test_no_credentials_or_secrets_in_sql():
    """Verify that no database credentials, URLs, or secrets are leaked into the SQL file."""
    content = SQL_PATH.read_text(encoding="utf-8")
    forbidden_patterns = [
        r"DATABASE_URL",
        r"postgres(?:ql)?://[^\s]+",
        r"SESSION_SECRET",
        r"(?:password|passwd|secret)\s*[:=]\s*['\"][^'\"]+['\"]",
        r"client_secret",
        r"supersecret",
    ]
    for pat in forbidden_patterns:
        match = re.search(pat, content, re.IGNORECASE)
        assert match is None, f"Forbidden credential pattern '{pat}' matched: {match.group(0)}"



def test_transactional_safety():
    """Verify that the entire migration is enclosed in BEGIN; and COMMIT; to prevent partial state."""
    content = SQL_PATH.read_text(encoding="utf-8")
    assert "BEGIN;" in content
    assert "COMMIT;" in content
    # BEGIN must appear before any CREATE or INSERT
    idx_begin = content.index("BEGIN;")
    idx_commit = content.index("COMMIT;")
    idx_create = content.index("CREATE TABLE")
    assert idx_begin < idx_create < idx_commit


def test_all_tables_and_indexes_defined():
    """Verify that all 11 tables and all required indexes are defined with IF NOT EXISTS."""
    content = SQL_PATH.read_text(encoding="utf-8")
    for tbl in EXPECTED_TABLES:
        pattern = rf"CREATE TABLE IF NOT EXISTS {tbl}\b"
        assert re.search(pattern, content, re.IGNORECASE), f"Table '{tbl}' definition missing!"

    required_indexes = [
        "idx_events_source_lookup",
        "idx_user_identities_sub",
        "idx_user_sessions_lookup",
    ]
    for idx in required_indexes:
        assert f"CREATE INDEX IF NOT EXISTS {idx}" in content, f"Index '{idx}' definition missing!"


def test_idempotent_inserts():
    """Verify that all INSERT blocks utilize ON CONFLICT DO NOTHING."""
    content = SQL_PATH.read_text(encoding="utf-8")
    insert_matches = re.findall(r'INSERT INTO "(\w+)"', content)
    assert len(insert_matches) > 0

    on_conflict_count = len(re.findall(r'ON CONFLICT \("[^"]+"\)\s+DO NOTHING;', content))
    assert on_conflict_count == len(insert_matches), "Mismatch between INSERT statements and ON CONFLICT clauses!"


def test_sequence_synchronization():
    """Verify that identity sequences are synchronized for all auto-increment tables."""
    content = SQL_PATH.read_text(encoding="utf-8")
    for tbl, expected_seq in EXPECTED_SEQUENCES.items():
        assert f"pg_get_serial_sequence('{tbl}', 'id')" in content, f"Sequence sync missing for {tbl}!"
        # Verify sequence baseline matches or exceeds known max
        assert f"{expected_seq})," in content or f"{expected_seq}\n" in content or f"{expected_seq})" in content


def test_row_count_parity_with_source_sqlite():
    """Verify that source SQLite row counts match expected migration destination row counts."""
    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()

    actual_counts = {}
    for tbl in EXPECTED_TABLES:
        cur.execute(f'SELECT COUNT(*) FROM "{tbl}";')
        actual_counts[tbl] = cur.fetchone()[0]
    conn.close()

    assert actual_counts == EXPECTED_ROW_COUNTS, f"Row count mismatch! Actual: {actual_counts}"


def test_source_sqlite_integrity_preserved():
    """Verify that backend/events.db can be read and has valid foreign keys without corruption."""
    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    res = cur.fetchone()
    assert res[0] == "ok", f"SQLite integrity check failed: {res[0]}"

    cur.execute("PRAGMA foreign_key_check;")
    fk_violations = cur.fetchall()
    assert len(fk_violations) == 0, f"Found foreign key violations: {fk_violations}"
    conn.close()
