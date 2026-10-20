import sqlite3
import datetime
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.config import SESSION_COOKIE_NAME
from app import auth_service

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Provides an isolated database for auth and security tests."""
    db_file = tmp_path / "test_auth.db"
    monkeypatch.setattr("app.database.DB_PATH", str(db_file))
    monkeypatch.setattr("app.config.DB_PATH", str(db_file))
    monkeypatch.setattr("app.config.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("app.config.GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr("app.auth_service.GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr("app.auth_service.GOOGLE_CLIENT_SECRET", "test-client-secret")
    init_db()
    return db_file

@pytest.fixture
def client(test_db):
    return TestClient(app)

def test_google_auth_url_generation(client, test_db):
    """Test generating OAuth authorization URL with state and nonce."""
    res = client.get("/api/auth/google/url?return_to=/my-criteria")
    assert res.status_code == 200
    data = res.json()
    assert "url" in data
    assert "accounts.google.com" in data["url"]
    assert "state=" in data["url"]
    assert "client_id=test-client-id" in data["url"]

    # Verify state was saved in oauth_states table
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM oauth_states;")
    states = cursor.fetchall()
    assert len(states) == 1
    assert states[0]["return_to"] == "/my-criteria"
    conn.close()

def test_missing_oauth_config_fails_gracefully(client, monkeypatch):
    """When OAuth client is unconfigured, return 503 instead of silent fake login."""
    monkeypatch.setattr("app.auth_service.GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr("app.auth_service.GOOGLE_CLIENT_SECRET", "")
    res = client.get("/api/auth/google/url")
    assert res.status_code == 503
    assert "Google OAuth credentials are not configured" in res.json()["detail"]

def test_invalid_state_rejected(client):
    """OAuth callback with invalid or missing state must fail securely."""
    res = client.get("/api/auth/google/callback?code=fake-code&state=non-existent-state", follow_redirects=False)
    assert res.status_code == 303
    assert "error=invalid_state" in res.headers["location"] or "error=" in res.headers["location"]

def test_one_time_state_consumption_prevents_replay(client, test_db):
    """State parameter must be strictly single-use to prevent replay attacks."""
    res = client.get("/api/auth/google/url")
    state = res.json()["url"].split("state=")[1].split("&")[0]

    # First attempt with fake code (will fail at code exchange, but state is consumed)
    with patch("app.auth_service.exchange_code_for_tokens", side_effect=auth_service.AuthError("Code expired", 400)):
        res1 = client.get(f"/api/auth/google/callback?code=any-code&state={state}", follow_redirects=False)
        assert res1.status_code == 303

    # Second attempt with same state must be rejected as invalid state (already consumed)
    res2 = client.get(f"/api/auth/google/callback?code=any-code&state={state}", follow_redirects=False)
    assert res2.status_code == 303
    assert "invalid_state" in res2.headers["location"] or "Invalid" in res2.headers["location"]

def test_open_redirect_prevention(client, test_db):
    """External return_to domains must be blocked to prevent open redirects."""
    # Malicious external domain
    res = client.get("/api/auth/google/url?return_to=https://attacker.com/evil")
    assert res.status_code == 200

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT return_to FROM oauth_states;")
    rows = cursor.fetchall()
    # Malicious return_to must be stripped/null
    assert len(rows) > 0
    assert rows[-1]["return_to"] is None
    conn.close()

def test_successful_first_time_login_redirects_to_onboarding(client, test_db):
    """New user sign-in creates identity and redirects to My Profile with onboarding=1."""
    # 1. Start flow
    res = client.get("/api/auth/google/url?return_to=/events")
    state = res.json()["url"].split("state=")[1].split("&")[0]

    # 2. Mock token exchange and ID token verification
    mock_tokens = {"id_token": "valid.mock.token", "access_type": "bearer"}
    mock_claims = {
        "sub": "google-sub-10001",
        "email": "sarah.dev@example.com",
        "email_verified": True,
        "name": "Sarah Developer",
        "picture": "https://example.com/sarah.jpg",
    }

    with patch("app.main.exchange_code_for_tokens", return_value=mock_tokens), \
         patch("app.main.verify_google_id_token", return_value=mock_claims):
        cb_res = client.get(f"/api/auth/google/callback?code=mock-code&state={state}", follow_redirects=False)

    assert cb_res.status_code == 303
    # Destination must be /profile?onboarding=1 because new user's profile is incomplete
    assert "/profile?onboarding=1" in cb_res.headers["location"]

    # Verify session cookie was set
    cookie_header = cb_res.headers.get("set-cookie", "")
    assert SESSION_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header

    # Extract session cookie to test /api/auth/me
    client.cookies.set(SESSION_COOKIE_NAME, cb_res.cookies[SESSION_COOKIE_NAME])
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == "sarah.dev@example.com"
    assert me_data["user"]["is_profile_complete"] is False
    assert len(me_data["profile_completion"]["missing_fields"]) > 0

def test_existing_user_with_complete_profile_redirects_to_intended_destination(client, test_db):
    """Existing user with complete profile skips onboarding and reaches destination."""
    # Seed user with complete profile
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO users (email, name, is_profile_complete, created_at, updated_at)
    VALUES ('pro.hacker@example.com', 'Alex Hacker', 1, '2026-01-01', '2026-01-01');
    """)
    uid = cursor.lastrowid
    cursor.execute("""
    INSERT INTO user_identities (user_id, provider, provider_sub, email, email_verified, created_at, updated_at)
    VALUES (?, 'google', 'google-sub-20002', 'pro.hacker@example.com', 1, '2026-01-01', '2026-01-01');
    """, (uid,))
    cursor.execute("""
    INSERT INTO student_profiles (
        user_id, student_name, student_email, institution, degree, graduation_year, skills, team_size, region, updated_at
    ) VALUES (?, 'Alex Hacker', 'pro.hacker@example.com', 'MIT', 'CS', '2026', 'Python, React', 2, 'All', '2026-01-01');
    """, (uid,))
    conn.commit()
    conn.close()

    # Generate state with return_to=/my-registrations
    res = client.get("/api/auth/google/url?return_to=/my-registrations")
    state = res.json()["url"].split("state=")[1].split("&")[0]

    mock_tokens = {"id_token": "valid.mock.token"}
    mock_claims = {
        "sub": "google-sub-20002",
        "email": "pro.hacker@example.com",
        "email_verified": True,
        "name": "Alex Hacker",
    }

    with patch("app.main.exchange_code_for_tokens", return_value=mock_tokens), \
         patch("app.main.verify_google_id_token", return_value=mock_claims):
        cb_res = client.get(f"/api/auth/google/callback?code=mock-code&state={state}", follow_redirects=False)

    assert cb_res.status_code == 303
    # Destination must be /my-registrations without forcing onboarding
    assert "/my-registrations" in cb_res.headers["location"]

def test_repeated_login_preserves_records_without_duplicates(client, test_db):
    """Repeated login using same Google sub does not duplicate user or identity records."""
    mock_claims = {
        "sub": "google-sub-stable-99",
        "email": "repeat.user@example.com",
        "email_verified": True,
        "name": "Repeat User",
    }

    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row
    u1, is_new1 = auth_service.get_or_create_user_from_google(conn, mock_claims)
    assert is_new1 is True

    # Second login
    u2, is_new2 = auth_service.get_or_create_user_from_google(conn, mock_claims)
    assert is_new2 is False
    assert u1["id"] == u2["id"]

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM users;")
    assert cursor.fetchone()["cnt"] == 1
    cursor.execute("SELECT COUNT(*) as cnt FROM user_identities;")
    assert cursor.fetchone()["cnt"] == 1
    conn.close()

def test_user_profile_isolation(client, test_db):
    """User A and User B have strictly isolated profile records."""
    conn = sqlite3.connect(str(test_db))
    conn.row_factory = sqlite3.Row

    # Create User A
    uA, _ = auth_service.get_or_create_user_from_google(conn, {
        "sub": "sub-A", "email": "alice@example.com", "name": "Alice"
    })
    sessA, _ = auth_service.create_user_session(conn, uA["id"])

    # Create User B
    uB, _ = auth_service.get_or_create_user_from_google(conn, {
        "sub": "sub-B", "email": "bob@example.com", "name": "Bob"
    })
    sessB, _ = auth_service.create_user_session(conn, uB["id"])
    conn.close()

    # User A updates profile
    resA = client.put(
        "/api/profile",
        headers={"Authorization": f"Bearer {sessA}"},
        json={
            "student_name": "Alice Wonderland",
            "student_email": "alice@example.com",
            "institution": "Stanford University",
            "degree": "Computer Science",
            "graduation_year": "2026",
            "skills": ["Python", "PyTorch"],
            "team_size": 3,
            "region": "North America",
            "participation_mode": "Online",
        }
    )
    assert resA.status_code == 200

    # User B queries profile -> must NOT see Alice's data
    resB = client.get("/api/profile", headers={"Authorization": f"Bearer {sessB}"})
    assert resB.status_code == 200
    profileB = resB.json()
    assert profileB["student_name"] == "Bob"
    assert profileB["institution"] is None
    assert profileB["skills"] == []

def test_profile_completion_unlocks_onboarding_status(client, test_db):
    """Submitting required profile fields flips is_profile_complete to true."""
    conn = sqlite3.connect(str(test_db))
    u, _ = auth_service.get_or_create_user_from_google(conn, {
        "sub": "sub-test-complete", "email": "student@college.edu", "name": "Charlie"
    })
    sess, _ = auth_service.create_user_session(conn, u["id"])
    conn.close()

    # Incomplete profile initially
    me1 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {sess}"})
    assert me1.json()["profile_completion"]["is_complete"] is False

    # Complete the required fields
    client.put(
        "/api/profile",
        headers={"Authorization": f"Bearer {sess}"},
        json={
            "student_name": "Charlie Chaplin",
            "student_email": "student@college.edu",
            "institution": "Georgia Tech",
            "degree": "Robotics Engineering",
            "graduation_year": "2027",
            "skills": ["ROS", "C++", "Python"],
            "team_size": 2,
            "region": "All",
        }
    )

    # Now verify /api/auth/me reflects completed onboarding
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {sess}"})
    assert me2.json()["profile_completion"]["is_complete"] is True
    assert len(me2.json()["profile_completion"]["missing_fields"]) == 0

def test_logout_invalidates_session_and_clears_cookie(client, test_db):
    """Logging out destroys the session on backend and deletes cookie."""
    conn = sqlite3.connect(str(test_db))
    u, _ = auth_service.get_or_create_user_from_google(conn, {
        "sub": "sub-logout-test", "email": "logout.test@example.com", "name": "Dave"
    })
    sess, _ = auth_service.create_user_session(conn, u["id"])
    conn.close()

    client.cookies.set(SESSION_COOKIE_NAME, sess)
    # Confirm authenticated
    res_me = client.get("/api/auth/me")
    assert res_me.json()["authenticated"] is True

    # Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True

    # Session in DB must be deleted
    conn = sqlite3.connect(str(test_db))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_sessions WHERE session_id = ?;", (sess,))
    assert cursor.fetchone() is None
    conn.close()

    # Subsequent request is unauthenticated
    res_after = client.get("/api/auth/me")
    assert res_after.json()["authenticated"] is False

def test_token_signature_verification_failure(monkeypatch):
    """Invalid token signature must raise TokenVerificationError."""
    monkeypatch.setattr(auth_service, "GOOGLE_CLIENT_ID", "mock-client-id")
    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Invalid crypto signature")):
        with pytest.raises(auth_service.TokenVerificationError) as exc_info:
            auth_service.verify_google_id_token("invalid.token.signature")
        assert "verification failed" in str(exc_info.value)

def test_token_missing_sub_claim_fails(monkeypatch):
    """ID token missing stable 'sub' claim must be rejected."""
    monkeypatch.setattr(auth_service, "GOOGLE_CLIENT_ID", "mock-client-id")
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value={"iss": "accounts.google.com", "email": "test@test.com"}):
        with pytest.raises(auth_service.TokenVerificationError) as exc_info:
            auth_service.verify_google_id_token("token.missing.sub")
        assert "sub" in str(exc_info.value)


def test_oauth_callback_delivers_session_token_and_preserves_client_origin(client, test_db):
    """OAuth callback must append session_token for cross-origin resilience and preserve client origin."""
    # Initiate from 127.0.0.1:5173
    url_res = client.get(
        "/api/auth/google/url?return_to=/events",
        headers={"Origin": "http://127.0.0.1:5173"}
    )
    assert url_res.status_code == 200
    state = url_res.json()["url"].split("state=")[1].split("&")[0]

    mock_tokens = {"id_token": "valid.mock.token"}
    mock_claims = {
        "sub": "google-sub-cross-origin-1",
        "email": "cross.origin@example.com",
        "email_verified": True,
        "name": "Cross Origin Dev",
    }

    with patch("app.main.exchange_code_for_tokens", return_value=mock_tokens), \
         patch("app.main.verify_google_id_token", return_value=mock_claims):
        cb_res = client.get(f"/api/auth/google/callback?code=mock-code&state={state}", follow_redirects=False)

    assert cb_res.status_code == 303
    location = cb_res.headers["location"]
    # Preserves client origin
    assert location.startswith("http://127.0.0.1:5173")
    # Delivers session_token query parameter
    assert "session_token=" in location

    # Extract session token from location URL
    session_token = location.split("session_token=")[1].split("&")[0]
    assert len(session_token) > 20

    # Ensure /api/auth/me succeeds with Bearer token EVEN WITH ZERO COOKIES
    client.cookies.clear()
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {session_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == "cross.origin@example.com"

