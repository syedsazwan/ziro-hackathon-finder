import datetime
import sqlite3
import threading
from typing import Optional, List, Dict, Any, Tuple

from app.normalization import NormalizedEventRecord, is_deadline_expired
from app.adapters import get_all_adapters, get_adapter
from app.adapters.base import SourceFetchResult

_refresh_lock = threading.Lock()

def canonicalize_url(url: Optional[str]) -> str:
    """Normalize URL for consistent deduplication: strip whitespace and trailing slash."""
    if not url or not isinstance(url, str):
        return ""
    u = url.strip()
    if u.endswith("/") and len(u) > 8:
        u = u[:-1]
    return u

class UpsertResult(int):
    """Integer event ID subclassed with operation status ('inserted' | 'updated')."""
    operation: str

    def __new__(cls, val: int, operation: str = "inserted"):
        obj = super().__new__(cls, val)
        obj.operation = operation
        return obj

def upsert_normalized_event(conn: sqlite3.Connection, event: NormalizedEventRecord) -> UpsertResult:
    """
    Inserts a normalized event or updates an existing record based on
    canonical source URL or (source_name, source_event_id) deduplication key.
    Prevents duplicate listings from repeated source syncs.
    Returns UpsertResult (integer event ID with .operation attribute: 'inserted' or 'updated').
    """
    cursor = conn.cursor()
    existing_id: Optional[int] = None
    existing_deadline: Optional[str] = None
    existing_deadline_status: Optional[str] = None
    existing_deadline_notes: Optional[str] = None

    # 1. Deduplication check by (source_name, source_event_id)
    if event.source_event_id:
        cursor.execute("""
        SELECT id, deadline, deadline_status, deadline_notes FROM events
        WHERE LOWER(source_name) = ? AND source_event_id = ?;
        """, (event.source_name.lower(), event.source_event_id))
        row = cursor.fetchone()
        if row:
            existing_id, existing_deadline, existing_deadline_status, existing_deadline_notes = row

    # 2. Deduplication fallback by canonical source_url
    if existing_id is None and event.source_url:
        canon_url = canonicalize_url(event.source_url)
        cursor.execute("""
        SELECT id, deadline, deadline_status, deadline_notes FROM events
        WHERE source_url = ? OR source_url = ? OR source_url = ?;
        """, (event.source_url, canon_url, canon_url + "/"))
        row = cursor.fetchone()
        if row:
            existing_id, existing_deadline, existing_deadline_status, existing_deadline_notes = row

    tags_str = ", ".join(event.tags) if event.tags else "Hackathon"
    deadline_to_store = event.deadline if event.deadline is not None else ""
    deadline_status_to_store = event.deadline_status
    deadline_notes_to_store = event.deadline_notes

    # Safeguard verified deadlines: do not overwrite a previously verified deadline with an empty/unavailable one
    if existing_id is not None:
        if existing_deadline_status == "verified" and event.deadline_status in ("unavailable", "unverified") and not event.deadline:
            deadline_to_store = existing_deadline or ""
            deadline_status_to_store = existing_deadline_status
            deadline_notes_to_store = existing_deadline_notes

    if existing_id is not None:
        # Update existing record
        cursor.execute("""
        UPDATE events
        SET title = ?,
            description = ?,
            organizer = ?,
            registration_url = ?,
            retrieved_at = ?,
            team_min = ?,
            team_max = ?,
            fee_amount = ?,
            fee_currency = ?,
            fee_status = ?,
            deadline = ?,
            timezone = ?,
            start_date = ?,
            end_date = ?,
            location = ?,
            format = ?,
            eligibility_requirements = ?,
            verification_status = ?,
            evidence_notes = ?,
            is_synthetic = ?,
            data_source_type = ?,
            tags = ?,
            region = ?,
            country = ?,
            deadline_status = ?,
            deadline_notes = ?,
            prize_info = ?
        WHERE id = ?;
        """, (
            event.title,
            event.description,
            event.organizer,
            event.registration_url,
            event.retrieved_at,
            event.team_min,
            event.team_max,
            event.fee_amount,
            event.fee_currency,
            event.fee_status,
            deadline_to_store,
            event.timezone,
            event.start_date,
            event.end_date,
            event.location,
            event.format,
            event.eligibility_requirements,
            event.verification_status,
            event.evidence_notes,
            1 if event.is_synthetic else 0,
            event.data_source_type,
            tags_str,
            event.region,
            event.country,
            deadline_status_to_store,
            deadline_notes_to_store,
            event.prize_info,
            existing_id,
        ))
        return UpsertResult(existing_id, "updated")
    else:
        # Insert new record
        cursor.execute("""
        INSERT INTO events (
            title, description, organizer, source_name, source_event_id,
            source_url, registration_url, retrieved_at, team_min, team_max,
            fee_amount, fee_currency, fee_status, deadline, timezone,
            start_date, end_date, location, format, eligibility_requirements,
            verification_status, evidence_notes, is_synthetic, data_source_type,
            tags, region, country, deadline_status, deadline_notes, prize_info
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        );
        """, (
            event.title,
            event.description,
            event.organizer,
            event.source_name,
            event.source_event_id,
            event.source_url,
            event.registration_url,
            event.retrieved_at,
            event.team_min,
            event.team_max,
            event.fee_amount,
            event.fee_currency,
            event.fee_status,
            deadline_to_store,
            event.timezone,
            event.start_date,
            event.end_date,
            event.location,
            event.format,
            event.eligibility_requirements,
            event.verification_status,
            event.evidence_notes,
            1 if event.is_synthetic else 0,
            event.data_source_type,
            tags_str,
            event.region,
            event.country,
            event.deadline_status,
            event.deadline_notes,
            event.prize_info,
        ))
        return UpsertResult(cursor.lastrowid, "inserted")

def refresh_events_from_sources(
    conn: sqlite3.Connection,
    source_name: Optional[str] = None,
    limit_per_source: int = 15,
    criteria: Optional[Dict[str, Any]] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes a real refresh from permitted public event source adapters driven by student criteria.
    SAFE DESIGN:
    - Thread-safe via _refresh_lock.
    - Queries real public endpoints using criteria (format, status, query, skills).
    - Does not bypass restricted sources (reports clear limitation status).
    - Preserves existing registration actions and audit records.
    - Accurately tracks discovered (new) vs updated events.
    - Updates synced_at only on actual success.
    - Reports status="completed" with sync_status="success" | "partial_success" | "error".
    """
    with _refresh_lock:
        adapters_to_run = []
        if source_name and source_name.lower() not in ("all", "*", ""):
            target = get_adapter(source_name)
            if not target:
                raise ValueError(f"Unknown event source '{source_name}'. Supported sources: devfolio, devpost, mlh, unstop.")
            adapters_to_run = [target]
        else:
            adapters_to_run = get_all_adapters()

        refreshed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sources_summary: List[Dict[str, Any]] = []
        total_fetched = 0
        total_discovered = 0
        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        total_failed = 0
        total_upserted = 0
        success_count = 0
        restricted_count = 0
        error_count = 0

        cursor = conn.cursor()

        for adapter in adapters_to_run:
            # Query prior successful sync timestamp for fallback
            cursor.execute("""
            SELECT synced_at FROM adapter_sync_logs
            WHERE LOWER(source_name) = ? AND status = 'success' AND synced_at IS NOT NULL
            ORDER BY id DESC LIMIT 1;
            """, (adapter.source_name.lower(),))
            prior_sync_row = cursor.fetchone()
            prior_successful_sync = prior_sync_row[0] if prior_sync_row and prior_sync_row[0] else None

            try:
                result = adapter.fetch_events(limit=limit_per_source, client=client, criteria=criteria)
            except Exception as e:
                result = SourceFetchResult(
                    source_name=adapter.source_name,
                    status="error",
                    notes=adapter.get_limitations(),
                    error_message=f"Adapter execution exception: {str(e)}"
                )

            fetched_count = result.events_count
            inserted_count = 0
            updated_count = 0
            skipped_count = 0
            failed_count = 0

            for ev in result.events:
                try:
                    res = upsert_normalized_event(conn, ev)
                    if res.operation == "inserted":
                        inserted_count += 1
                    elif res.operation == "updated":
                        updated_count += 1
                    else:
                        skipped_count += 1
                except Exception:
                    failed_count += 1

            upserted_count = inserted_count + updated_count
            total_fetched += fetched_count
            total_inserted += inserted_count
            total_discovered += inserted_count
            total_updated += updated_count
            total_skipped += skipped_count
            total_failed += failed_count
            total_upserted += upserted_count

            if result.status == "success":
                success_count += 1
                actual_synced_at = refreshed_at
            elif result.status == "restricted":
                restricted_count += 1
                actual_synced_at = prior_successful_sync
            else:
                error_count += 1
                actual_synced_at = prior_successful_sync

            sources_summary.append({
                "source_name": adapter.source_name,
                "status": result.status,
                "events_fetched": fetched_count,
                "events_discovered": inserted_count,
                "events_inserted": inserted_count,
                "events_updated": updated_count,
                "events_skipped": skipped_count,
                "events_failed": failed_count,
                "events_upserted": upserted_count,
                "last_attempted_at": refreshed_at,
                "last_synced_at": actual_synced_at,
                "notes": result.notes,
                "error_message": result.error_message,
            })

            # Record sync history in adapter_sync_logs
            log_synced_at = refreshed_at if result.status == "success" else None
            try:
                cursor.execute("""
                INSERT INTO adapter_sync_logs (
                    source_name, status, events_fetched, events_upserted, notes, error_message, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """, (
                    adapter.source_name,
                    result.status,
                    result.events_count,
                    upserted_count,
                    result.notes,
                    result.error_message,
                    log_synced_at,
                ))
            except Exception:
                pass

        conn.commit()

        # Determine overall sync status:
        # success: all attempted adapters succeeded (HTTP 200, status == "success")
        # partial_success: some succeeded and some were restricted/failed
        # restricted: all attempted adapters were restricted by policy (e.g. Unstop 403)
        # error: zero adapters succeeded and at least one encountered a genuine error
        if success_count > 0 and error_count == 0 and restricted_count == 0:
            overall_status = "success"
        elif success_count > 0:
            overall_status = "partial_success"
        elif restricted_count > 0 and error_count == 0:
            overall_status = "restricted"
        else:
            overall_status = "error"

        return {
            "status": "completed",
            "sync_status": overall_status,
            "overall_status": overall_status,
            "refreshed_at": refreshed_at,
            "total_fetched": total_fetched,
            "total_upserted": total_upserted,
            "total_discovered": total_discovered,
            "total_inserted": total_inserted,
            "total_updated": total_updated,
            "total_skipped": total_skipped,
            "total_failed": total_failed,
            "sources_summary": sources_summary,
        }

def get_adapter_statuses(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Returns live status, access mechanisms, last sync timestamps, and error messages
    for all registered source adapters.
    Accurately reflects real results: last_synced_at is populated only from successful syncs.
    """
    cursor = conn.cursor()
    adapters = get_all_adapters()
    statuses = []

    for adapter in adapters:
        name = adapter.source_name
        # Count non-synthetic events in database for this source
        cursor.execute("SELECT COUNT(*) FROM events WHERE LOWER(source_name) = ? AND is_synthetic = 0;", (name.lower(),))
        count_row = cursor.fetchone()
        events_in_db = count_row[0] if count_row else 0

        # Query latest sync log for current status and error messages
        cursor.execute("""
        SELECT synced_at, status, error_message, notes
        FROM adapter_sync_logs
        WHERE LOWER(source_name) = ?
        ORDER BY id DESC LIMIT 1;
        """, (name.lower(),))
        log_row = cursor.fetchone()

        last_synced_at = None
        last_error = None
        sync_notes = adapter.get_limitations()

        if log_row:
            last_error = log_row["error_message"]
            if log_row["notes"]:
                sync_notes = log_row["notes"]
            if log_row["status"] == "success" and log_row["synced_at"]:
                last_synced_at = log_row["synced_at"]

        # If latest log wasn't a successful sync, query the most recent successful sync timestamp
        if not last_synced_at:
            cursor.execute("""
            SELECT synced_at
            FROM adapter_sync_logs
            WHERE LOWER(source_name) = ? AND status = 'success' AND synced_at IS NOT NULL
            ORDER BY id DESC LIMIT 1;
            """, (name.lower(),))
            succ_row = cursor.fetchone()
            if succ_row and succ_row[0]:
                last_synced_at = succ_row[0]
            else:
                # Fallback to MAX(retrieved_at) in events table for verified real events
                cursor.execute("SELECT MAX(retrieved_at) FROM events WHERE LOWER(source_name) = ? AND is_synthetic = 0;", (name.lower(),))
                max_row = cursor.fetchone()
                if max_row and max_row[0]:
                    last_synced_at = max_row[0]

        # Query latest attempt time from adapter_sync_logs
        cursor.execute("SELECT synced_at, status FROM adapter_sync_logs WHERE LOWER(source_name) = ? ORDER BY id DESC LIMIT 1;", (name.lower(),))
        att_row = cursor.fetchone()
        last_attempted_at = att_row[0] if att_row and att_row[0] else last_synced_at

        portal_url = None
        if name.lower() == "unstop":
            display_name = "Unstop"
            access_mech = adapter.get_limitations()
            portal_url = "https://unstop.com/hackathons"
            if log_row and log_row["status"] == "success":
                compliance = "Active & Compliant"
            elif log_row and log_row["status"] == "restricted":
                compliance = "Restricted (Cloudflare 403)"
            elif log_row and log_row["status"] == "error":
                compliance = "Sync Error (Restricted)"
            else:
                compliance = "Restricted (Cloudflare / Terms Policy)"
        elif name.lower() == "devfolio":
            display_name = "Devfolio"
            access_mech = "Official Public API (api.devfolio.co)"
            compliance = "Active & Compliant"
            portal_url = "https://devfolio.co/hackathons"
        elif name.lower() == "devpost":
            display_name = "Devpost"
            access_mech = "Official Public API (devpost.com/api/hackathons)"
            compliance = "Active & Compliant"
            portal_url = "https://devpost.com/hackathons"
        elif name.lower() == "mlh":
            display_name = "Major League Hacking (MLH)"
            access_mech = "Official Public Schedule (mlh.io/events)"
            compliance = "Active & Compliant"
            portal_url = "https://mlh.io/events"
        else:
            display_name = name
            access_mech = "Public Web Adapter"
            compliance = "Active" if adapter.is_available() else "Restricted"
            portal_url = getattr(adapter, "portal_url", None)

        statuses.append({
            "source_name": name,
            "display_name": display_name,
            "access_mechanism": access_mech,
            "compliance_status": compliance,
            "portal_url": portal_url,
            "last_attempted_at": last_attempted_at,
            "last_synced_at": last_synced_at,
            "events_in_db": events_in_db,
            "last_error": last_error,
            "notes": sync_notes,
        })

    return statuses


