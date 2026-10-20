import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database

@pytest.fixture(scope="session")
def isolated_stage4c_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_stage4c.db")
    
    conn = get_connection(db_path)
    init_db(conn)
    seed_database(conn)
    conn.close()

    yield db_path

    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass

@pytest.fixture(autouse=True)
def setup_isolated_context(isolated_stage4c_db):
    conn = get_connection(isolated_stage4c_db)
    conn.execute("DELETE FROM registration_audit_logs;")
    conn.execute("DELETE FROM registration_actions;")
    conn.execute("DELETE FROM adapter_sync_logs;")
    conn.execute("DELETE FROM student_profiles;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_stage4c_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

def test_cancel_registration_workflow():
    """Verify registration actions can be cancelled with audit log trail."""
    # 1. Create a registration
    create_res = client.post("/api/registrations", json={
        "event_id": 1,
        "student_name": "Aarav Sharma",
        "student_email": "aarav@tech.edu",
        "team_size": 2,
    })
    assert create_res.status_code == 201
    action_id = create_res.json()["id"]

    # 2. Cancel from pending_approval
    cancel_res = client.post(f"/api/registrations/{action_id}/cancel", json={
        "reason": "Schedule conflict with exams",
        "actor": "Aarav Sharma"
    })
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["status"] == "cancelled"
    assert "Cancelled: Schedule conflict with exams" in cancel_data["verification_evidence"]
    assert any(log["to_status"] == "cancelled" for log in cancel_data["audit_logs"])

    # 3. Trying to cancel already cancelled action must fail (terminal state)
    cancel_again = client.post(f"/api/registrations/{action_id}/cancel", json={
        "reason": "Double cancel attempt"
    })
    assert cancel_again.status_code == 400

def test_cancel_approved_registration():
    """Verify an approved registration can be cancelled before submission."""
    create_res = client.post("/api/registrations", json={
        "event_id": 2,
        "student_name": "Rohan Gupta",
        "student_email": "rohan@college.edu",
        "team_size": 1,
    })
    assert create_res.status_code == 201
    action_id = create_res.json()["id"]

    approve_res = client.post(f"/api/registrations/{action_id}/approve", json={
        "approver_name": "Faculty Sponsor Prof. Rao",
        "approval_notes": "Eligible to participate"
    })
    assert approve_res.status_code == 200

    cancel_res = client.post(f"/api/registrations/{action_id}/cancel", json={
        "reason": "Team withdrew",
        "actor": "Prof. Rao"
    })
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

def test_audit_logs_endpoint():
    """Verify GET /api/audit-logs returns recorded audit entries."""
    # Create action to generate logs
    create_res = client.post("/api/registrations", json={
        "event_id": 1,
        "student_name": "Devi Kumar",
        "student_email": "devi@campus.in",
        "team_size": 2,
    })
    action_id = create_res.json()["id"]

    # Query all audit logs
    res = client.get("/api/audit-logs")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert any(log["action_id"] == action_id for log in data["logs"])

    # Query filtered by action_id
    res_filtered = client.get(f"/api/audit-logs?action_id={action_id}")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert filtered_data["total"] >= 1
    assert all(log["action_id"] == action_id for log in filtered_data["logs"])

def test_adapters_status_endpoint():
    """Verify GET /api/adapters/status returns real adapter status and counts."""
    res = client.get("/api/adapters/status")
    assert res.status_code == 200
    data = res.json()
    assert "adapters" in data
    adapter_names = [a["source_name"].lower() for a in data["adapters"]]
    assert "devfolio" in adapter_names
    assert "unstop" in adapter_names
    assert "mlh" in adapter_names
    assert "synthetic" not in adapter_names

    unstop_adapter = next(a for a in data["adapters"] if a["source_name"].lower() == "unstop")
    assert "Restricted" in unstop_adapter["compliance_status"]

def test_student_profile_persistence():
    """Verify GET and PUT /api/profile properly persist profile in backend database."""
    # Initially returns default
    get_res = client.get("/api/profile")
    assert get_res.status_code == 200
    default_data = get_res.json()
    assert default_data["team_size"] == 2

    # Update profile
    put_res = client.put("/api/profile", json={
        "student_name": "Kavya Subramanian",
        "student_email": "kavya@iit.ac.in",
        "skills": ["Python", "PyTorch", "FastAPI"],
        "team_size": 3,
        "region": "India",
        "budget": 50.0
    })
    assert put_res.status_code == 200
    saved = put_res.json()
    assert saved["student_name"] == "Kavya Subramanian"
    assert saved["student_email"] == "kavya@iit.ac.in"
    assert saved["team_size"] == 3
    assert saved["region"] == "India"
    assert saved["budget"] == 50.0
    assert saved["updated_at"] is not None

    # Retrieve again and ensure persistence
    get_res2 = client.get("/api/profile")
    assert get_res2.status_code == 200
    persisted = get_res2.json()
    assert persisted["student_name"] == "Kavya Subramanian"
    assert persisted["student_email"] == "kavya@iit.ac.in"
    assert persisted["skills"] == ["Python", "PyTorch", "FastAPI"]
    assert persisted["team_size"] == 3
