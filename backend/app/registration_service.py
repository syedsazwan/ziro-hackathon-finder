import json
import uuid
import datetime
import sqlite3
from typing import Optional, List, Dict, Any

from app.schemas import (
    RegistrationActionCreate,
    RegistrationApproveRequest,
    RegistrationSubmitRequest,
    RegistrationVerifyRequest,
)

class EventNotFoundError(Exception):
    """Raised when the specified event ID does not exist."""
    pass

class DuplicateActionError(Exception):
    """Raised when a registration action already exists for the event and student."""
    def __init__(self, action_id: str, status: str, event_id: int, student_email: str):
        self.action_id = action_id
        self.status = status
        self.event_id = event_id
        self.student_email = student_email
        super().__init__(
            f"Registration action already exists for student '{student_email}' on event {event_id}. "
            f"Existing action ID: {action_id}, status: {status}."
        )

class ActionNotFoundError(Exception):
    """Raised when the specified action ID does not exist."""
    pass

class ApprovalRequiredError(Exception):
    """Raised when an unapproved action attempts submission."""
    pass

class InvalidStateTransitionError(Exception):
    """Raised when attempting an invalid status transition."""
    pass

def _get_utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def record_audit_log(
    conn: sqlite3.Connection,
    action_id: str,
    from_status: Optional[str],
    to_status: str,
    actor: str,
    event_type: str,
    details: Dict[str, Any],
) -> int:
    """Appends an immutable record to the audit trail."""
    cursor = conn.cursor()
    created_at = _get_utc_now()
    cursor.execute("""
    INSERT INTO registration_audit_logs (
        action_id, from_status, to_status, actor, event_type, details, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (
        action_id,
        from_status,
        to_status,
        actor,
        event_type,
        json.dumps(details),
        created_at,
    ))
    return cursor.lastrowid

def create_registration_action(
    conn: sqlite3.Connection,
    data: RegistrationActionCreate,
) -> Dict[str, Any]:
    """
    Creates a new registration action in 'pending_approval' state.
    Enforces idempotency and prevents duplicate entries per (event_id, student_email).
    """
    cursor = conn.cursor()

    # 1. Verify event exists
    cursor.execute("SELECT id, title FROM events WHERE id = ?", (data.event_id,))
    event_row = cursor.fetchone()
    if not event_row:
        raise EventNotFoundError(f"Event with ID {data.event_id} does not exist.")

    # 2. Check for duplicate action
    cursor.execute("""
    SELECT id, status, event_id, student_email
    FROM registration_actions
    WHERE event_id = ? AND student_email = ?
    """, (data.event_id, data.student_email.strip().lower()))
    existing = cursor.fetchone()
    if existing:
        raise DuplicateActionError(
            action_id=existing["id"],
            status=existing["status"],
            event_id=existing["event_id"],
            student_email=existing["student_email"],
        )

    action_id = f"act_{uuid.uuid4().hex[:12]}"
    created_at = _get_utc_now()
    initial_status = "pending_approval"
    normalized_email = data.student_email.strip().lower()

    try:
        cursor.execute("""
        INSERT INTO registration_actions (
            id, event_id, student_email, student_name, team_size,
            status, created_at, is_simulation, simulation_notice
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?);
        """, (
            action_id,
            data.event_id,
            normalized_email,
            data.student_name.strip(),
            data.team_size,
            initial_status,
            created_at,
            "Simulated workflow: No external registration submitted. Demo record only.",
        ))
    except sqlite3.IntegrityError:
        # Extra safety in case of concurrent insert
        cursor.execute("""
        SELECT id, status, event_id, student_email
        FROM registration_actions
        WHERE event_id = ? AND student_email = ?
        """, (data.event_id, normalized_email))
        dup = cursor.fetchone()
        if dup:
            raise DuplicateActionError(
                action_id=dup["id"],
                status=dup["status"],
                event_id=dup["event_id"],
                student_email=dup["student_email"],
            )
        raise

    # 3. Append to audit log
    record_audit_log(
        conn=conn,
        action_id=action_id,
        from_status=None,
        to_status=initial_status,
        actor=data.student_name.strip(),
        event_type="created",
        details={
            "event_id": data.event_id,
            "event_title": event_row["title"],
            "student_email": normalized_email,
            "team_size": data.team_size,
            "notes": data.notes,
            "workflow_stage": "Stage 2 - Demo Registration Workflow",
        },
    )

    conn.commit()
    return get_registration_action(conn, action_id)

def approve_registration_action(
    conn: sqlite3.Connection,
    action_id: str,
    data: RegistrationApproveRequest,
) -> Dict[str, Any]:
    """
    Applies explicit human approval to a pending registration action.
    Transitions status: 'pending_approval' -> 'approved'.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registration_actions WHERE id = ?", (action_id,))
    action = cursor.fetchone()
    if not action:
        raise ActionNotFoundError(f"Registration action '{action_id}' not found.")

    current_status = action["status"]
    if current_status != "pending_approval":
        raise InvalidStateTransitionError(
            f"Action '{action_id}' is in status '{current_status}'. Only 'pending_approval' actions can be approved."
        )

    approved_at = _get_utc_now()
    new_status = "approved"

    cursor.execute("""
    UPDATE registration_actions
    SET status = ?, approved_at = ?, approved_by = ?, approval_notes = ?
    WHERE id = ?;
    """, (
        new_status,
        approved_at,
        data.approver_name.strip(),
        data.approval_notes.strip() if data.approval_notes else None,
        action_id,
    ))

    # Append to audit log
    record_audit_log(
        conn=conn,
        action_id=action_id,
        from_status=current_status,
        to_status=new_status,
        actor=data.approver_name.strip(),
        event_type="approved",
        details={
            "approver_name": data.approver_name.strip(),
            "approval_notes": data.approval_notes,
            "approved_at": approved_at,
            "human_approval_confirmed": True,
        },
    )

    conn.commit()
    return get_registration_action(conn, action_id)

def simulate_submission(
    conn: sqlite3.Connection,
    action_id: str,
    data: RegistrationSubmitRequest,
) -> Dict[str, Any]:
    """
    Executes a simulated registration submission.
    REQUIREMENT: Requires explicit human approval first.
    CRITICAL RULE: Unverified registrations are NEVER marked 'confirmed'.
    Allowed simulated outcomes: 'submitted', 'needs_manual_verification', 'failed'.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registration_actions WHERE id = ?", (action_id,))
    action = cursor.fetchone()
    if not action:
        raise ActionNotFoundError(f"Registration action '{action_id}' not found.")

    current_status = action["status"]

    # Explicit check: If pending_approval, submission is strictly blocked
    if current_status == "pending_approval":
        raise ApprovalRequiredError(
            f"Action '{action_id}' requires explicit human approval before submission can be initiated. "
            f"Current status: '{current_status}'."
        )

    if current_status != "approved":
        raise InvalidStateTransitionError(
            f"Cannot submit action '{action_id}' from status '{current_status}'. Must be in 'approved' status."
        )

    target_outcome = data.simulate_outcome or "submitted"
    if target_outcome == "confirmed":
        raise ValueError(
            "Security rule violation: A registration cannot be directly marked 'confirmed' upon submission. "
            "It must undergo post-submission manual verification."
        )

    if target_outcome not in ("submitted", "needs_manual_verification", "failed"):
        raise ValueError(f"Invalid simulated submission outcome: '{target_outcome}'.")

    submitted_at = _get_utc_now()
    
    if target_outcome == "failed":
        evidence_note = f"Simulated submission failure: {data.failure_reason or 'Mock upstream network timeout'}"
    elif target_outcome == "needs_manual_verification":
        evidence_note = "Simulated submission queued; upstream portal requires manual verification of student credentials."
    else:
        evidence_note = "Simulated submission received by mock portal; pending human verification of confirmation."

    cursor.execute("""
    UPDATE registration_actions
    SET status = ?, submitted_at = ?, verification_evidence = ?
    WHERE id = ?;
    """, (
        target_outcome,
        submitted_at,
        evidence_note,
        action_id,
    ))

    # Append to audit log
    record_audit_log(
        conn=conn,
        action_id=action_id,
        from_status=current_status,
        to_status=target_outcome,
        actor="simulation_engine",
        event_type="submission_attempted",
        details={
            "simulated_outcome": target_outcome,
            "failure_reason": data.failure_reason,
            "evidence_note": evidence_note,
            "is_simulation": True,
            "submitted_at": submitted_at,
        },
    )

    conn.commit()
    return get_registration_action(conn, action_id)

def verify_registration(
    conn: sqlite3.Connection,
    action_id: str,
    data: RegistrationVerifyRequest,
) -> Dict[str, Any]:
    """
    Records an explicit manual verification outcome.
    Can only be performed after a submission has been attempted (status in 'submitted', 'needs_manual_verification').
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registration_actions WHERE id = ?", (action_id,))
    action = cursor.fetchone()
    if not action:
        raise ActionNotFoundError(f"Registration action '{action_id}' not found.")

    current_status = action["status"]
    if current_status not in ("submitted", "needs_manual_verification"):
        raise InvalidStateTransitionError(
            f"Cannot verify action '{action_id}' in status '{current_status}'. "
            f"Action must be in 'submitted' or 'needs_manual_verification'."
        )

    target_status = data.verification_status
    evidence = f"Verified by {data.verified_by}: {data.evidence_notes.strip()}"

    cursor.execute("""
    UPDATE registration_actions
    SET status = ?, verification_evidence = ?
    WHERE id = ?;
    """, (
        target_status,
        evidence,
        action_id,
    ))

    record_audit_log(
        conn=conn,
        action_id=action_id,
        from_status=current_status,
        to_status=target_status,
        actor=data.verified_by.strip(),
        event_type="verification_recorded",
        details={
            "verified_by": data.verified_by.strip(),
            "target_status": target_status,
            "evidence_notes": data.evidence_notes.strip(),
            "verified_at": _get_utc_now(),
        },
    )

    conn.commit()
    return get_registration_action(conn, action_id)

def get_registration_action(
    conn: sqlite3.Connection,
    action_id: str,
) -> Optional[Dict[str, Any]]:
    """Retrieves a registration action and its associated append-only audit trail."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT r.*, e.is_synthetic AS event_is_synthetic, e.data_source_type
    FROM registration_actions r
    LEFT JOIN events e ON r.event_id = e.id
    WHERE r.id = ?;
    """, (action_id,))
    row = cursor.fetchone()
    if not row:
        return None

    # Retrieve audit trail
    cursor.execute("""
    SELECT id, action_id, from_status, to_status, actor, event_type, details, created_at
    FROM registration_audit_logs
    WHERE action_id = ?
    ORDER BY id ASC;
    """, (action_id,))
    audit_rows = cursor.fetchall()

    action_dict = dict(row)
    action_dict["is_simulation"] = bool(action_dict["is_simulation"])
    action_dict["is_synthetic"] = bool(
        action_dict.get("event_is_synthetic", 0) or action_dict.get("data_source_type") == "synthetic_demo_fixture"
    )
    action_dict["audit_logs"] = [dict(a) for a in audit_rows]
    return action_dict

def list_registration_actions(
    conn: sqlite3.Connection,
    event_id: Optional[int] = None,
    student_email: Optional[str] = None,
    status: Optional[str] = None,
    include_synthetic: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Lists registration actions matching criteria."""
    cursor = conn.cursor()
    query = """
    SELECT r.*, e.is_synthetic AS event_is_synthetic, e.data_source_type
    FROM registration_actions r
    LEFT JOIN events e ON r.event_id = e.id
    WHERE 1=1
    """
    params = []

    if event_id is not None:
        query += " AND r.event_id = ?"
        params.append(event_id)

    if student_email:
        query += " AND LOWER(r.student_email) = ?"
        params.append(student_email.strip().lower())

    if status:
        query += " AND r.status = ?"
        params.append(status.strip())

    if include_synthetic is False:
        query += " AND (e.is_synthetic = 0 OR e.is_synthetic IS NULL) AND (e.data_source_type != 'synthetic_demo_fixture' OR e.data_source_type IS NULL)"
    elif include_synthetic is True:
        query += " AND (e.is_synthetic = 1 OR e.data_source_type = 'synthetic_demo_fixture')"

    query += " ORDER BY r.created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    results = []
    for r in rows:
        d = dict(r)
        d["is_simulation"] = bool(d["is_simulation"])
        d["is_synthetic"] = bool(
            d.get("event_is_synthetic", 0) or d.get("data_source_type") == "synthetic_demo_fixture"
        )
        results.append(d)
    return results

def cancel_registration_action(
    conn: sqlite3.Connection,
    action_id: str,
    reason: Optional[str] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cancels a registration action.
    Allowed from 'pending_approval', 'approved', or 'needs_manual_verification'.
    Terminal states ('confirmed', 'failed', 'cancelled') cannot be cancelled.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registration_actions WHERE id = ?", (action_id,))
    action = cursor.fetchone()
    if not action:
        raise ActionNotFoundError(f"Registration action '{action_id}' not found.")

    current_status = action["status"]
    if current_status in ("confirmed", "failed", "cancelled"):
        raise InvalidStateTransitionError(
            f"Cannot cancel action '{action_id}' in status '{current_status}'. "
            f"Action is already in a terminal state."
        )

    new_status = "cancelled"
    cancel_reason = reason.strip() if reason else "Cancelled by student"
    actor_name = actor.strip() if actor else action["student_name"]

    cursor.execute("""
    UPDATE registration_actions
    SET status = ?, verification_evidence = ?
    WHERE id = ?;
    """, (
        new_status,
        f"Cancelled: {cancel_reason}",
        action_id,
    ))

    record_audit_log(
        conn=conn,
        action_id=action_id,
        from_status=current_status,
        to_status=new_status,
        actor=actor_name,
        event_type="cancelled",
        details={
            "reason": cancel_reason,
            "cancelled_at": _get_utc_now(),
        },
    )

    conn.commit()
    return get_registration_action(conn, action_id)

def get_recent_audit_logs(
    conn: sqlite3.Connection,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Retrieves recent audit logs across all registration actions."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, action_id, from_status, to_status, actor, event_type, details, created_at
    FROM registration_audit_logs
    ORDER BY id DESC
    LIMIT ?;
    """, (min(limit, 100),))
    rows = cursor.fetchall()
    return [dict(r) for r in rows]

