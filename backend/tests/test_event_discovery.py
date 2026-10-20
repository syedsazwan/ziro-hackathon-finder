import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_connection, init_db, get_db
from app.seed import seed_database
from app.normalization import (
    normalize_raw_event,
    convert_deadline_to_ist_safe,
    is_deadline_expired,
    validate_source_url,
    NormalizationError,
)
from app.event_service import refresh_events_from_sources, upsert_normalized_event

@pytest.fixture(scope="session")
def isolated_discovery_db():
    """Isolated temporary SQLite database for Stage 3 tests."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_isolated_discovery.db")
    
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
def setup_isolated_discovery_context(isolated_discovery_db):
    """Overrides get_db and cleans real/test event data from temporary database only."""
    conn = get_connection(isolated_discovery_db)
    # Remove any non-synthetic events added in previous tests, keeping synthetic seeds
    conn.execute("DELETE FROM events WHERE is_synthetic = 0;")
    conn.execute("DELETE FROM registration_audit_logs;")
    conn.execute("DELETE FROM registration_actions;")
    conn.commit()
    conn.close()

    def override_get_db():
        connection = get_connection(isolated_discovery_db)
        try:
            yield connection
        finally:
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

client = TestClient(app)

MOCK_DEVFOLIO_PAYLOAD = {
    "result": [
        {
            "uuid": "df-hack-001",
            "name": "Global Open Web Hackathon",
            "slug": "global-open-web",
            "starts_at": "2026-11-20T09:00:00.000Z",
            "ends_at": "2026-11-22T18:00:00.000Z",
            "hackathon_brand": "Open Web Collective",
            "location": "Online",
            "is_online": True,
            "themes": [{"name": "Web3"}, {"name": "AI/ML"}],
            "country": "Global",
            "hackathon_setting": {
                "reg_ends_at": "2026-11-19T23:59:00.000Z"
            }
        },
        {
            "uuid": "df-hack-002",
            "name": "Bangalore Cloud Challenge",
            "slug": "blr-cloud-2026",
            "starts_at": "2026-12-01T04:30:00.000Z",
            "ends_at": "2026-12-02T12:30:00.000Z",
            "hackathon_brand": "Bangalore Tech Forum",
            "location": "Bangalore, India",
            "is_online": False,
            "themes": [{"name": "Cloud"}],
            "country": "India",
            "hackathon_setting": {
                "reg_ends_at": "2026-11-29T23:59:00.000Z"
            }
        }
    ]
}

# -------------------------------------------------------------
# Stage 3 Tests: Safe Event Discovery and Provenance
# -------------------------------------------------------------

def test_devfolio_adapter_mocked_success(isolated_discovery_db):
    """Verify Devfolio adapter ingests permitted public events into normalized records."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_DEVFOLIO_PAYLOAD

    with patch("httpx.Client.get", return_value=mock_response):
        res = client.post("/api/events/refresh?source=devfolio")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["total_upserted"] == 2
        summary = data["sources_summary"][0]
        assert summary["source_name"] == "Devfolio"
        assert summary["status"] == "success"
        assert summary["events_fetched"] == 2

    # Verify events are accessible in GET /api/events with normalized fields
    res_events = client.get("/api/events?source=devfolio")
    assert res_events.status_code == 200
    events = res_events.json()["events"]
    assert len(events) == 2

    e1 = next(e for e in events if e["source_event_id"] == "df-hack-001")
    assert e1["title"] == "Global Open Web Hackathon"
    assert e1["source_url"] == "https://global-open-web.devfolio.co"
    assert e1["registration_url"] == "https://global-open-web.devfolio.co"
    assert e1["is_synthetic"] is False
    assert e1["data_source_type"] == "official_api"
    assert "IST" in e1["deadline_ist_formatted"]
    assert e1["fee_status"] == "free"

def test_event_normalization_invalid_source_urls():
    """Verify real events with missing or malformed URLs are strictly rejected."""
    # 1. Missing URL
    with pytest.raises(NormalizationError, match="Missing source URL"):
        validate_source_url(None, is_synthetic=False)

    # 2. Non-HTTP scheme
    with pytest.raises(NormalizationError, match="Invalid or malformed source URL"):
        validate_source_url("ftp://files.example.com/hackathon", is_synthetic=False)

    # 3. Malformed URL without domain
    with pytest.raises(NormalizationError, match="Invalid or malformed source URL"):
        validate_source_url("not_a_valid_url", is_synthetic=False)

    # 4. Valid HTTP/HTTPS passes
    assert validate_source_url("https://devfolio.co/hackathons/test", is_synthetic=False) == "https://devfolio.co/hackathons/test"

def test_timezone_conversion_non_guessing():
    """Verify naive timestamp with ambiguous/unrecognized timezone is rejected without guessing."""
    # Unrecognized timezone abbreviation
    with pytest.raises(NormalizationError, match="Ambiguous or unrecognized timezone"):
        convert_deadline_to_ist_safe("2026-11-15T23:59:00", timezone_name="XYZ_UNKNOWN")

    # Timezone naive without specified timezone
    with pytest.raises(NormalizationError, match="timezone-naive and no timezone was specified"):
        convert_deadline_to_ist_safe("2026-11-15T23:59:00", timezone_name=None)

    # Valid timezone offset converts accurately (+13:30 from PST UTC-8)
    iso_ist, formatted_ist, tz = convert_deadline_to_ist_safe("2026-11-15T23:59:00-08:00", timezone_name="PST")
    assert iso_ist == "2026-11-16T13:29:00+05:30"
    assert formatted_ist == "16 Nov 2026, 01:29 PM IST"

def test_expired_deadline_accuracy():
    """Verify expired deadlines are accurately flagged based on IST reference time."""
    past_deadline_ist = "2024-01-01T00:00:00+05:30"
    future_deadline_ist = "2029-01-01T00:00:00+05:30"

    assert is_deadline_expired(past_deadline_ist) is True
    assert is_deadline_expired(future_deadline_ist) is False

def test_missing_fee_marked_needs_verification():
    """Verify events with missing/unconfirmed fee status are marked 'Needs verification'."""
    raw = {
        "title": "Unconfirmed Registration Contest",
        "organizer": "Independent Org",
        "source_name": "Devfolio",
        "source_url": "https://example.devfolio.co",
        "deadline": "2026-11-30T23:59:00Z",
        "fee_status": "unknown",
        "fee_amount": None,
    }
    norm = normalize_raw_event(raw, is_synthetic=False)
    assert norm.fee_status == "unknown"
    assert norm.verification_status == "needs_verification"

def test_event_deduplication(isolated_discovery_db):
    """Verify repeated ingestion of same canonical event updates record rather than duplicating."""
    conn = get_connection(isolated_discovery_db)

    raw1 = {
        "title": "Idempotent Hackathon v1",
        "organizer": "Devfolio Org",
        "source_name": "Devfolio",
        "source_event_id": "df-dedup-01",
        "source_url": "https://dedup.devfolio.co",
        "deadline": "2026-11-25T18:00:00Z",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    norm1 = normalize_raw_event(raw1, is_synthetic=False)
    id1 = upsert_normalized_event(conn, norm1)
    conn.commit()

    # Second ingestion with updated title
    raw2 = {
        "title": "Idempotent Hackathon v2 (Updated)",
        "organizer": "Devfolio Org",
        "source_name": "Devfolio",
        "source_event_id": "df-dedup-01",
        "source_url": "https://dedup.devfolio.co",
        "deadline": "2026-11-25T18:00:00Z",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    norm2 = normalize_raw_event(raw2, is_synthetic=False)
    id2 = upsert_normalized_event(conn, norm2)
    conn.commit()

    assert id1 == id2

    # Check database count for this source event
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), title FROM events WHERE source_name = 'Devfolio' AND source_event_id = 'df-dedup-01';")
    count, title = cursor.fetchone()
    conn.close()

    assert count == 1
    assert title == "Idempotent Hackathon v2 (Updated)"

def test_unstop_adapter_safe_restriction():
    """Verify Unstop adapter safely reports access limitation and does not attempt unauthorized bypass."""
    res = client.post("/api/events/refresh?source=unstop")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "completed"
    assert data["total_upserted"] == 0

    summary = data["sources_summary"][0]
    assert summary["source_name"] == "Unstop"
    assert summary["status"] == "restricted"
    assert "Cloudflare" in summary["notes"] or "restricted" in summary["notes"]
    assert "disabled" in summary["error_message"]

def test_source_failure_graceful_handling():
    """Verify upstream source network failures are caught and reported without crashing the API."""
    mock_response = MagicMock()
    mock_response.status_code = 502
    mock_response.text = "Bad Gateway upstream"

    with patch("httpx.Client.get", return_value=mock_response):
        res = client.post("/api/events/refresh?source=devfolio")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["total_upserted"] == 0
        summary = data["sources_summary"][0]
        assert summary["status"] == "error"
        assert "502" in summary["error_message"]

def test_synthetic_and_real_event_separation(isolated_discovery_db):
    """Verify synthetic fixtures are clearly separated from real discovered events."""
    conn = get_connection(isolated_discovery_db)
    
    # Ingest one real event
    raw_real = {
        "title": "Real World AI Hackathon",
        "organizer": "Official Alliance",
        "source_name": "Devfolio",
        "source_event_id": "real-uuid-99",
        "source_url": "https://real-ai.devfolio.co",
        "deadline": "2026-11-28T23:59:00Z",
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    norm_real = normalize_raw_event(raw_real, is_synthetic=False)
    upsert_normalized_event(conn, norm_real)
    conn.commit()
    conn.close()

    # 1. Query only real events
    res_real_only = client.get("/api/events?include_synthetic=false")
    assert res_real_only.status_code == 200
    events_real = res_real_only.json()["events"]
    assert all(e["is_synthetic"] is False for e in events_real)
    assert any(e["title"] == "Real World AI Hackathon" for e in events_real)
    assert not any("[SYNTHETIC DEMO]" in e["title"] for e in events_real)

    # 2. Query both real and synthetic
    res_all = client.get("/api/events?include_synthetic=true")
    assert res_all.status_code == 200
    events_all = res_all.json()["events"]
    synthetic_count = sum(1 for e in events_all if e["is_synthetic"] is True)
    real_count = sum(1 for e in events_all if e["is_synthetic"] is False)
    assert synthetic_count > 0
    assert real_count > 0

def test_discovery_preserves_registration_workflow_safety(isolated_discovery_db):
    """Verify event discovery and refresh operations NEVER modify registration actions or audit trails."""
    conn = get_connection(isolated_discovery_db)
    
    # Check registration table is empty
    actions_before = conn.execute("SELECT COUNT(*) FROM registration_actions;").fetchone()[0]
    audit_before = conn.execute("SELECT COUNT(*) FROM registration_audit_logs;").fetchone()[0]
    conn.close()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_DEVFOLIO_PAYLOAD

    with patch("httpx.Client.get", return_value=mock_response):
        client.post("/api/events/refresh")

    conn = get_connection(isolated_discovery_db)
    actions_after = conn.execute("SELECT COUNT(*) FROM registration_actions;").fetchone()[0]
    audit_after = conn.execute("SELECT COUNT(*) FROM registration_audit_logs;").fetchone()[0]
    conn.close()

    assert actions_before == actions_after == 0
    assert audit_before == audit_after == 0

MOCK_MLH_HTML = """
<!DOCTYPE html>
<html>
<head>
    <script data-page="app" type="application/json">
    {
        "component": "SeasonEvents/Index",
        "props": {
            "upcomingEvents": [
                {
                    "id": "mlh-001",
                    "slug": "cal-hacks-13",
                    "name": "Cal Hacks 13.0",
                    "status": "pending",
                    "startsAt": "2026-10-23T17:00:00Z",
                    "endsAt": "2026-10-25T19:00:00Z",
                    "dateRange": "OCT 23 - 25",
                    "websiteUrl": "https://calhacks.io/",
                    "location": "San Francisco, California",
                    "formatType": "physical",
                    "region": "AMER",
                    "venueAddress": {
                        "city": "San Francisco",
                        "state": "California",
                        "country": "US"
                    }
                }
            ],
            "pastEvents": []
        }
    }
    </script>
</head>
<body></body>
</html>
"""

def test_mlh_adapter_inertia_parsing_and_deadline_non_inferral(isolated_discovery_db):
    """Verify MLH adapter parses Inertia schedule and strictly refuses to infer registration deadline from start date."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = MOCK_MLH_HTML

    with patch("httpx.Client.get", return_value=mock_response):
        res = client.post("/api/events/refresh?source=mlh")
        assert res.status_code == 200
        data = res.json()
        assert data["total_upserted"] == 1
        summary = data["sources_summary"][0]
        assert summary["source_name"] == "MLH"
        assert summary["status"] == "success"

    # Query the ingested MLH event
    res_events = client.get("/api/events?source=mlh")
    assert res_events.status_code == 200
    events = res_events.json()["events"]
    assert len(events) == 1
    ev = events[0]

    assert ev["title"] == "Cal Hacks 13.0"
    assert ev["source_name"] == "MLH"
    assert ev["source_url"] == "https://calhacks.io/"
    assert ev["format"] == "In-Person"
    assert ev["country"] == "United States"
    assert ev["start_date"] == "2026-10-23T17:00:00Z"
    # Registration deadline must NOT be inferred from start_date
    assert ev["deadline"] is None
    assert ev["deadline_status"] == "unavailable"
    assert ev["verification_status"] == "needs_verification"
    assert "Deadline Unavailable" in (ev["deadline_ist_formatted"] or "Deadline Unavailable")

def test_country_and_format_filtering(isolated_discovery_db):
    """Verify country and format filtering in GET /api/events operates on real event fields."""
    conn = get_connection(isolated_discovery_db)
    raw_india = {
        "title": "Delhi AI Hackathon 2026",
        "organizer": "Delhi Tech Society",
        "source_name": "Devfolio",
        "source_url": "https://delhi-ai.devfolio.co",
        "deadline": "2026-11-20T18:00:00Z",
        "country": "India",
        "region": "India",
        "format": "In-Person",
        "is_online": False,
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    raw_virtual = {
        "title": "Global CyberSprint Virtual",
        "organizer": "Cyber Alliance",
        "source_name": "Devfolio",
        "source_url": "https://cybersprint.devfolio.co",
        "deadline": "2026-11-25T18:00:00Z",
        "country": "Global",
        "region": "Global / Online",
        "format": "Online / Virtual",
        "is_online": True,
        "fee_status": "free",
        "fee_amount": 0.0,
    }
    upsert_normalized_event(conn, normalize_raw_event(raw_india, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_virtual, is_synthetic=False))
    conn.commit()
    conn.close()

    # Filter country=India
    res_india = client.get("/api/events?country=India&include_synthetic=false")
    assert res_india.status_code == 200
    events_india = res_india.json()["events"]
    assert any("Delhi AI Hackathon 2026" in e["title"] for e in events_india)
    assert not any("Global CyberSprint Virtual" in e["title"] for e in events_india)

    # Filter event_format=Online / Virtual
    res_virtual = client.get("/api/events?event_format=Online&include_synthetic=false")
    assert res_virtual.status_code == 200
    events_virtual = res_virtual.json()["events"]
    assert any("Global CyberSprint Virtual" in e["title"] for e in events_virtual)
    assert not any("Delhi AI Hackathon 2026" in e["title"] for e in events_virtual)

def test_filter_driven_live_source_discovery_with_metadata():
    """Verify that live_search=true triggers real source requests and returns rich discovery metadata."""
    res = client.get("/api/events?live_search=true&q=AI&include_synthetic=false")
    assert res.status_code == 200
    data = res.json()
    assert "discovery_metadata" in data
    meta = data["discovery_metadata"]
    assert meta["sources_searched"] >= 3
    sources = [s["source_name"].lower() for s in meta["sources_summary"]]
    assert "devfolio" in sources
    assert "mlh" in sources
    assert "unstop" in sources
    assert "devpost" in sources

    # Unstop must be reported truthfully as restricted
    unstop_s = next(s for s in meta["sources_summary"] if s["source_name"].lower() == "unstop")
    assert unstop_s["status"] == "restricted"
    assert "Cloudflare" in unstop_s["notes"] or "unstop.com/hackathons" in unstop_s["error_message"]

def test_devpost_adapter_parses_real_json():
    """Verify Devpost adapter parses valid hackathons JSON into NormalizedEventRecord."""
    from app.adapters.devpost import DevpostAdapter
    class MockDevpostClient:
        def get(self, *args, **kwargs):
            class Response:
                status_code = 200
                def json(self):
                    return {
                        "hackathons": [
                            {
                                "id": 40101,
                                "title": "Global Autonomous Agent Challenge",
                                "url": "https://agentchallenge.devpost.com/",
                                "organization_name": "Autonomous Labs",
                                "displayed_location": {"location": "Online", "icon": "globe"},
                                "submission_period_dates": "Oct 01 - Nov 30, 2026",
                                "themes": [{"name": "AI/ML"}, {"name": "Robotics"}],
                                "prize_amount": "$50,000",
                                "start_a_submission_url": "https://agentchallenge.devpost.com/challenges/start_a_submission"
                            }
                        ]
                    }
            return Response()

    adapter = DevpostAdapter()
    res = adapter.fetch_events(client=MockDevpostClient())
    assert res.status == "success"
    assert res.events_count == 1
    ev = res.events[0]
    assert ev.title == "Global Autonomous Agent Challenge"
    assert ev.source_event_id == "40101"
    assert ev.source_url == "https://agentchallenge.devpost.com/"
    assert ev.format == "Online / Virtual"
    assert ev.deadline_status == "unavailable"  # Safe: never guess naive deadline
    assert "AI/ML" in ev.tags

def test_partial_sync_status_reporting_and_metrics():
    """Verify that sync reports 'partial_success' when some sources succeed and Unstop is restricted."""
    import sqlite3
    from app.event_service import refresh_events_from_sources
    from app.database import init_db
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    class MockAllClient:
        def get(self, url, *args, **kwargs):
            class Response:
                def __init__(self, code, data=None, text=""):
                    self.status_code = code
                    self._data = data or {}
                    self.text = text
                def json(self):
                    return self._data
            if "devfolio" in str(url):
                return Response(200, {
                    "result": [{
                        "uuid": "df-101",
                        "slug": "test-devfolio",
                        "name": "Devfolio Hack Test",
                        "hackathon_setting": {"reg_ends_at": "2026-12-01T23:59:00Z"},
                        "is_online": True,
                        "desc": "Devfolio test hackathon"
                    }]
                })
            elif "devpost" in str(url):
                return Response(200, {
                    "hackathons": [{
                        "id": 90101,
                        "title": "Devpost Hack Test",
                        "url": "https://test.devpost.com",
                        "displayed_location": {"location": "Online"},
                        "themes": [{"name": "AI"}]
                    }]
                })
            elif "mlh" in str(url):
                return Response(200, text='<script data-page="app" type="application/json">{"props":{"upcomingEvents":[{"name":"MLH Hack Test","url":"https://mlh-test.com","location":"Online"}]}}</script>')
            elif "unstop" in str(url):
                return Response(403, text="Cloudflare bot challenge")
            return Response(404)

    # First sync: all fetched events are newly discovered / inserted
    rep1 = refresh_events_from_sources(conn, client=MockAllClient())
    assert rep1["status"] == "completed"
    assert rep1["sync_status"] == "partial_success"
    assert rep1["total_inserted"] == 3
    assert rep1["total_discovered"] == 3
    assert rep1["total_updated"] == 0
    assert rep1["total_fetched"] == 3

    # Check unstop status in summary
    unstop_res = next(s for s in rep1["sources_summary"] if s["source_name"].lower() == "unstop")
    assert unstop_res["status"] == "restricted"
    assert unstop_res["events_fetched"] == 0

    # Second sync with same events: must report 0 inserted, 3 updated, 0 duplicates created
    rep2 = refresh_events_from_sources(conn, client=MockAllClient())
    assert rep2["sync_status"] == "partial_success"
    assert rep2["total_inserted"] == 0
    assert rep2["total_discovered"] == 0
    assert rep2["total_updated"] == 3
    assert rep2["total_fetched"] == 3

    # Verify database has exactly 3 real rows, not 6
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM events WHERE is_synthetic = 0;")
    assert cur.fetchone()[0] == 3

def test_adapter_statuses_portal_urls_and_devpost_details():
    """Verify that get_adapter_statuses returns accurate official portal URLs and Devpost mechanism."""
    from app.event_service import get_adapter_statuses
    from app.database import init_db
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    statuses = get_adapter_statuses(conn)
    status_map = {s["source_name"].lower(): s for s in statuses}

    assert "devpost" in status_map
    assert status_map["devpost"]["portal_url"] == "https://devpost.com/hackathons"
    assert "api.devpost.com" in status_map["devpost"]["access_mechanism"] or "devpost.com/api" in status_map["devpost"]["access_mechanism"]
    assert status_map["devpost"]["display_name"] == "Devpost"

    assert "devfolio" in status_map
    assert status_map["devfolio"]["portal_url"] == "https://devfolio.co/hackathons"

    assert "mlh" in status_map
    assert status_map["mlh"]["portal_url"] == "https://mlh.io/events"

    assert "unstop" in status_map
    assert status_map["unstop"]["portal_url"] == "https://unstop.com/hackathons"

def test_upsert_deduplication_and_canonical_urls():
    """Verify upsert_normalized_event correctly handles trailing slashes and operation return types."""
    from app.event_service import upsert_normalized_event, UpsertResult
    from app.normalization import normalize_raw_event
    from app.database import init_db
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    raw1 = {
        "title": "Canonical Test Hackathon",
        "organizer": "Devpost Org",
        "source_name": "Devpost",
        "source_event_id": "7788",
        "source_url": "https://canonical-test.devpost.com/",
        "registration_url": "https://canonical-test.devpost.com/",
        "format": "Online / Virtual",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 4,
    }
    norm1 = normalize_raw_event(raw1, is_synthetic=False)
    res1 = upsert_normalized_event(conn, norm1)
    assert isinstance(res1, int)
    assert isinstance(res1, UpsertResult)
    assert res1.operation == "inserted"

    # Second upsert without trailing slash and matching source_event_id: must update, not insert
    raw2 = dict(raw1)
    raw2["source_url"] = "https://canonical-test.devpost.com"
    raw2["description"] = "Updated description"
    norm2 = normalize_raw_event(raw2, is_synthetic=False)
    res2 = upsert_normalized_event(conn, norm2)
    assert res2 == res1
    assert res2.operation == "updated"

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM events WHERE source_name = 'Devpost';")
    assert cur.fetchone()[0] == 1


def test_parse_date_range_string_and_is_date_in_past():
    """Verify robust parsing of various date range patterns and past-date evaluation."""
    from app.normalization import parse_date_range_string, is_date_in_past

    # 1. Date range formats
    s1, e1 = parse_date_range_string("Jun 19 - 22, 2024")
    assert s1 == "2024-06-19"
    assert e1 == "2024-06-22"

    s2, e2 = parse_date_range_string("Aug 31 - Oct 23, 2026")
    assert s2 == "2026-08-31"
    assert e2 == "2026-10-23"

    s3, e3 = parse_date_range_string("Sep 12, 2026")
    assert s3 == "2026-09-12"
    assert e3 == "2026-09-12"

    s4, e4 = parse_date_range_string("Dec 15, 2025 - Jan 15, 2026")
    assert s4 == "2025-12-15"
    assert e4 == "2026-01-15"

    assert parse_date_range_string(None) == (None, None)
    assert parse_date_range_string("Invalid date string") == (None, None)

    # 2. Past date checking
    assert is_date_in_past("2024-06-22") is True
    assert is_date_in_past("2020-01-01") is True
    assert is_date_in_past(None) is False
    assert is_date_in_past("2099-12-31") is False


def test_devpost_adapter_parses_open_state_and_submission_period_dates():
    """Verify DevpostAdapter correctly detects ended hackathons and extracts dates from official API response."""
    from app.adapters.devpost import DevpostAdapter
    import httpx

    fake_items = [
        {
            "id": 21687,
            "title": "Python Park-THE HACKATHON",
            "open_state": "ended",
            "time_left_to_submission": "Ended",
            "submission_period_dates": "Jun 19 - 22, 2024",
            "url": "https://python-park-the-hackathon.devpost.com/",
            "organization_name": "Compunnel Inc.",
            "displayed_location": {"location": "Compunnel, Inc. "},
            "themes": [{"name": "Databases"}],
        },
        {
            "id": 22000,
            "title": "Active Devpost Hackathon 2026",
            "open_state": "open",
            "time_left_to_submission": "15 days left",
            "submission_period_dates": "Oct 15 - Nov 15, 2026",
            "url": "https://active-2026.devpost.com/",
            "organization_name": "Active Org",
            "displayed_location": {"location": "Online"},
            "themes": [{"name": "AI"}],
        }
    ]

    def mock_handler(request: httpx.Request):
        return httpx.Response(200, json={"hackathons": fake_items})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    adapter = DevpostAdapter()
    result = adapter.fetch_events(limit=5, client=client)

    assert result.status == "success"
    assert len(result.events) == 2

    # Ended event checks
    ended_ev = result.events[0]
    assert ended_ev.title == "Python Park-THE HACKATHON"
    assert ended_ev.deadline_status == "closed"
    assert ended_ev.is_deadline_expired is True
    assert ended_ev.start_date == "2024-06-19"
    assert ended_ev.end_date == "2024-06-22"
    assert "Ended" in (ended_ev.deadline_notes or "")

    # Active event checks
    active_ev = result.events[1]
    assert active_ev.title == "Active Devpost Hackathon 2026"
    assert active_ev.deadline_status == "unavailable"
    assert active_ev.is_deadline_expired is False
    assert active_ev.start_date == "2026-10-15"
    assert active_ev.end_date == "2026-11-15"


def test_unknown_registration_cutoff_yields_needs_verification_not_eligible():
    """Verify that events with unlisted/unavailable registration cutoffs NEVER return Eligible."""
    from app.utils import calculate_eligibility

    # Solo student, fee free, team min 1, max 4, BUT deadline cutoff is unavailable
    result = calculate_eligibility(
        team_min=1,
        team_max=4,
        fee_status="free",
        fee_amount=0.0,
        team_size=1,
        deadline_status="unavailable",
        verification_status="verified",
    )
    assert result["status"] == "Needs verification"
    assert any("Registration cutoff is unlisted" in r for r in result["reasons"])

    # If verification_status is needs_verification, also yields Needs verification
    result_unverified = calculate_eligibility(
        team_min=1,
        team_max=4,
        fee_status="free",
        fee_amount=0.0,
        team_size=1,
        deadline_status="verified",
        verification_status="needs_verification",
    )
    assert result_unverified["status"] == "Needs verification"
    assert any("require verification" in r for r in result_unverified["reasons"])


def test_ended_event_yields_not_eligible():
    """Verify that closed/ended events yield 'Not eligible' even if team size and fee are compatible."""
    from app.utils import calculate_eligibility

    # Event ended on 2024-06-22
    result = calculate_eligibility(
        team_min=1,
        team_max=5,
        fee_status="free",
        fee_amount=0.0,
        team_size=1,
        deadline_status="closed",
        is_deadline_expired=True,
        event_end_date="2024-06-22",
    )
    assert result["status"] == "Not eligible"
    assert any("closed or the event has ended" in r for r in result["reasons"])


def test_expired_and_ended_events_excluded_from_upcoming_and_marked_closed(isolated_discovery_db):
    """Verify GET /api/events with status filter distinguishes upcoming from closed events."""
    from app.database import get_connection
    from app.normalization import normalize_raw_event
    from app.event_service import upsert_normalized_event

    conn = get_connection(isolated_discovery_db)
    raw_active = {
        "title": "Upcoming Active Hackathon 2026",
        "organizer": "Devpost Community",
        "source_name": "Devpost",
        "source_url": "https://active2026.devpost.com",
        "start_date": "2026-11-01",
        "end_date": "2026-11-05",
        "deadline": "2026-10-31T23:59:00Z",
        "deadline_status": "verified",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 4,
    }
    raw_ended = {
        "title": "Python Park-THE HACKATHON",
        "organizer": "Compunnel Inc.",
        "source_name": "Devpost",
        "source_url": "https://python-park-the-hackathon.devpost.com/",
        "start_date": "2024-06-19",
        "end_date": "2024-06-22",
        "deadline_status": "closed",
        "deadline_notes": "Official Devpost status: Ended. Submission period was Jun 19 - 22, 2024.",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 5,
    }
    upsert_normalized_event(conn, normalize_raw_event(raw_active, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_ended, is_synthetic=False))
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    from app.main import app
    test_client = TestClient(app)

    # 1. status=upcoming must include active and exclude Python Park (which ended in 2024)
    res_upcoming = test_client.get("/api/events?status=upcoming&include_synthetic=false")
    assert res_upcoming.status_code == 200
    upcoming_events = res_upcoming.json()["events"]
    assert any("Upcoming Active Hackathon 2026" in e["title"] for e in upcoming_events)
    assert not any("Python Park" in e["title"] for e in upcoming_events)
    assert all(e["deadline_status"] != "closed" and not e["is_deadline_expired"] for e in upcoming_events)

    # 2. status=closed must include Python Park and mark it closed
    res_closed = test_client.get("/api/events?status=closed&include_synthetic=false")
    assert res_closed.status_code == 200
    closed_events = res_closed.json()["events"]
    python_park = next((e for e in closed_events if "Python Park" in e["title"]), None)
    assert python_park is not None
    assert python_park["deadline_status"] == "closed"
    assert python_park["is_deadline_expired"] is True
    assert python_park["eligibility"]["status"] == "Not eligible"

    # 3. Direct eligibility check on Python Park via /api/eligibility/check
    res_check = test_client.post("/api/eligibility/check", json={"event_id": python_park["id"], "team_size": 1})
    assert res_check.status_code == 200
    check_data = res_check.json()
    assert check_data["status"] == "Not eligible"
    assert any("closed or the event has ended" in r for r in check_data["reasons"])


def test_the_python_coders_and_python_park_regression(isolated_discovery_db):
    """
    MASTER REGRESSION TEST FOR PROBLEM 1:
    Verifies that observed old hackathons:
    - 'The python coders' (Dec 10-20, 2020)
    - 'Python Park-THE HACKATHON' (Jun 19-22, 2024)
    are excluded from default 'Upcoming & Open' view,
    accessible under 'status=closed' or 'status=all',
    evaluated as 'Not eligible',
    and events with unknown cutoff produce 'Needs verification'.
    """
    from app.database import get_connection, _backfill_historical_and_ended_events
    from app.event_service import upsert_normalized_event
    from app.normalization import normalize_raw_event

    conn = get_connection(isolated_discovery_db)

    # Insert 'The python coders' (2020)
    raw_coders = {
        "title": "The python coders",
        "organizer": "Devpost Community Organizer",
        "source_name": "Devpost",
        "source_event_id": "the-python-coders-2020",
        "source_url": "https://the-python-coders.devpost.com/",
        "start_date": "2020-12-10",
        "end_date": "2020-12-20",
        "deadline_status": "closed",
        "deadline_notes": "Official Devpost status: Ended. Submission period was Dec 10 - 20, 2020.",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 4,
    }
    # Insert 'Python Park-THE HACKATHON' (2024)
    raw_park = {
        "title": "Python Park-THE HACKATHON",
        "organizer": "Compunnel Inc.",
        "source_name": "Devpost",
        "source_event_id": "python-park-2024",
        "source_url": "https://python-park-the-hackathon.devpost.com/",
        "start_date": "2024-06-19",
        "end_date": "2024-06-22",
        "deadline_status": "closed",
        "deadline_notes": "Official Devpost status: Ended. Submission period was Jun 19 - 22, 2024.",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 5,
    }
    # Insert active upcoming event (2026)
    raw_open = {
        "title": "Open Python AI Challenge 2026",
        "organizer": "Global AI Lab",
        "source_name": "Devpost",
        "source_event_id": "open-python-ai-2026",
        "source_url": "https://open-python-ai-2026.devpost.com/",
        "start_date": "2026-11-15",
        "end_date": "2026-11-20",
        "deadline": "2026-11-10T23:59:00Z",
        "deadline_status": "verified",
        "fee_status": "free",
        "team_min": 1,
        "team_max": 4,
    }
    # Insert event with unknown registration cutoff
    raw_unlisted = {
        "title": "Future Quantum Hackathon 2026",
        "organizer": "Quantum League",
        "source_name": "Devpost",
        "source_event_id": "future-quantum-2026",
        "source_url": "https://future-quantum-2026.devpost.com/",
        "start_date": "2026-12-01",
        "end_date": "2026-12-05",
        "deadline": "",
        "deadline_status": "unavailable",
        "deadline_notes": "Official cutoff timestamp unlisted.",
        "fee_status": "unknown",
        "team_min": 1,
        "team_max": 4,
    }

    upsert_normalized_event(conn, normalize_raw_event(raw_coders, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_park, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_open, is_synthetic=False))
    upsert_normalized_event(conn, normalize_raw_event(raw_unlisted, is_synthetic=False))
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    # 1. Default GET /api/events (WITHOUT status query param) MUST default to upcoming and exclude 2020 and 2024 events
    res_default = client.get("/api/events?include_synthetic=false")
    assert res_default.status_code == 200
    events_default = res_default.json()["events"]
    titles_default = [e["title"] for e in events_default]
    assert "Open Python AI Challenge 2026" in titles_default
    assert "The python coders" not in titles_default
    assert "Python Park-THE HACKATHON" not in titles_default

    # 2. GET /api/events?status=closed MUST return both ended events
    res_closed = client.get("/api/events?status=closed&include_synthetic=false")
    assert res_closed.status_code == 200
    events_closed = res_closed.json()["events"]
    titles_closed = [e["title"] for e in events_closed]
    assert "The python coders" in titles_closed
    assert "Python Park-THE HACKATHON" in titles_closed
    assert "Open Python AI Challenge 2026" not in titles_closed

    # Verify ended event details
    coders_ev = next(e for e in events_closed if e["title"] == "The python coders")
    assert coders_ev["deadline_status"] == "closed"
    assert coders_ev["is_deadline_expired"] is True
    assert coders_ev["eligibility"]["status"] == "Not eligible"
    assert any("closed or the event has ended" in r for r in coders_ev["eligibility"]["reasons"])

    park_ev = next(e for e in events_closed if e["title"] == "Python Park-THE HACKATHON")
    assert park_ev["deadline_status"] == "closed"
    assert park_ev["is_deadline_expired"] is True
    assert park_ev["eligibility"]["status"] == "Not eligible"

    # 3. GET /api/events?status=all MUST return active and closed events
    res_all = client.get("/api/events?status=all&include_synthetic=false")
    assert res_all.status_code == 200
    events_all = res_all.json()["events"]
    titles_all = [e["title"] for e in events_all]
    assert "Open Python AI Challenge 2026" in titles_all
    assert "The python coders" in titles_all
    assert "Python Park-THE HACKATHON" in titles_all
    assert "Future Quantum Hackathon 2026" in titles_all

    # 4. Unknown cutoff produces Needs verification
    quantum_ev = next(e for e in events_all if e["title"] == "Future Quantum Hackathon 2026")
    assert quantum_ev["eligibility"]["status"] == "Needs verification"


def test_devpost_adapter_filter_routing_and_default_open():
    """
    Verifies that DevpostAdapter:
    1. Defaults status[] to 'open' when status is unspecified or 'upcoming'
    2. Sends status[]='ended' when status is 'closed'
    3. Omits status[] when status is 'all'
    4. Routes search criteria and skills to 'search' parameter
    5. Routes online event format to challenge_type[]=online
    """
    from app.adapters.devpost import DevpostAdapter

    adapter = DevpostAdapter()

    # Case 1: Default criteria (no status specified) -> sends status[]='open'
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hackathons": []}
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = adapter.fetch_events(limit=10, criteria={"skills": ["Python"], "event_format": "Online / Virtual"})
        assert res.status == "success"
        call_args, call_kwargs = mock_client.get.call_args
        params = call_kwargs["params"]
        assert params.get("status[]") == "open"
        assert params.get("search") == "Python"
        assert params.get("challenge_type[]") == "online"

    # Case 2: Explicit closed/ended criteria -> sends status[]='ended'
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hackathons": []}
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = adapter.fetch_events(limit=10, criteria={"status": "closed", "query": "AI"})
        assert res.status == "success"
        call_args, call_kwargs = mock_client.get.call_args
        params = call_kwargs["params"]
        assert params.get("status[]") == "ended"
        assert params.get("search") == "AI"

    # Case 3: status='all' -> does not restrict status[]
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hackathons": []}
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value.__enter__.return_value = mock_client

        res = adapter.fetch_events(limit=10, criteria={"status": "all"})
        assert res.status == "success"
        call_args, call_kwargs = mock_client.get.call_args
        params = call_kwargs["params"]
        assert "status[]" not in params

def test_devpost_deadline_resolution_from_public_page():
    """Verify that DevpostAdapter resolves verified deadline when official public page has a <time> tag."""
    from app.adapters.devpost import DevpostAdapter, DEVPOST_PAGE_DEADLINE_CACHE
    import httpx

    # Clear cache for isolated test
    DEVPOST_PAGE_DEADLINE_CACHE.clear()

    fake_api_json = {
        "hackathons": [
            {
                "id": 99901,
                "title": "Amazon Developer Hackathon",
                "url": "https://amazonappdev2026.devpost.com/",
                "organization_name": "Amazon",
                "displayed_location": {"location": "Online"},
                "submission_period_dates": "Aug 31 - Oct 23, 2026",
                "open_state": "open",
                "time_left_to_submission": "3 days left",
            }
        ]
    }

    page_html = """
    <html>
      <body>
        <div class="deadline">
          <time datetime="2026-10-23T15:00:00-04:00">October 23 at 3:00pm EDT</time>
        </div>
      </body>
    </html>
    """

    def mock_handler(request: httpx.Request):
        if "api/hackathons" in str(request.url):
            return httpx.Response(200, json=fake_api_json)
        elif "amazonappdev2026.devpost.com" in str(request.url):
            return httpx.Response(200, text=page_html)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    adapter = DevpostAdapter()
    result = adapter.fetch_events(limit=5, client=client)

    assert result.status == "success"
    assert len(result.events) == 1
    ev = result.events[0]
    assert ev.deadline_status == "verified"
    assert ev.deadline == "2026-10-23T15:00:00-04:00"
    assert ev.deadline_ist_formatted == "24 Oct 2026, 12:30 AM IST"
    assert "October 23 at 3:00pm EDT" in (ev.deadline_notes or "")

def test_unstop_refresh_returns_restricted_overall_status():
    """Verify that refreshing only Unstop reports sync_status='restricted' rather than 'error'."""
    import sqlite3
    from app.event_service import refresh_events_from_sources
    from app.database import init_db

    conn = sqlite3.connect(":memory:")
    init_db(conn)

    report = refresh_events_from_sources(conn, source_name="unstop")
    assert report["status"] == "completed"
    assert report["sync_status"] == "restricted"
    assert report["overall_status"] == "restricted"
    assert len(report["sources_summary"]) == 1
    assert report["sources_summary"][0]["status"] == "restricted"
    conn.close()

def test_adapter_exception_isolation_during_refresh():
    """Verify that an unexpected exception in one adapter does not crash the overall sync."""
    import sqlite3
    from unittest.mock import patch, MagicMock
    from app.event_service import refresh_events_from_sources
    from app.database import init_db

    conn = sqlite3.connect(":memory:")
    init_db(conn)

    failing_adapter = MagicMock()
    failing_adapter.source_name = "FaultySource"
    failing_adapter.fetch_events.side_effect = RuntimeError("Simulated network socket reset")
    failing_adapter.get_limitations.return_value = "Faulty source limitation"

    with patch("app.event_service.get_all_adapters", return_value=[failing_adapter]):
        report = refresh_events_from_sources(conn, source_name="all")
        assert report["status"] == "completed"
        assert report["sync_status"] == "error"
        assert len(report["sources_summary"]) == 1
        src = report["sources_summary"][0]
        assert src["status"] == "error"
        assert "Simulated network socket reset" in (src["error_message"] or "")

    conn.close()





