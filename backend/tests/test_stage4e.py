import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database

@pytest.fixture(scope="session")
def isolated_stage4e_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_stage4e.db")
    
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
def setup_isolated_context(isolated_stage4e_db):
    conn = get_connection(isolated_stage4e_db)
    conn.execute("DELETE FROM student_profiles;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_stage4e_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

def test_student_portfolio_fields_persistence():
    """Verify Stage 4E student portfolio fields (institution, degree, links, bio) persist cleanly."""
    put_res = client.put("/api/profile", json={
        "student_name": "Arjun Patel",
        "student_email": "arjun@iitb.ac.in",
        "skills": ["Python", "FastAPI", "React", "PyTorch"],
        "team_size": 3,
        "region": "India",
        "budget": 20.0,
        "institution": "Indian Institute of Technology Bombay",
        "degree": "B.Tech Computer Science & Engineering",
        "graduation_year": "2027",
        "github_url": "https://github.com/arjunpatel",
        "linkedin_url": "https://linkedin.com/in/arjunpatel",
        "portfolio_url": "https://arjunpatel.dev",
        "bio": "AI systems builder and competitive programmer.",
        "collaboration_preference": "Open to joining teams",
        "projects_json": '[{"id":"p1","title":"SmartRouter","description":"Fast dynamic router","tech_stack":["Python","FastAPI"]}]',
        "participation_mode": "Hybrid"
    })
    assert put_res.status_code == 200
    saved = put_res.json()
    assert saved["student_name"] == "Arjun Patel"
    assert saved["institution"] == "Indian Institute of Technology Bombay"
    assert saved["degree"] == "B.Tech Computer Science & Engineering"
    assert saved["graduation_year"] == "2027"
    assert saved["github_url"] == "https://github.com/arjunpatel"
    assert saved["linkedin_url"] == "https://linkedin.com/in/arjunpatel"
    assert saved["portfolio_url"] == "https://arjunpatel.dev"
    assert saved["bio"] == "AI systems builder and competitive programmer."
    assert saved["collaboration_preference"] == "Open to joining teams"
    assert saved["participation_mode"] == "Hybrid"
    assert saved["updated_at"] is not None

    # Retrieve to confirm SQLite read-back
    get_res = client.get("/api/profile")
    assert get_res.status_code == 200
    persisted = get_res.json()
    assert persisted["student_name"] == "Arjun Patel"
    assert persisted["institution"] == "Indian Institute of Technology Bombay"
    assert persisted["degree"] == "B.Tech Computer Science & Engineering"
    assert persisted["graduation_year"] == "2027"
    assert persisted["github_url"] == "https://github.com/arjunpatel"
    assert persisted["linkedin_url"] == "https://linkedin.com/in/arjunpatel"
    assert persisted["portfolio_url"] == "https://arjunpatel.dev"
    assert persisted["bio"] == "AI systems builder and competitive programmer."
    assert persisted["collaboration_preference"] == "Open to joining teams"
    assert "SmartRouter" in persisted["projects_json"]

def test_student_profile_defaults_and_backward_compatibility():
    """Verify GET /api/profile returns safe non-fabricated defaults when table is empty."""
    res = client.get("/api/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["student_name"] is None
    assert data["institution"] is None
    assert data["degree"] is None
    assert data["graduation_year"] is None
    assert data["team_size"] == 2
    assert data["skills"] == []
