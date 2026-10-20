import sqlite3
from app.database import get_connection, init_db

DEMO_EVENTS = [
    {
        "title": "[SYNTHETIC DEMO] Global AI Systems Hackathon 2026",
        "description": "Synthetic demo event for prototyping multi-agent AI tools. All teams build automated research agents in this 48-hour online hackathon.",
        "organizer": "Synthetic Hackathon Alliance",
        "source_url": "https://demo-fixtures.local/events/global-ai-hackathon-2026",
        "retrieved_at": "2026-10-15T12:00:00Z",
        "team_min": 2,
        "team_max": 4,
        "fee_amount": 0.0,
        "fee_currency": "USD",
        "fee_status": "free",
        "deadline": "2026-11-15T23:59:00-08:00",
        "timezone": "America/Los_Angeles",
        "data_source_type": "synthetic_demo_fixture",
        "tags": "Python, AI/ML, FastApi, React",
        "region": "Global / Online",
        "format": "Online / Virtual"
    },
    {
        "title": "[SYNTHETIC DEMO] Collegiate CodeSprint Cup",
        "description": "Synthetic individual algorithmic tournament fixture. Fee status is currently unverified on upstream portal mock.",
        "organizer": "Demo University Tech Council",
        "source_url": "https://demo-fixtures.local/events/collegiate-codesprint",
        "retrieved_at": "2026-10-16T08:30:00Z",
        "team_min": 1,
        "team_max": 1,
        "fee_amount": None,
        "fee_currency": "USD",
        "fee_status": "unknown",
        "deadline": "2026-11-20T18:00:00-05:00",
        "timezone": "America/New_York",
        "data_source_type": "synthetic_demo_fixture",
        "tags": "Algorithms, TypeScript, C++, Python",
        "region": "North America",
        "format": "Online / Virtual"
    },
    {
        "title": "[SYNTHETIC DEMO] India Cloud & DevOps Championship",
        "description": "Synthetic demo fixture focused on cloud infrastructure, container orchestration, and serverless reliability engineering.",
        "organizer": "Mock Cloud Foundation India",
        "source_url": "https://demo-fixtures.local/events/india-cloud-championship",
        "retrieved_at": "2026-10-16T14:15:00Z",
        "team_min": 1,
        "team_max": 3,
        "fee_amount": 0.0,
        "fee_currency": "INR",
        "fee_status": "free",
        "deadline": "2026-11-30T23:59:00+05:30",
        "timezone": "Asia/Kolkata",
        "data_source_type": "synthetic_demo_fixture",
        "tags": "Cloud, Docker, Kubernetes, Python",
        "region": "India",
        "format": "Hybrid"
    },
    {
        "title": "[SYNTHETIC DEMO] Premium Web3 Innovation Summit",
        "description": "Synthetic demo fixture modeling a paid entry registration hackathon with industry mentoring tracks.",
        "organizer": "Demo Blockchain Guild",
        "source_url": "https://demo-fixtures.local/events/web3-innovation-summit",
        "retrieved_at": "2026-10-17T04:00:00Z",
        "team_min": 3,
        "team_max": 5,
        "fee_amount": 50.0,
        "fee_currency": "USD",
        "fee_status": "paid",
        "deadline": "2026-12-05T20:00:00-08:00",
        "timezone": "America/Los_Angeles",
        "data_source_type": "synthetic_demo_fixture",
        "tags": "Web3, Solidity, React, TypeScript",
        "region": "Global / Online",
        "format": "Online / Virtual"
    },
    {
        "title": "[SYNTHETIC DEMO] Open HealthTech Hackathon",
        "description": "Synthetic demo fixture exploring predictive clinical informatics and accessible patient telemetry web apps.",
        "organizer": "Synthetic BioTech Collective",
        "source_url": "https://demo-fixtures.local/events/open-healthtech-2026",
        "retrieved_at": "2026-10-17T06:00:00Z",
        "team_min": 2,
        "team_max": 6,
        "fee_amount": 15.0,
        "fee_currency": "USD",
        "fee_status": "paid",
        "deadline": "2026-12-12T17:00:00Z",
        "timezone": "UTC",
        "data_source_type": "synthetic_demo_fixture",
        "tags": "HealthTech, React, Python, Data Science",
        "region": "Europe / Remote",
        "format": "Online / Virtual"
    }
]

def seed_database(conn: sqlite3.Connection | None = None) -> None:
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    init_db(conn)
    cursor = conn.cursor()
    
    # Check if records already exist
    cursor.execute("SELECT COUNT(*) FROM events")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.executemany("""
        INSERT INTO events (
            title, description, organizer, source_url, retrieved_at,
            team_min, team_max, fee_amount, fee_currency, fee_status,
            deadline, timezone, data_source_type, tags, region, format
        ) VALUES (
            :title, :description, :organizer, :source_url, :retrieved_at,
            :team_min, :team_max, :fee_amount, :fee_currency, :fee_status,
            :deadline, :timezone, :data_source_type, :tags, :region, :format
        );
        """, DEMO_EVENTS)
        conn.commit()

    if close_after:
        conn.close()

if __name__ == "__main__":
    seed_database()
    print("Database initialized and synthetic demo events seeded successfully.")
