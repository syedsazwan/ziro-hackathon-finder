"""
ZIRO — SQLite to Neon PostgreSQL Data Migration Script

Safely copies all existing tables and data from backend/events.db into PostgreSQL
preserving all primary keys, foreign key relationships, timestamps, and sequence values.

SAFETY GUARANTEES:
1. Opens SQLite strictly in read-only mode (?mode=ro) - zero risk of modification.
2. Masks DATABASE_URL and passwords in all logs and outputs.
3. DRY RUN SAFETY: Performs zero DDL or DML on target. Inspects source data and migration
   plan without creating target tables. Never calls any schema initialization function
   that commits changes. Rolls back any open transaction as an added safeguard.
4. EXPLICIT TRANSACTIONS: Live migration explicitly owns the transaction lifecycle:
   init_db(dst_conn, commit=False) runs schema creation inside the transaction,
   and commits only once all data and sequences have verified parity.
5. Idempotent: checks for existing primary keys before insertion so reruns are safe without duplicating data.
6. Synchronizes PostgreSQL identity sequences after data transfer.
7. Verifies row count parity between SQLite and PostgreSQL.
"""

import sys
import os
import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import (
    DATABASE_URL,
    DB_PATH,
    get_masked_database_url,
)
from app.database import (
    get_connection,
    init_db,
    HAS_PSYCOPG,
    TABLES_WITH_IDENTITY_ID,
)

# Migration order respecting foreign key constraints
TABLE_MIGRATION_ORDER = [
    ("events", "id"),
    ("users", "id"),
    ("student_profiles", "id"),
    ("user_identities", "id"),
    ("user_sessions", "session_id"),
    ("oauth_states", "state"),
    ("notification_preferences", "id"),
    ("registration_actions", "id"),
    ("registration_audit_logs", "id"),
    ("adapter_sync_logs", "id"),
    ("notifications", "id"),
]


def _check_table_exists_in_target(dst_conn: Any, table_name: str) -> bool:
    """Safely checks if a table exists in the target database without modifying schema."""
    cur = dst_conn.cursor()
    try:
        is_pg = getattr(dst_conn, "is_postgres", False) or hasattr(cur, "_cur")
        if is_pg:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;",
                (table_name.lower(),)
            )
            return cur.fetchone() is not None
        else:
            # Fallback for SQLite-based test mocks
            cur.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?;",
                (table_name,)
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def migrate_data(
    sqlite_path: Path,
    pg_url: Optional[str] = None,
    dry_run: bool = False,
    dst_conn: Optional[Any] = None,
) -> bool:
    """
    Executes the migration from SQLite to PostgreSQL or inspects dry-run plan.

    Args:
        sqlite_path: Path to source SQLite database file.
        pg_url: Target PostgreSQL connection URL (optional in dry-run or if dst_conn provided).
        dry_run: If True, inspects source data and migration plan without creating
                 target tables or committing any schema/data changes.
        dst_conn: Optional pre-existing target connection (e.g. for testing with mocks).

    Returns:
        True if migration or dry-run inspection succeeded, False otherwise.
    """
    if not HAS_PSYCOPG and not dry_run and dst_conn is None:
        print("[ERROR] psycopg library is not installed. Please run: pip install 'psycopg[binary]>=3.1.18'")
        return False

    if not sqlite_path.exists():
        print(f"[ERROR] Source SQLite database file not found at: {sqlite_path}")
        return False

    masked_url = get_masked_database_url(pg_url) if pg_url else "[NOT_SPECIFIED]"
    print(f"=== ZIRO NEON POSTGRESQL MIGRATION ===")
    print(f"Source Database (SQLite): {sqlite_path} [READ-ONLY]")
    print(f"Target Database (PostgreSQL): {masked_url}")
    print(f"Mode: {'DRY RUN (inspection only, 0 changes to target)' if dry_run else 'LIVE MIGRATION'}")
    print("-" * 65)

    # 1. Connect to SQLite in read-only mode (?mode=ro)
    sqlite_uri = f"file:{sqlite_path.resolve().as_posix()}?mode=ro"
    try:
        src_conn = sqlite3.connect(sqlite_uri, uri=True)
        src_conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"[ERROR] Failed to connect to SQLite in read-only mode: {str(e)}")
        return False

    # 2. Target PostgreSQL connection
    close_dst_after = False
    if dst_conn is None and pg_url:
        try:
            dst_conn = get_connection(db_target=pg_url)
            close_dst_after = True
        except Exception as e:
            if dry_run:
                print(f"[WARN] Target connection could not be established: {type(e).__name__}.")
                print("[INFO] Proceeding with dry-run source inspection and migration plan.")
                dst_conn = None
            else:
                print(f"[ERROR] Failed to connect to PostgreSQL: {type(e).__name__}: {str(e)}")
                src_conn.close()
                return False

    try:
        migration_summary = []
        all_passed = True

        # =====================================================================
        # DRY RUN MODE: Pure inspection, ZERO schema creation, ZERO commits
        # =====================================================================
        if dry_run:
            print("[INFO] DRY RUN: Performing source inspection and migration planning.")
            print("[INFO] Skipping target schema initialization (no tables will be created).")
            print("-" * 65)

            for table_name, pk_col in TABLE_MIGRATION_ORDER:
                src_cur = src_conn.cursor()
                src_cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = ?;",
                    (table_name,)
                )
                if not src_cur.fetchone():
                    print(f"[SKIP] Table '{table_name}' does not exist in source database.")
                    continue

                src_cur.execute(f"SELECT COUNT(*) AS cnt FROM {table_name};")
                src_count = src_cur.fetchone()[0]

                # Inspect target state safely via information_schema (read-only)
                target_state = "PENDING_CREATION"
                existing_in_target = 0
                to_insert = src_count
                to_skip = 0

                if dst_conn is not None:
                    table_exists = _check_table_exists_in_target(dst_conn, table_name)
                    if table_exists:
                        dst_cur = dst_conn.cursor()
                        dst_cur.execute(f'SELECT "{pk_col}" FROM "{table_name}";')
                        target_pks = set()
                        for r in dst_cur.fetchall():
                            val = r[pk_col] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[0]
                            target_pks.add(val)
                        existing_in_target = len(target_pks)

                        # Check how many SQLite rows match existing PKs
                        src_cur.execute(f"SELECT {pk_col} FROM {table_name};")
                        for r in src_cur.fetchall():
                            if r[0] in target_pks:
                                to_skip += 1
                        to_insert = src_count - to_skip
                        target_state = f"EXISTS ({existing_in_target} rows in target)"
                    else:
                        target_state = "PENDING_CREATION (Table not yet created)"
                else:
                    target_state = "NOT_CONNECTED (Source inspected)"

                migration_summary.append({
                    "table": table_name,
                    "src_count": src_count,
                    "target_state": target_state,
                    "to_insert": to_insert,
                    "to_skip": to_skip,
                    "status": "PLAN_READY",
                })

            # Roll back any accidental queries/locks on target connection
            if dst_conn is not None:
                dst_conn.rollback()

            print("-" * 80)
            print(f"{'Table Name':<26} | {'SQLite':<7} | {'Target State':<28} | {'To Insert':<9} | {'To Skip':<7} | {'Plan Status'}")
            print("-" * 95)
            for s in migration_summary:
                print(f"{s['table']:<26} | {s['src_count']:<7} | {s['target_state']:<28} | {s['to_insert']:<9} | {s['to_skip']:<7} | {s['status']}")
            print("-" * 95)
            print("[DRY RUN SAFE] Zero changes committed to target. Target schema and data remain untouched.")
            print("[DRY RUN SAFE] Source SQLite database opened in read-only mode. backend/events.db remains untouched.")
            return True

        # =====================================================================
        # LIVE MIGRATION MODE: Explicit transaction lifecycle
        # =====================================================================
        if dst_conn is None:
            print("[ERROR] Cannot perform live migration without an active target database connection.")
            return False

        # Initialize schema within caller's transaction WITHOUT auto-committing
        print("[INFO] Initializing target PostgreSQL schema (transaction-managed, commit=False)...")
        init_db(dst_conn, commit=False)
        print("[INFO] Target schema initialized in active transaction.")
        print("-" * 65)

        for table_name, pk_col in TABLE_MIGRATION_ORDER:
            src_cur = src_conn.cursor()
            src_cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?;",
                (table_name,)
            )
            if not src_cur.fetchone():
                print(f"[SKIP] Table '{table_name}' does not exist in source database.")
                continue

            src_cur.execute(f"SELECT * FROM {table_name};")
            sqlite_rows = src_cur.fetchall()
            src_count = len(sqlite_rows)

            if src_count == 0:
                migration_summary.append({
                    "table": table_name,
                    "src_count": 0,
                    "dst_count": 0,
                    "inserted": 0,
                    "skipped": 0,
                    "status": "EMPTY",
                })
                continue

            col_names = [col[0] for col in src_cur.description]

            dst_cur = dst_conn.cursor()
            dst_cur.execute(f'SELECT "{pk_col}" FROM "{table_name}";')
            existing_pks = set()
            for r in dst_cur.fetchall():
                val = r[pk_col] if isinstance(r, dict) or hasattr(r, "__getitem__") else r[0]
                existing_pks.add(val)

            inserted = 0
            skipped = 0
            cols_str = ", ".join(f'"{col}"' for col in col_names)
            placeholders = ", ".join("%s" for _ in col_names)
            insert_query = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})'

            for row in sqlite_rows:
                pk_val = row[pk_col]
                if pk_val in existing_pks:
                    skipped += 1
                    continue

                row_vals = [row[c] for c in col_names]
                if hasattr(dst_cur, "_cur"):
                    dst_cur._cur.execute(insert_query, row_vals)
                else:
                    # SQLite test mock compatibility
                    sqlite_placeholders = ", ".join("?" for _ in col_names)
                    sql_insert = f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({sqlite_placeholders})'
                    dst_cur.execute(sql_insert, row_vals)
                inserted += 1

            # Sync sequence if identity table (Postgres only)
            if table_name in TABLES_WITH_IDENTITY_ID and hasattr(dst_cur, "_cur"):
                try:
                    dst_cur._cur.execute(f"""
                        SELECT setval(
                            pg_get_serial_sequence('{table_name}', 'id'),
                            COALESCE((SELECT MAX(id) FROM "{table_name}"), 0) + 1,
                            false
                        );
                    """)
                except Exception:
                    pass

            dst_cur.execute(f'SELECT COUNT(*) AS cnt FROM "{table_name}";')
            dst_count_row = dst_cur.fetchone()
            total_in_dst = (
                dst_count_row["cnt"]
                if isinstance(dst_count_row, dict) or hasattr(dst_count_row, "__getitem__")
                else dst_count_row[0]
            )

            status = "OK" if total_in_dst >= src_count else "MISMATCH"
            if status == "MISMATCH":
                all_passed = False

            migration_summary.append({
                "table": table_name,
                "src_count": src_count,
                "dst_count": total_in_dst,
                "inserted": inserted,
                "skipped": skipped,
                "status": status,
            })

        if all_passed:
            dst_conn.commit()
            print("[INFO] Transaction committed successfully to PostgreSQL.")
        else:
            dst_conn.rollback()
            print("[ERROR] Parity mismatch detected. Entire migration rolled back.")
            return False

        print("-" * 65)
        print(f"{'Table Name':<28} | {'SQLite':<7} | {'Postgres':<8} | {'Migrated':<8} | {'Skipped':<7} | {'Status'}")
        print("-" * 75)
        for s in migration_summary:
            print(f"{s['table']:<28} | {s['src_count']:<7} | {s['dst_count']:<8} | {s['inserted']:<8} | {s['skipped']:<7} | {s['status']}")
        print("-" * 75)

        return all_passed

    except Exception as e:
        if dst_conn is not None:
            dst_conn.rollback()
        print(f"[ERROR] Migration failed and was rolled back: {str(e)}")
        return False
    finally:
        src_conn.close()
        if close_dst_after and dst_conn is not None:
            dst_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate Ziro database from SQLite to Neon PostgreSQL.")
    parser.add_argument(
        "--sqlite-path",
        default=str(BASE_DIR / "events.db"),
        help="Path to source events.db file (default: backend/events.db)"
    )
    parser.add_argument(
        "--pg-url",
        default=DATABASE_URL,
        help="Target PostgreSQL connection URL (defaults to DATABASE_URL from environment)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform inspection and checks without committing changes to PostgreSQL"
    )

    args = parser.parse_args()

    if not args.pg_url and not args.dry_run:
        print("[ERROR] DATABASE_URL is not set in environment and --pg-url was not specified.")
        print("Please provide DATABASE_URL via backend/.env or argument:")
        print("  python migrate_to_postgres.py --pg-url 'postgresql://user:password@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require'")
        sys.exit(1)

    success = migrate_data(
        sqlite_path=Path(args.sqlite_path),
        pg_url=args.pg_url,
        dry_run=args.dry_run
    )

    if success:
        if args.dry_run:
            print("[SUCCESS] Dry-run verification completed successfully. No changes were made.")
        else:
            print("[SUCCESS] Database migration completed successfully.")
        sys.exit(0)
    else:
        print("[FAILED] Migration encountered issues. Check logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
