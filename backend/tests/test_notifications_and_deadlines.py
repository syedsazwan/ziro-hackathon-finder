import os
import tempfile
import datetime
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database
from app.notification_service import (
    get_notification_preferences,
    save_notification_preferences,
    calculate_deadline_group,
    evaluate_and_generate_notifications,
    get_user_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    get_deadline_groups,
)
from app.schemas import NotificationPreferencesPayload

IST = ZoneInfo("Asia/Kolkata")
client = TestClient(app)

@pytest.fixture(scope="session")
def isolated_notif_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_notif.db")
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
def setup_db(isolated_notif_db):
    conn = get_connection(isolated_notif_db)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notifications;")
    cursor.execute("DELETE FROM notification_preferences;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_notif_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

def test_notification_preferences_defaults_and_save(isolated_notif_db):
    conn = get_connection(isolated_notif_db)
    try:
        # Default for new user
        prefs = get_notification_preferences(conn, "new_student@ziro.local")
        assert prefs.matching_events_enabled is True
        assert prefs.master_reminders_enabled is True
        assert prefs.remind_7_days is True
        assert prefs.remind_48_hours is True
        assert prefs.remind_24_hours is True
        assert prefs.browser_notifications_enabled is False

        # Save custom
        payload = NotificationPreferencesPayload(
            matching_events_enabled=False,
            upcoming_deadlines_enabled=True,
            deadline_changes_enabled=False,
            master_reminders_enabled=True,
            remind_7_days=False,
            remind_48_hours=True,
            remind_24_hours=True,
            browser_notifications_enabled=True,
        )
        saved = save_notification_preferences(conn, "new_student@ziro.local", payload)
        assert saved.matching_events_enabled is False
        assert saved.remind_7_days is False
        assert saved.remind_48_hours is True
        assert saved.browser_notifications_enabled is True

        # Re-fetch
        fetched = get_notification_preferences(conn, "new_student@ziro.local")
        assert fetched.matching_events_enabled is False
        assert fetched.remind_48_hours is True
        assert fetched.browser_notifications_enabled is True
    finally:
        conn.close()

def test_deadline_group_calculation():
    ref_utc = datetime.datetime(2026, 11, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
    ref_ist = ref_utc.astimezone(IST)

    # 1. Due Today (same day IST)
    today_deadline_ist = (ref_ist.replace(hour=23, minute=59, second=0)).isoformat()
    group, days, hours, expired = calculate_deadline_group(today_deadline_ist, reference_time_utc=ref_utc)
    assert group == "Due Today"
    assert days == 0
    assert expired is False

    # 2. Due Tomorrow (next calendar day IST)
    tomorrow_deadline_ist = (ref_ist + datetime.timedelta(days=1)).replace(hour=18, minute=0).isoformat()
    group, days, hours, expired = calculate_deadline_group(tomorrow_deadline_ist, reference_time_utc=ref_utc)
    assert group == "Due Tomorrow"
    assert days == 1
    assert expired is False

    # 3. Next 7 Days (4 days out)
    four_days_ist = (ref_ist + datetime.timedelta(days=4)).isoformat()
    group, days, hours, expired = calculate_deadline_group(four_days_ist, reference_time_utc=ref_utc)
    assert group == "Due in the Next 7 Days"
    assert days == 4
    assert expired is False

    # 4. Later (15 days out)
    later_ist = (ref_ist + datetime.timedelta(days=15)).isoformat()
    group, days, hours, expired = calculate_deadline_group(later_ist, reference_time_utc=ref_utc)
    assert group == "Later"
    assert days == 15
    assert expired is False

    # 5. Deadline Passed
    past_ist = (ref_ist - datetime.timedelta(days=2)).isoformat()
    group, days, hours, expired = calculate_deadline_group(past_ist, reference_time_utc=ref_utc)
    assert group == "Deadline Passed"
    assert expired is True

    # 6. Needs Verification
    group, days, hours, expired = calculate_deadline_group(
        "2026-11-15T23:59:00+05:30",
        verification_status="needs_verification",
        reference_time_utc=ref_utc,
    )
    assert group == "Needs Verification"

def test_evaluate_notifications_and_duplicate_suppression(isolated_notif_db):
    conn = get_connection(isolated_notif_db)
    try:
        user_email = "student_test@ziro.local"
        ref_utc = datetime.datetime(2026, 11, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)

        # Insert a controlled event due in 36 hours (which hits the 48h reminder window)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO events (
            title, description, organizer, source_name, source_event_id, source_url,
            registration_url, retrieved_at, deadline, timezone, is_synthetic, verification_status,
            team_min, team_max, fee_currency, fee_status, tags, region, format, data_source_type
        ) VALUES (
            'AI World Hackathon 2026', 'Worldwide AI challenge', 'Global AI Org', 'Devfolio',
            'ai-world-2026', 'https://aiworld.devfolio.co', 'https://aiworld.devfolio.co/apply',
            '2026-10-25T10:00:00Z', '2026-11-02T22:00:00+00:00', 'UTC', 0, 'verified',
            1, 4, 'USD', 'free', 'AI,ML,Hackathon', 'Global / Online', 'Online / Virtual', 'official_api'
        );
        """)
        conn.commit()

        # Run evaluation 1st time
        count1 = evaluate_and_generate_notifications(conn, user_email=user_email, reference_time_utc=ref_utc)
        assert count1 > 0

        # Retrieve notifications
        notifs = get_user_notifications(conn, user_email=user_email)
        assert notifs.total_count > 0
        assert notifs.unread_count > 0

        first = notifs.notifications[0]
        assert "AI World Hackathon 2026" in first.title or "AI World Hackathon 2026" in first.event_title
        assert first.is_read is False

        # Run evaluation 2nd time: should NOT produce duplicate reminders
        count2 = evaluate_and_generate_notifications(conn, user_email=user_email, reference_time_utc=ref_utc)
        assert count2 == 0  # Deduplication successfully suppressed duplicates!

        # Total count should be unchanged
        notifs2 = get_user_notifications(conn, user_email=user_email)
        assert notifs2.total_count == notifs.total_count

        # Mark read
        marked = mark_notification_read(conn, first.id, user_email=user_email)
        assert marked is True
        notifs3 = get_user_notifications(conn, user_email=user_email)
        assert notifs3.unread_count == notifs.unread_count - 1

        # Mark all read
        mark_all_notifications_read(conn, user_email=user_email)
        notifs4 = get_user_notifications(conn, user_email=user_email)
        assert notifs4.unread_count == 0
    finally:
        conn.close()

def test_api_notification_and_deadline_endpoints():
    user = "api_user@ziro.local"

    # 1. Preferences GET & PUT
    res_pref = client.get(f"/api/notifications/preferences?user_email={user}")
    assert res_pref.status_code == 200
    data = res_pref.json()
    assert data["matching_events_enabled"] is True
    assert data["master_reminders_enabled"] is True

    payload = {
        "matching_events_enabled": False,
        "upcoming_deadlines_enabled": True,
        "deadline_changes_enabled": True,
        "master_reminders_enabled": True,
        "remind_7_days": True,
        "remind_48_hours": False,
        "remind_24_hours": True,
        "browser_notifications_enabled": False,
    }
    put_res = client.put(f"/api/notifications/preferences?user_email={user}", json=payload)
    assert put_res.status_code == 200
    assert put_res.json()["matching_events_enabled"] is False
    assert put_res.json()["remind_48_hours"] is False

    # 2. Evaluate POST
    eval_res = client.post(f"/api/notifications/evaluate?user_email={user}")
    assert eval_res.status_code == 200
    assert "newly_generated" in eval_res.json()

    # 3. Notifications List GET
    list_res = client.get(f"/api/notifications?user_email={user}")
    assert list_res.status_code == 200
    assert "notifications" in list_res.json()
    assert "unread_count" in list_res.json()

    # 4. Deadline Groups GET
    groups_res = client.get("/api/events/deadlines/groups")
    assert groups_res.status_code == 200
    assert "groups" in groups_res.json()
    assert "counts" in groups_res.json()
    assert "Due Today" in groups_res.json()["groups"]
    assert "Due in the Next 7 Days" in groups_res.json()["groups"]
    assert "Later" in groups_res.json()["groups"]

def test_unknown_deadlines_never_produce_deadline_reminders(isolated_notif_db):
    """Verify events with unlisted/unavailable deadlines never generate deadline reminder notifications."""
    conn = get_connection(isolated_notif_db)
    cursor = conn.cursor()
    user_email = "mlh_tester@ziro.local"

    # Insert an event with deadline_status = 'unavailable' (e.g. MLH event)
    cursor.execute("""
    INSERT INTO events (
        title, description, organizer, source_name, source_url, registration_url,
        retrieved_at, team_min, team_max, fee_amount, fee_currency, fee_status,
        deadline, timezone, start_date, end_date, location, region, country, format,
        verification_status, deadline_status, is_synthetic, data_source_type, tags
    ) VALUES (
        'MLH HackCon 2026', 'Official MLH hackathon', 'MLH', 'MLH', 'https://mlh.io/hackcon', 'https://mlh.io/hackcon',
        '2026-10-20T00:00:00Z', 1, 4, 0.0, 'USD', 'free',
        '', 'UTC', '2026-10-24T00:00:00Z', '2026-10-26T00:00:00Z', 'Seattle', 'North America', 'United States', 'In-Person',
        'verified', 'unavailable', 0, 'official_api', 'Hackathon'
    );
    """)
    event_id = cursor.lastrowid
    conn.commit()

    try:
        # Run notification evaluation
        newly_inserted = evaluate_and_generate_notifications(conn, user_email=user_email)
        
        # Verify no deadline_reminder was created for this event
        cursor.execute("""
        SELECT * FROM notifications
        WHERE user_email = ? AND event_id = ? AND category = 'deadline_reminder';
        """, (user_email, event_id))
        deadline_reminders = cursor.fetchall()
        assert len(deadline_reminders) == 0, "Unlisted deadline must not produce deadline reminders"
    finally:
        conn.close()

