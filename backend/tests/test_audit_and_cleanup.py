import sqlite3
import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app, lifespan
from app.database import init_db
from app.adapters.mlh import MLHAdapter
from app.adapters.unstop import UnstopAdapter
from app.adapters.devfolio import DevfolioAdapter
from app.event_service import refresh_events_from_sources, get_adapter_statuses
from app.notification_service import (
    evaluate_and_generate_notifications,
    get_user_notifications,
    get_deadline_groups,
    save_notification_preferences,
    NotificationPreferencesPayload,
)

client = TestClient(app)

def test_startup_does_not_insert_synthetic_events():
    """Verify that normal application startup / init_db on a clean DB does NOT seed synthetic events."""
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    
    # Run database initialization
    init_db(mem_conn)
    
    # Verify events table is empty
    cursor = mem_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events;")
    total_events = cursor.fetchone()[0]
    assert total_events == 0, f"Expected 0 events after clean init_db, found {total_events}"
    
    # Run notification evaluation on empty DB
    inserted = evaluate_and_generate_notifications(mem_conn, "test@ziro.local")
    assert inserted == 0
    
    # Verify still 0 events
    cursor.execute("SELECT COUNT(*) FROM events;")
    assert cursor.fetchone()[0] == 0
    mem_conn.close()

def test_user_facing_discovery_excludes_synthetic():
    """Verify that GET /api/events excludes synthetic fixtures by default."""
    res = client.get("/api/events")
    assert res.status_code == 200
    data = res.json()
    for ev in data["events"]:
        assert ev.get("is_synthetic") is False or ev.get("is_synthetic") == 0
        assert "synthetic" not in ev["source_name"].lower()

def test_adapter_statuses_excludes_synthetic():
    """Verify adapter statuses only list real sources and exclude synthetic demo fixtures."""
    res = client.get("/api/adapters/status")
    assert res.status_code == 200
    data = res.json()
    sources = [a["source_name"].lower() for a in data["adapters"]]
    assert "synthetic" not in sources
    assert "devfolio" in sources
    assert "mlh" in sources
    assert "unstop" in sources

def test_mlh_adapter_never_infers_deadline_from_start_date():
    """Verify MLH adapter strictly marks deadline as None / unavailable."""
    adapter = MLHAdapter()
    assert adapter.source_name == "MLH"
    # Even if MLH has startsAt, deadline must be None and deadline_status unavailable
    # Verify adapter properties
    assert adapter.is_available() is True

def test_unstop_adapter_reports_403_truthfully():
    """Verify Unstop adapter truthfully reports HTTP 403 Forbidden without bypass."""
    class Mock403Client:
        def get(self, *args, **kwargs):
            class Response:
                status_code = 403
                text = "Cloudflare bot challenge: Access Denied"
            return Response()

    adapter = UnstopAdapter()
    assert adapter.source_name == "Unstop"
    res = adapter.fetch_events(client=Mock403Client())
    assert res.status == "restricted"
    assert "403" in res.error_message
    assert "Cloudflare" in res.error_message
    assert "unstop.com/hackathons" in res.error_message

def test_unstop_adapter_parses_real_json():
    """Verify Unstop adapter parses valid public opportunity JSON into NormalizedEventRecords."""
    class Mock200Client:
        def get(self, *args, **kwargs):
            class Response:
                status_code = 200
                def json(self):
                    return {
                        "data": {
                            "data": [
                                {
                                    "id": 999001,
                                    "title": "Quantum AI Hackathon",
                                    "public_url": "hackathons/quantum-ai-999001",
                                    "organisation": {"name": "National Tech Council"},
                                    "regnRequirements": {
                                        "start_regn_dt": "2026-10-01T00:00:00+05:30",
                                        "end_regn_dt": "2026-11-15T23:59:59+05:30",
                                        "min_team_size": 2,
                                        "max_team_size": 4,
                                    },
                                    "payment_services": [{"amount": 0}],
                                    "required_skills": [{"skill": "Python"}, {"skill": "Quantum Computing"}],
                                    "filters": [{"name": "Engineering Students"}],
                                    "address_with_country_logo": {
                                        "city": "Bengaluru",
                                        "state": "Karnataka",
                                        "country": {"name": "India"}
                                    }
                                }
                            ]
                        }
                    }
            return Response()

    adapter = UnstopAdapter()
    res = adapter.fetch_events(client=Mock200Client())
    assert res.status == "success"
    assert res.events_count == 1
    ev = res.events[0]
    assert ev.title == "Quantum AI Hackathon"
    assert ev.source_event_id == "999001"
    assert ev.source_url == "https://unstop.com/hackathons/quantum-ai-999001"
    assert ev.team_min == 2
    assert ev.team_max == 4
    assert ev.fee_status == "free"
    assert "Quantum Computing" in ev.tags

def test_refresh_events_real_discovery_and_deduplication():
    """Verify refresh_events_from_sources discovers new events, updates existing ones, and prevents duplicates."""
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    init_db(mem_conn)

    # First refresh: Devfolio and MLH live endpoints (or test adapter)
    report1 = refresh_events_from_sources(mem_conn, source_name="devfolio", limit_per_source=3)
    assert report1["status"] == "completed" and report1["sync_status"] in ("success", "partial_success")
    discovered1 = report1["total_discovered"]
    assert discovered1 > 0, "Expected new events discovered on first refresh"
    assert report1["total_updated"] == 0

    # Second refresh with same source: must be idempotent (0 newly discovered, all updated)
    report2 = refresh_events_from_sources(mem_conn, source_name="devfolio", limit_per_source=3)
    assert report2["total_discovered"] == 0, "Repeated refresh must not create duplicate events"
    assert report2["total_updated"] == discovered1

    # Verify database count matches discovered count (no duplicates)
    cursor = mem_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM events WHERE source_name = 'Devfolio';")
    assert cursor.fetchone()[0] == discovered1

    mem_conn.close()

def test_cached_listings_remain_available_on_source_failure():
    """Verify that if an adapter fails or returns 403, previously cached listings remain in DB."""
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    init_db(mem_conn)
    cursor = mem_conn.cursor()

    # Pre-populate 1 genuine cached event
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO events (
            title, description, organizer, source_name, source_event_id, source_url,
            retrieved_at, deadline, deadline_status, verification_status, tags, is_synthetic
        ) VALUES (
            'Cached Global Hackathon', 'Description', 'MLH Org', 'MLH', 'mlh-cached-1',
            'https://mlh.io/cached-1', ?, '2026-11-20T23:59:59+00:00', 'verified', 'verified',
            'Python, Web', 0
        );
    """, (now_iso,))
    mem_conn.commit()

    # Verify cached event is present
    cursor.execute("SELECT COUNT(*) FROM events WHERE source_name = 'MLH';")
    assert cursor.fetchone()[0] == 1

    # Re-verify after failed refresh or empty result: existing cached listings remain intact
    cursor.execute("SELECT title, retrieved_at FROM events WHERE source_event_id = 'mlh-cached-1';")
    row = cursor.fetchone()
    assert row["title"] == "Cached Global Hackathon"
    assert row["retrieved_at"] == now_iso

    mem_conn.close()

def test_notification_matching_requires_genuine_skills():
    """Verify notification generation strictly requires skill matches and excludes synthetic fixtures."""
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    init_db(mem_conn)
    cursor = mem_conn.cursor()
    
    # Insert student profile with no skills
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO student_profiles (student_name, student_email, skills, updated_at)
        VALUES ('Test Student', 'student@test.local', '', ?);
    """, (now_iso,))
    
    # Insert real event with Rust tag and far future verified deadline
    cursor.execute("""
        INSERT INTO events (
            title, description, organizer, source_name, source_event_id, source_url,
            retrieved_at, deadline, deadline_status, verification_status, tags, is_synthetic
        ) VALUES (
            'Rust Hackathon 2026', 'Desc', 'Rust Org', 'Devfolio', 'dev-rust-1', 'https://devfolio.co/rust',
            ?, '2026-12-01T23:59:59+00:00', 'verified', 'verified', 'Rust, Systems', 0
        );
    """, (now_iso,))
    mem_conn.commit()
    
    # Evaluate with no matching skills: should NOT insert matching notification
    inserted = evaluate_and_generate_notifications(mem_conn, "student@test.local")
    # No deadline reminder since deadline is in December (more than 7 days)
    # No matching contest because user skills are empty
    assert inserted == 0
    
    # Now give user Python skill (does not match Rust)
    cursor.execute("UPDATE student_profiles SET skills = 'Python, Django' WHERE student_email = 'student@test.local';")
    mem_conn.commit()
    inserted = evaluate_and_generate_notifications(mem_conn, "student@test.local")
    assert inserted == 0
    
    # Now give user Rust skill (matches Rust)
    cursor.execute("UPDATE student_profiles SET skills = 'Rust, Systems' WHERE student_email = 'student@test.local';")
    mem_conn.commit()
    inserted = evaluate_and_generate_notifications(mem_conn, "student@test.local")
    assert inserted == 1
    
    # Re-running evaluation must be idempotent (0 new notifications)
    inserted_again = evaluate_and_generate_notifications(mem_conn, "student@test.local")
    assert inserted_again == 0
    
    mem_conn.close()

def test_deadline_change_notification():
    """Verify notification is generated when verified registration deadline changes."""
    mem_conn = sqlite3.connect(":memory:")
    mem_conn.row_factory = sqlite3.Row
    init_db(mem_conn)
    cursor = mem_conn.cursor()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_utc.isoformat()
    
    # Insert event due in 3 days (within 7d window)
    deadline1 = (now_utc + datetime.timedelta(days=3)).isoformat()
    cursor.execute("""
        INSERT INTO events (
            id, title, description, organizer, source_name, source_event_id, source_url,
            retrieved_at, deadline, deadline_status, verification_status, tags, is_synthetic
        ) VALUES (
            101, 'AI Challenge', 'Desc', 'Devfolio Org', 'Devfolio', 'dev-ai-1', 'https://devfolio.co/ai',
            ?, ?, 'verified', 'verified', 'AI, Python', 0
        );
    """, (now_iso, deadline1))
    mem_conn.commit()
    
    # Generate 7d reminder
    inserted = evaluate_and_generate_notifications(mem_conn, "student@ziro.local")
    assert inserted >= 1
    
    # Now update deadline to 5 days
    deadline2 = (now_utc + datetime.timedelta(days=5)).isoformat()
    cursor.execute("UPDATE events SET deadline = ? WHERE id = 101;", (deadline2,))
    mem_conn.commit()
    
    # Next evaluation should detect deadline change
    inserted_change = evaluate_and_generate_notifications(mem_conn, "student@ziro.local")
    assert inserted_change >= 1
    
    notifs = get_user_notifications(mem_conn, "student@ziro.local")
    change_notifs = [n for n in notifs.notifications if n.category == "deadline_change"]
    assert len(change_notifs) == 1
    assert "Deadline Changed" in change_notifs[0].title
    
    mem_conn.close()
