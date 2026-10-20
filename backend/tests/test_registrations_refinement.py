import os
import tempfile
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database
from app.config import DB_PATH

@pytest.fixture(scope="session")
def isolated_refinement_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_refinement.db")
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
def setup_isolated_context(isolated_refinement_db):
    conn = get_connection(isolated_refinement_db)
    conn.execute("DELETE FROM registration_audit_logs;")
    conn.execute("DELETE FROM registration_actions;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_refinement_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

def test_existing_database_records_preserved():
    """Verify existing saved records in backend/events.db remain intact and are not deleted or corrupted."""
    if not os.path.exists(DB_PATH):
        pytest.skip("Main events.db does not exist in standard location")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    events_count = cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert events_count >= 5, "Database events table should have preserved records"

    reg_actions = cur.execute("SELECT * FROM registration_actions").fetchall()
    assert len(reg_actions) >= 3, "Database registration_actions table should have preserved records"

    audit_logs = cur.execute("SELECT * FROM registration_audit_logs").fetchall()
    assert len(audit_logs) >= 5, "Database registration_audit_logs table should have preserved records"
    conn.close()

def test_registration_filtering_by_synthetic_provenance(isolated_refinement_db):
    """Verify include_synthetic query param cleanly separates genuine vs synthetic records."""
    # 1. Insert a synthetic registration (event 1 is synthetic demo)
    res_syn = client.post("/api/registrations", json={
        "event_id": 1,
        "student_name": "Test Synthetic Student",
        "student_email": "syn@fixture.local",
        "team_size": 2,
    })
    assert res_syn.status_code == 201
    assert res_syn.json()["is_synthetic"] is True

    # 2. Insert a real event into the test database (is_synthetic = 0, data_source_type = 'official_api')
    conn = get_connection(isolated_refinement_db)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO events (
        title, description, organizer, source_url, retrieved_at,
        team_min, team_max, fee_amount, fee_currency, fee_status,
        deadline, timezone, data_source_type, is_synthetic, tags, region, format
    ) VALUES (
        'Real Tech Contest 2026', 'Genuine event', 'Tech Council', 'https://tech.org',
        '2026-10-18T00:00:00Z', 1, 4, 0.0, 'USD', 'free',
        '2026-12-01T23:59:00Z', 'UTC', 'official_api', 0, 'Python', 'Global', 'Online'
    );
    """)
    real_event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 3. Create genuine registration on the real event
    res_real = client.post("/api/registrations", json={
        "event_id": real_event_id,
        "student_name": "Priya Patel",
        "student_email": "priya@university.edu",
        "team_size": 2,
    })
    assert res_real.status_code == 201
    assert res_real.json()["is_synthetic"] is False

    # 4. Query include_synthetic=false: only genuine registrations returned
    res_genuine_only = client.get("/api/registrations?include_synthetic=false")
    assert res_genuine_only.status_code == 200
    genuine_actions = res_genuine_only.json()["actions"]
    assert len(genuine_actions) == 1
    assert genuine_actions[0]["student_email"] == "priya@university.edu"
    assert genuine_actions[0]["is_synthetic"] is False

    # 5. Query include_synthetic=true: only synthetic fixtures returned
    res_syn_only = client.get("/api/registrations?include_synthetic=true")
    assert res_syn_only.status_code == 200
    syn_actions = res_syn_only.json()["actions"]
    assert len(syn_actions) == 1
    assert syn_actions[0]["student_email"] == "syn@fixture.local"
    assert syn_actions[0]["is_synthetic"] is True

    # 6. Query without param: defaults to genuine records only (Section 6 Requirement 1)
    res_default = client.get("/api/registrations")
    assert res_default.status_code == 200
    assert len(res_default.json()["actions"]) == 1
    assert res_default.json()["actions"][0]["is_synthetic"] is False
