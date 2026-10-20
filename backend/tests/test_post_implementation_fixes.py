import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database
from app.normalization import normalize_raw_event, normalize_country_name
from app.event_service import upsert_normalized_event

@pytest.fixture(scope="session")
def isolated_fix_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_fixes.db")
    
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
def setup_isolated_context(isolated_fix_db):
    conn = get_connection(isolated_fix_db)
    conn.execute("DELETE FROM registration_audit_logs;")
    conn.execute("DELETE FROM registration_actions;")
    conn.execute("DELETE FROM adapter_sync_logs;")
    conn.execute("DELETE FROM student_profiles;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_fix_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

# -----------------------------------------------------------------
# 1. My Profile — Technical Expertise Regression Tests
# -----------------------------------------------------------------

def test_new_profile_zero_skills_and_existing_profile_retention():
    """
    Verify:
    1. A newly created profile begins with zero selected skills.
    2. An existing profile retains explicitly saved skills across reload.
    3. Saving an empty skills list persists [] without silently restoring defaults.
    """
    # 1. A new profile starts with 0 selected skills
    res_new = client.get("/api/profile")
    assert res_new.status_code == 200
    new_data = res_new.json()
    assert new_data["skills"] == []
    assert new_data["student_name"] is None
    assert new_data["student_email"] is None

    # 2. Existing user saves specific skills
    res_save = client.put("/api/profile", json={
        "student_name": "Mira Patel",
        "student_email": "mira@university.edu",
        "skills": ["Rust", "Distributed Systems", "TypeScript"],
        "team_size": 3,
        "region": "India",
    })
    assert res_save.status_code == 200
    assert res_save.json()["skills"] == ["Rust", "Distributed Systems", "TypeScript"]

    # 3. Existing profile retains saved skills on reload
    res_reload = client.get("/api/profile")
    assert res_reload.status_code == 200
    reload_data = res_reload.json()
    assert reload_data["student_name"] == "Mira Patel"
    assert reload_data["skills"] == ["Rust", "Distributed Systems", "TypeScript"]

    # 4. Saving empty skills does not restore defaults
    res_empty_save = client.put("/api/profile", json={
        "student_name": "Mira Patel",
        "student_email": "mira@university.edu",
        "skills": [],
        "team_size": 2,
    })
    assert res_empty_save.status_code == 200
    assert res_empty_save.json()["skills"] == []

    res_reload_empty = client.get("/api/profile")
    assert res_reload_empty.status_code == 200
    assert res_reload_empty.json()["skills"] == []

# -----------------------------------------------------------------
# 2. My Criteria — Technical Skills for Event Matching Tests
# -----------------------------------------------------------------

def test_criteria_matching_behavior_and_empty_skills_persistence(isolated_fix_db):
    """
    Verify:
    1. Matching evaluation with 0 selected skills evaluates events without crashing or injecting defaults.
    2. Matching evaluation with selected skills reflects matched skills.
    3. Events evaluation behaves correctly when criteria skills are empty.
    """
    conn = get_connection(isolated_fix_db)
    raw_event = {
        "title": "Autonomous Robotics Hack 2026",
        "organizer": "Robotics Lab",
        "source_name": "Devfolio",
        "source_url": "https://robotics-hack.devfolio.co",
        "deadline": "2026-11-20T18:00:00Z",
        "country": "India",
        "region": "India",
        "format": "In-Person",
        "fee_status": "free",
        "fee_amount": 0.0,
        "tags": "ROS, Python, C++, Robotics",
    }
    upsert_normalized_event(conn, normalize_raw_event(raw_event, is_synthetic=False))
    conn.commit()
    conn.close()

    # Query with 0 skills (empty criteria)
    res_zero_skills = client.get("/api/events")
    assert res_zero_skills.status_code == 200
    events_zero = res_zero_skills.json()["events"]
    assert len(events_zero) >= 1
    # Check that no skill matching reason is falsely injected
    target_event = next(e for e in events_zero if e["title"] == "Autonomous Robotics Hack 2026")
    assert not any("Matched skills" in r for r in target_event["eligibility"]["reasons"])

    # Query with matching skills (e.g. ROS, Python)
    res_with_skills = client.get("/api/events?skills=ROS,Python")
    assert res_with_skills.status_code == 200
    events_matched = res_with_skills.json()["events"]
    target_event_matched = next(e for e in events_matched if e["title"] == "Autonomous Robotics Hack 2026")
    assert any("Matched skills" in r for r in target_event_matched["eligibility"]["reasons"])

# -----------------------------------------------------------------
# 3. Discover Events — Test Data Isolation Tests
# -----------------------------------------------------------------

def test_synthetic_fixtures_excluded_from_default_discovery(isolated_fix_db):
    """
    Verify:
    1. Normal discovery API excludes synthetic events by default.
    2. Synthetic fixtures cannot appear in the default feed.
    3. Synthetic fixtures cannot affect the default total count.
    4. include_synthetic=true explicitly retrieves synthetic test fixtures when isolated testing requires it.
    """
    conn = get_connection(isolated_fix_db)
    raw_genuine_1 = {
        "title": "Genuine Public Hackathon Alpha",
        "organizer": "Global Dev League",
        "source_name": "MLH",
        "source_url": "https://mlh.io/events/genuine-alpha",
        "deadline": "2026-11-25T18:00:00Z",
        "country": "United States",
        "region": "United States",
        "format": "In-Person",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    raw_genuine_2 = {
        "title": "Genuine Public Hackathon Beta",
        "organizer": "Dev Community",
        "source_name": "Devfolio",
        "source_url": "https://devfolio.co/beta",
        "deadline": "2026-11-28T18:00:00Z",
        "country": "India",
        "region": "India",
        "format": "In-Person",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    upsert_normalized_event(conn, normalize_raw_event(raw_genuine_1, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_genuine_2, is_synthetic=False))
    conn.commit()
    conn.close()

    # 1. Default GET /api/events must return only genuine events
    res_default = client.get("/api/events")
    assert res_default.status_code == 200
    data_default = res_default.json()
    events_default = data_default["events"]

    # All returned events must be genuine
    assert all(e["is_synthetic"] is False for e in events_default)
    assert not any("[SYNTHETIC DEMO]" in e["title"] for e in events_default)
    # Total count must reflect only genuine events
    synthetic_in_db = len([e for e in events_default if e["is_synthetic"]])
    assert synthetic_in_db == 0

    # 2. Querying explicitly with include_synthetic=true returns fixtures
    res_with_synthetic = client.get("/api/events?include_synthetic=true")
    assert res_with_synthetic.status_code == 200
    data_syn = res_with_synthetic.json()
    assert any("[SYNTHETIC DEMO]" in e["title"] for e in data_syn["events"])
    assert data_syn["total"] > data_default["total"]

# -----------------------------------------------------------------
# 4. Discover Events — Country & Region Normalization & Filtering Tests
# -----------------------------------------------------------------

def test_country_normalization_and_filtering(isolated_fix_db):
    """
    Verify:
    1. Country codes (e.g. 'FI', 'US', 'GB', 'IN', 'CA') are normalized to readable names.
    2. Filtering by country returns only matching events.
    3. Filtering by 'Global / Online' returns only online/global events and does not contaminate country filters.
    4. Selecting a country does not include Global/Online events as India or another country.
    5. Clearing the filter restores the complete real-event result set.
    """
    # Verify country normalization function
    assert normalize_country_name("FI") == "Finland"
    assert normalize_country_name("IN") == "India"
    assert normalize_country_name("US") == "United States"
    assert normalize_country_name("GB") == "United Kingdom"
    assert normalize_country_name("DE") == "Germany"
    assert normalize_country_name("CA") == "Canada"

    conn = get_connection(isolated_fix_db)
    raw_finland = {
        "title": "Nordic AI Challenge 2026",
        "organizer": "Nordic Tech",
        "source_name": "MLH",
        "source_url": "https://nordic-ai.fi",
        "deadline": "2026-11-20T18:00:00Z",
        "country": "FI",  # Raw country code must be normalized to Finland
        "region": "FI",
        "format": "In-Person",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    raw_india = {
        "title": "Bengaluru Innovation Conclave 2026",
        "organizer": "Karnataka Tech",
        "source_name": "Devfolio",
        "source_url": "https://bengaluru-innovate.devfolio.co",
        "deadline": "2026-11-22T18:00:00Z",
        "country": "India",
        "region": "India",
        "format": "In-Person",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    raw_online = {
        "title": "Worldwide Virtual Code Jam 2026",
        "organizer": "Global Dev Network",
        "source_name": "Devfolio",
        "source_url": "https://worldwide-jam.devfolio.co",
        "deadline": "2026-11-24T18:00:00Z",
        "country": None,
        "region": "Global / Online",
        "format": "Online / Virtual",
        "is_online": True,
        "fee_status": "free",
        "fee_amount": 0.0,
    }

    norm_fi = normalize_raw_event(raw_finland, is_synthetic=False)
    assert norm_fi.country == "Finland"
    assert norm_fi.region == "Finland"

    upsert_normalized_event(conn, norm_fi)
    upsert_normalized_event(conn, normalize_raw_event(raw_india, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_online, is_synthetic=False))
    conn.commit()
    conn.close()

    # 1. Filter by Finland
    res_fi = client.get("/api/events?country=Finland")
    assert res_fi.status_code == 200
    events_fi = res_fi.json()["events"]
    assert any(e["title"] == "Nordic AI Challenge 2026" for e in events_fi)
    assert not any(e["title"] == "Bengaluru Innovation Conclave 2026" for e in events_fi)
    assert not any(e["title"] == "Worldwide Virtual Code Jam 2026" for e in events_fi)

    # 2. Filter by India: must NOT contain Worldwide Virtual Code Jam
    res_in = client.get("/api/events?country=India")
    assert res_in.status_code == 200
    events_in = res_in.json()["events"]
    assert any(e["title"] == "Bengaluru Innovation Conclave 2026" for e in events_in)
    assert not any(e["title"] == "Worldwide Virtual Code Jam 2026" for e in events_in)
    assert not any(e["title"] == "Nordic AI Challenge 2026" for e in events_in)

    # 3. Filter by Global / Online
    res_online = client.get("/api/events?country=Global%20/%20Online")
    assert res_online.status_code == 200
    events_online = res_online.json()["events"]
    assert any(e["title"] == "Worldwide Virtual Code Jam 2026" for e in events_online)
    assert not any(e["title"] == "Bengaluru Innovation Conclave 2026" for e in events_online)

    # 4. Clear filter restores all genuine events
    res_all = client.get("/api/events")
    assert res_all.status_code == 200
    titles_all = {e["title"] for e in res_all.json()["events"]}
    assert "Nordic AI Challenge 2026" in titles_all
    assert "Bengaluru Innovation Conclave 2026" in titles_all
    assert "Worldwide Virtual Code Jam 2026" in titles_all
