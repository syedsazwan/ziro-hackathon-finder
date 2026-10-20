import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database
from app.utils import convert_to_ist, calculate_eligibility

@pytest.fixture(scope="session")
def isolated_test_db():
    """
    Creates an isolated temporary SQLite database file for tests
    so existing demo records and audit logs in backend/events.db remain untouched.
    """
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_events.db")
    
    # Initialize schema and seed synthetic fixtures in the isolated database
    conn = get_connection(db_path)
    init_db(conn)
    seed_database(conn)
    conn.close()

    yield db_path

    # Clean up temporary database files after the test session
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass

@pytest.fixture(autouse=True)
def setup_isolated_test_context(isolated_test_db):
    """
    Per-test fixture that overrides FastAPI's get_db dependency to point to the
    isolated temporary SQLite database, and cleans temporary test registration data.
    """
    conn = get_connection(isolated_test_db)
    # Clean only the registration tables in the temporary database for test isolation
    conn.execute("DELETE FROM registration_audit_logs;")
    conn.execute("DELETE FROM registration_actions;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_test_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

# -------------------------------------------------------------
# Stage 1 Tests: Preserved Discovery & Eligibility Functionality
# -------------------------------------------------------------

def test_health_endpoint():
    """Verify GET /health returns 200, healthy status, and connected database."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "timestamp" in data

def test_event_listing():
    """Verify GET /api/events with include_synthetic=true lists seeded synthetic demo events with proper fields."""
    # 1. Default query without include_synthetic must exclude synthetic fixtures
    res_default = client.get("/api/events")
    assert res_default.status_code == 200
    assert res_default.json()["total"] == 0
    assert all(e["is_synthetic"] is False for e in res_default.json()["events"])

    # 2. Query with include_synthetic=true retrieves isolated synthetic test fixtures
    response = client.get("/api/events?include_synthetic=true")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert data["total"] > 0
    
    for event in data["events"]:
        assert event["data_source_type"] == "synthetic_demo_fixture"
        assert "[SYNTHETIC DEMO]" in event["title"]
        assert "source_url" in event
        assert "retrieved_at" in event
        assert "deadline_ist" in event
        assert "deadline_ist_formatted" in event
        assert "eligibility" in event

def test_team_size_eligibility():
    """Verify team size eligibility rules: solo student vs team events."""
    res_solo = client.get("/api/events?team_size=1&include_synthetic=true")
    assert res_solo.status_code == 200
    events_solo = {e["title"]: e for e in res_solo.json()["events"]}

    team_event = events_solo["[SYNTHETIC DEMO] Global AI Systems Hackathon 2026"]
    assert team_event["eligibility"]["status"] == "Not eligible"
    assert any("below the minimum required (2)" in r for r in team_event["eligibility"]["reasons"])

    res_team3 = client.get("/api/events?team_size=3&include_synthetic=true")
    assert res_team3.status_code == 200
    events_team3 = {e["title"]: e for e in res_team3.json()["events"]}
    team_event_eligible = events_team3["[SYNTHETIC DEMO] Global AI Systems Hackathon 2026"]
    assert team_event_eligible["eligibility"]["status"] == "Eligible"

    res_too_large = calculate_eligibility(team_min=2, team_max=4, fee_status="free", fee_amount=0, team_size=5)
    assert res_too_large["status"] == "Not eligible"
    assert any("exceeds the maximum allowed (4)" in r for r in res_too_large["reasons"])

def test_unknown_fees_require_verification():
    """Verify unknown fee status results in 'Needs verification' eligibility label."""
    res = client.get("/api/events?team_size=1&include_synthetic=true")
    assert res.status_code == 200
    events = {e["title"]: e for e in res.json()["events"]}
    
    unknown_fee_event = events["[SYNTHETIC DEMO] Collegiate CodeSprint Cup"]
    assert unknown_fee_event["fee_status"] == "unknown"
    assert unknown_fee_event["eligibility"]["status"] == "Needs verification"
    assert any("requires verification" in r for r in unknown_fee_event["eligibility"]["reasons"])

def test_pst_to_ist_conversion():
    """Verify timezone-aware PST to IST conversion yields the exact expected result."""
    pst_iso = "2026-11-15T23:59:00-08:00"
    iso_result, formatted_result = convert_to_ist(pst_iso, "America/Los_Angeles")
    assert iso_result == "2026-11-16T13:29:00+05:30"
    assert formatted_result == "16 Nov 2026, 01:29 PM IST"

# -------------------------------------------------------------
# Stage 2.5 Safety Tests: Registration Workflow & Invariants
# -------------------------------------------------------------

def test_new_registration_starts_as_pending_approval():
    """Test 2.a: A new registration action always starts in 'pending_approval' state."""
    res = client.post("/api/registrations", json={
        "event_id": 1,
        "student_email": "turing.alan@cambridge.edu",
        "student_name": "Alan Turing",
        "team_size": 2,
        "notes": "Cryptographic systems track interest"
    })
    assert res.status_code == 201
    action = res.json()

    assert action["status"] == "pending_approval"
    assert action["approved_at"] is None
    assert action["approved_by"] is None
    assert action["submitted_at"] is None
    assert action["verification_evidence"] is None
    assert action["is_simulation"] is True

    # Audit log verification
    assert len(action["audit_logs"]) == 1
    log = action["audit_logs"][0]
    assert log["event_type"] == "created"
    assert log["from_status"] is None
    assert log["to_status"] == "pending_approval"
    assert log["actor"] == "Alan Turing"

def test_submission_before_approval_rejected_and_status_unchanged():
    """Test 2.b: Submission before explicit approval is rejected (403) and status remains unchanged."""
    res_create = client.post("/api/registrations", json={
        "event_id": 1,
        "student_email": "lovelace.ada@oxford.edu",
        "student_name": "Ada Lovelace",
        "team_size": 2,
        "notes": "Analytical engine algorithms"
    })
    action_id = res_create.json()["id"]

    # Attempt submission while in pending_approval state
    res_submit = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })
    assert res_submit.status_code == 403
    assert "requires explicit human approval" in res_submit.json()["detail"]

    # Verify status is unchanged
    res_get = client.get(f"/api/registrations/{action_id}")
    assert res_get.status_code == 200
    action = res_get.json()
    assert action["status"] == "pending_approval"
    assert action["submitted_at"] is None
    assert len(action["audit_logs"]) == 1  # No duplicate or unauthorized transition log recorded

def test_approval_followed_by_simulated_submission_results_in_submitted_never_confirmed():
    """Test 2.c: Approval followed by simulated submission results in 'submitted', never 'confirmed'."""
    res_create = client.post("/api/registrations", json={
        "event_id": 1,
        "student_email": "vonneumann.john@princeton.edu",
        "student_name": "John von Neumann",
        "team_size": 3,
        "notes": "Game theory algorithms"
    })
    action_id = res_create.json()["id"]

    # Explicit human approval
    res_approve = client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Prof. Eleanor Vance (Faculty Sponsor)",
        "approval_notes": "Prerequisites and team roster verified"
    })
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] == "approved"
    assert res_approve.json()["approved_by"] == "Prof. Eleanor Vance (Faculty Sponsor)"

    # Attempt to fraudulently request 'confirmed' directly on submission -> Blocked with 400
    res_illegal_submit = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "confirmed"
    })
    assert res_illegal_submit.status_code == 400
    assert "Security rule violation" in res_illegal_submit.json()["detail"]

    # Valid simulated submission -> results in 'submitted'
    res_valid_submit = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })
    assert res_valid_submit.status_code == 200
    action = res_valid_submit.json()
    assert action["status"] == "submitted"
    assert action["status"] != "confirmed"
    assert action["is_simulation"] is True
    assert "No external registration submitted" in action["simulation_notice"]

def test_verification_before_submission_is_rejected():
    """Test 2.d: Manual verification attempted before submission is strictly rejected."""
    # Sub-case 1: Attempt verification on pending_approval action
    res_pending = client.post("/api/registrations", json={
        "event_id": 2,
        "student_email": "hopper.grace@navy.mil",
        "student_name": "Grace Hopper",
        "team_size": 1
    })
    pending_id = res_pending.json()["id"]

    res_verify_early = client.post(f"/api/registrations/{pending_id}/verify", json={
        "verified_by": "Compliance Officer Evelyn Reed",
        "verification_status": "confirmed",
        "evidence_notes": "Official university transcript and eligibility verified on roster REF-2026-104."
    })
    assert res_verify_early.status_code == 400
    assert "Cannot verify action" in res_verify_early.json()["detail"]

    # Sub-case 2: Attempt verification on approved action (not yet submitted)
    client.post(f"/api/registrations/{pending_id}/approve", json={
        "approver_name": "Department Chair Dr. Miller",
        "approval_notes": "Approved for collegiate tournament entry"
    })

    res_verify_approved = client.post(f"/api/registrations/{pending_id}/verify", json={
        "verified_by": "Compliance Officer Evelyn Reed",
        "verification_status": "confirmed",
        "evidence_notes": "Official university transcript and eligibility verified on roster REF-2026-104."
    })
    assert res_verify_approved.status_code == 400
    assert "Cannot verify action" in res_verify_approved.json()["detail"]

def test_manual_verification_after_submission_records_status_and_evidence_in_audit_log():
    """Test 2.e: Manual verification after submission records chosen status and evidence in audit log."""
    res_create = client.post("/api/registrations", json={
        "event_id": 3,
        "student_email": "shannon.claude@mit.edu",
        "student_name": "Claude Shannon",
        "team_size": 2,
        "notes": "Information theory track"
    })
    action_id = res_create.json()["id"]

    # Human approval
    client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Academic Advisor Sarah Connor",
        "approval_notes": "Student academic standing verified"
    })

    # Simulated submission
    client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })

    # Manual verification with meaningful factual evidence notes
    res_verify = client.post(f"/api/registrations/{action_id}/verify", json={
        "verified_by": "Regional Director Marcus Sterling",
        "verification_status": "confirmed",
        "evidence_notes": "Cross-referenced contest portal fixture badge reference #REG-IND-8841."
    })
    assert res_verify.status_code == 200
    action = res_verify.json()
    assert action["status"] == "confirmed"
    assert "Marcus Sterling" in action["verification_evidence"]

    # Audit log check
    audit_logs = action["audit_logs"]
    assert len(audit_logs) == 4
    verify_log = audit_logs[3]
    assert verify_log["event_type"] == "verification_recorded"
    assert verify_log["from_status"] == "submitted"
    assert verify_log["to_status"] == "confirmed"
    assert verify_log["actor"] == "Regional Director Marcus Sterling"
    assert "REG-IND-8841" in verify_log["details"]

def test_repeated_approval_and_submission_requests_rejected_safely():
    """Test 2.f: Repeated approvals or submissions are rejected safely without duplicate state transitions."""
    res_create = client.post("/api/registrations", json={
        "event_id": 1,
        "student_email": "knuth.donald@stanford.edu",
        "student_name": "Donald Knuth",
        "team_size": 2
    })
    action_id = res_create.json()["id"]

    # First approval succeeds
    res_app1 = client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Dean Robert Tarjan",
        "approval_notes": "Algorithms research group entry approved"
    })
    assert res_app1.status_code == 200
    assert len(res_app1.json()["audit_logs"]) == 2

    # Second approval attempt on already approved action -> Must be rejected (400)
    res_app2 = client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Dean Robert Tarjan",
        "approval_notes": "Duplicate second approval attempt"
    })
    assert res_app2.status_code == 400
    assert "Only 'pending_approval' actions can be approved" in res_app2.json()["detail"]

    # Verify audit log count did not increase from rejected attempt
    res_check1 = client.get(f"/api/registrations/{action_id}")
    assert len(res_check1.json()["audit_logs"]) == 2

    # First simulated submission succeeds
    res_sub1 = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })
    assert res_sub1.status_code == 200
    assert res_sub1.json()["status"] == "submitted"
    assert len(res_sub1.json()["audit_logs"]) == 3

    # Second simulated submission attempt on already submitted action -> Must be rejected (400)
    res_sub2 = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })
    assert res_sub2.status_code == 400
    assert "Must be in 'approved' status" in res_sub2.json()["detail"]

    # Verify audit log count remained 3
    res_check2 = client.get(f"/api/registrations/{action_id}")
    assert len(res_check2.json()["audit_logs"]) == 3

def test_duplicate_registration_for_same_event_and_student_safely_handled():
    """Test 2.g: Duplicate registration attempts for same event and student email return 409 Conflict."""
    email = "dijkstra.edsger@austin.utexas.edu"
    payload = {
        "event_id": 2,
        "student_email": email,
        "student_name": "Edsger Dijkstra",
        "team_size": 1
    }

    # Initial request
    res1 = client.post("/api/registrations", json=payload)
    assert res1.status_code == 201
    first_action_id = res1.json()["id"]

    # Identical email duplicate attempt
    res2 = client.post("/api/registrations", json=payload)
    assert res2.status_code == 409
    assert res2.json()["detail"]["existing_action_id"] == first_action_id
    assert res2.json()["detail"]["status"] == "pending_approval"

    # Mixed-case email duplicate attempt
    res3 = client.post("/api/registrations", json={
        "event_id": 2,
        "student_email": "Dijkstra.Edsger@Austin.UTexas.Edu",
        "student_name": "Edsger W. Dijkstra",
        "team_size": 1
    })
    assert res3.status_code == 409
    assert res3.json()["detail"]["existing_action_id"] == first_action_id

def test_failed_simulated_submission_does_not_produce_confirmed_registration():
    """Test 2.h: A failed simulated submission produces 'failed' status and cannot be marked confirmed."""
    res_create = client.post("/api/registrations", json={
        "event_id": 4,
        "student_email": "lamport.leslie@microsoft.com",
        "student_name": "Leslie Lamport",
        "team_size": 3
    })
    action_id = res_create.json()["id"]

    client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Faculty Supervisor Dr. Milner",
        "approval_notes": "Distributed consensus research submission"
    })

    # Simulate submission failure (e.g. gateway timeout)
    res_failed = client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "failed",
        "failure_reason": "Simulated upstream gateway timeout after 3 exponential backoff retries."
    })
    assert res_failed.status_code == 200
    action = res_failed.json()
    assert action["status"] == "failed"
    assert action["status"] != "confirmed"
    assert "Simulated submission failure" in action["verification_evidence"]

    # Attempting to verify a failed action must be rejected (cannot confirm a failed submission)
    res_verify_failed = client.post(f"/api/registrations/{action_id}/verify", json={
        "verified_by": "Senior Auditor Henderson",
        "verification_status": "confirmed",
        "evidence_notes": "Attempting to confirm a failed submission without re-submission."
    })
    assert res_verify_failed.status_code == 400
    assert "Cannot verify action" in res_verify_failed.json()["detail"]

    # Status remains 'failed'
    res_final = client.get(f"/api/registrations/{action_id}")
    assert res_final.json()["status"] == "failed"

def test_placeholder_values_rejected_by_verification_endpoint():
    """Verify that generic placeholder values like 'string' or 'placeholder' are rejected with 422."""
    res_create = client.post("/api/registrations", json={
        "event_id": 5,
        "student_email": "karp.richard@berkeley.edu",
        "student_name": "Richard Karp",
        "team_size": 2
    })
    action_id = res_create.json()["id"]

    # Reject placeholder in approver name
    res_bad_approve = client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "string",
        "approval_notes": "Valid note"
    })
    assert res_bad_approve.status_code == 422

    # Legitimate approval
    client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Academic Dean Barbara Liskov",
        "approval_notes": "Computational complexity project verified"
    })

    # Legitimate submission
    client.post(f"/api/registrations/{action_id}/submit", json={
        "simulate_outcome": "submitted"
    })

    # Reject placeholder in verifier name
    res_bad_verifier = client.post(f"/api/registrations/{action_id}/verify", json={
        "verified_by": "string",
        "verification_status": "confirmed",
        "evidence_notes": "Official university badge verified"
    })
    assert res_bad_verifier.status_code == 422

    # Reject placeholder in evidence notes
    res_bad_evidence = client.post(f"/api/registrations/{action_id}/verify", json={
        "verified_by": "Registrar Officer Collins",
        "verification_status": "confirmed",
        "evidence_notes": "string"
    })
    assert res_bad_evidence.status_code == 422

def test_direct_eligibility_check_endpoint():
    """Verify POST /api/eligibility/check evaluates constraints directly with safety guarantees."""
    # 1. Eligible case
    res1 = client.post("/api/eligibility/check", json={
        "team_min": 2,
        "team_max": 4,
        "team_size": 3,
        "fee_status": "free",
        "skills": ["Python", "FastAPI"],
        "event_tags": ["Python", "Backend"]
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "Eligible"
    assert any("Team size 3 fits" in r for r in data1["reasons"])
    assert any("Matched skills" in r for r in data1["reasons"])

    # 2. Team size out of bounds -> Not eligible
    res2 = client.post("/api/eligibility/check", json={
        "team_min": 2,
        "team_max": 4,
        "team_size": 5,
        "fee_status": "free"
    })
    assert res2.status_code == 200
    assert res2.json()["status"] == "Not eligible"

    # 3. Unknown fee status -> Needs verification (never claimed eligible)
    res3 = client.post("/api/eligibility/check", json={
        "team_min": 1,
        "team_max": 4,
        "team_size": 2,
        "fee_status": "unknown"
    })
    assert res3.status_code == 200
    assert res3.json()["status"] == "Needs verification"
    assert any("requires verification" in r for r in res3.json()["reasons"])

    # 4. Check against existing seeded event ID
    res4 = client.post("/api/eligibility/check", json={
        "event_id": 1,
        "team_size": 3,
        "budget": 50.0
    })
    assert res4.status_code == 200
    assert res4.json()["status"] in ("Eligible", "Not eligible", "Needs verification")

    # 5. Non-existent event ID -> 404
    res5 = client.post("/api/eligibility/check", json={
        "event_id": 999999,
        "team_size": 2
    })
    assert res5.status_code == 404
