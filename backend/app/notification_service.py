import datetime
import sqlite3
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo
from app.normalization import IST_ZONE, is_deadline_expired, convert_deadline_to_ist_safe
from app.schemas import (
    NotificationPreferencesPayload,
    NotificationPreferencesResponse,
    NotificationItemResponse,
    NotificationListResponse,
    DeadlineGroupItem,
    DeadlineSummaryResponse,
)

def get_notification_preferences(conn: sqlite3.Connection, user_email: str = "student@ziro.local") -> NotificationPreferencesResponse:
    """Retrieves persisted notification preferences for the user, returning defaults if not yet saved."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT user_email, matching_events_enabled, upcoming_deadlines_enabled, deadline_changes_enabled,
           master_reminders_enabled, remind_7_days, remind_48_hours, remind_24_hours,
           browser_notifications_enabled, updated_at
    FROM notification_preferences
    WHERE LOWER(user_email) = LOWER(?)
    LIMIT 1;
    """, (user_email,))
    row = cursor.fetchone()

    if not row:
        return NotificationPreferencesResponse(
            user_email=user_email,
            matching_events_enabled=True,
            upcoming_deadlines_enabled=True,
            deadline_changes_enabled=True,
            master_reminders_enabled=True,
            remind_7_days=True,
            remind_48_hours=True,
            remind_24_hours=True,
            browser_notifications_enabled=False,
            updated_at=None,
        )

    return NotificationPreferencesResponse(
        user_email=row["user_email"],
        matching_events_enabled=bool(row["matching_events_enabled"]),
        upcoming_deadlines_enabled=bool(row["upcoming_deadlines_enabled"]),
        deadline_changes_enabled=bool(row["deadline_changes_enabled"]),
        master_reminders_enabled=bool(row["master_reminders_enabled"]),
        remind_7_days=bool(row["remind_7_days"]),
        remind_48_hours=bool(row["remind_48_hours"]),
        remind_24_hours=bool(row["remind_24_hours"]),
        browser_notifications_enabled=bool(row["browser_notifications_enabled"]),
        updated_at=row["updated_at"],
    )

def save_notification_preferences(
    conn: sqlite3.Connection,
    user_email: str,
    payload: NotificationPreferencesPayload
) -> NotificationPreferencesResponse:
    """Upserts notification and deadline reminder preferences for the user."""
    cursor = conn.cursor()
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cursor.execute("""
    INSERT INTO notification_preferences (
        user_email, matching_events_enabled, upcoming_deadlines_enabled, deadline_changes_enabled,
        master_reminders_enabled, remind_7_days, remind_48_hours, remind_24_hours,
        browser_notifications_enabled, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_email) DO UPDATE SET
        matching_events_enabled = excluded.matching_events_enabled,
        upcoming_deadlines_enabled = excluded.upcoming_deadlines_enabled,
        deadline_changes_enabled = excluded.deadline_changes_enabled,
        master_reminders_enabled = excluded.master_reminders_enabled,
        remind_7_days = excluded.remind_7_days,
        remind_48_hours = excluded.remind_48_hours,
        remind_24_hours = excluded.remind_24_hours,
        browser_notifications_enabled = excluded.browser_notifications_enabled,
        updated_at = excluded.updated_at;
    """, (
        user_email.strip().lower(),
        1 if payload.matching_events_enabled else 0,
        1 if payload.upcoming_deadlines_enabled else 0,
        1 if payload.deadline_changes_enabled else 0,
        1 if payload.master_reminders_enabled else 0,
        1 if payload.remind_7_days else 0,
        1 if payload.remind_48_hours else 0,
        1 if payload.remind_24_hours else 0,
        1 if payload.browser_notifications_enabled else 0,
        now_utc,
    ))
    conn.commit()

    return get_notification_preferences(conn, user_email)

def get_user_notifications(
    conn: sqlite3.Connection,
    user_email: str = "student@ziro.local",
    limit: int = 50
) -> NotificationListResponse:
    """Retrieves chronological in-app notifications for the user with unread count."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, user_email, event_id, category, reminder_interval, title, message,
           event_title, deadline_ist, deadline_formatted, remaining_time, official_url,
           source_name, is_read, created_at
    FROM notifications
    WHERE LOWER(user_email) = LOWER(?)
    ORDER BY id DESC
    LIMIT ?;
    """, (user_email, limit))
    rows = cursor.fetchall()

    cursor.execute("""
    SELECT COUNT(*) FROM notifications
    WHERE LOWER(user_email) = LOWER(?) AND is_read = 0;
    """, (user_email,))
    unread_count = cursor.fetchone()[0]

    notifications = [
        NotificationItemResponse(
            id=r["id"],
            user_email=r["user_email"],
            event_id=r["event_id"],
            category=r["category"],
            reminder_interval=r["reminder_interval"],
            title=r["title"],
            message=r["message"],
            event_title=r["event_title"],
            deadline_ist=r["deadline_ist"],
            deadline_formatted=r["deadline_formatted"],
            remaining_time=r["remaining_time"],
            official_url=r["official_url"],
            source_name=r["source_name"],
            is_read=bool(r["is_read"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]

    return NotificationListResponse(
        unread_count=unread_count,
        total_count=len(notifications),
        notifications=notifications,
    )

def mark_notification_read(conn: sqlite3.Connection, notification_id: int, user_email: str = "student@ziro.local") -> bool:
    """Marks a single notification as read."""
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE notifications
    SET is_read = 1
    WHERE id = ? AND LOWER(user_email) = LOWER(?);
    """, (notification_id, user_email))
    conn.commit()
    return cursor.rowcount > 0

def mark_all_notifications_read(conn: sqlite3.Connection, user_email: str = "student@ziro.local") -> int:
    """Marks all notifications for the user as read."""
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE notifications
    SET is_read = 1
    WHERE LOWER(user_email) = LOWER(?);
    """, (user_email,))
    conn.commit()
    return cursor.rowcount

def calculate_deadline_group(
    deadline_ist_str: Optional[str],
    verification_status: str = "verified",
    reference_time_utc: Optional[datetime.datetime] = None
) -> Tuple[str, Optional[int], Optional[int], bool]:
    """
    Categorizes a deadline into groups:
    - 'Needs Verification'
    - 'Deadline Passed'
    - 'Due Today'
    - 'Due Tomorrow'
    - 'Due in the Next 7 Days'
    - 'Later'
    
    Returns: (group_name, remaining_days, remaining_hours, is_expired)
    """
    if not deadline_ist_str or verification_status.lower() == "needs_verification":
        return "Needs Verification", None, None, False

    now_ist = (reference_time_utc or datetime.datetime.now(datetime.timezone.utc)).astimezone(IST_ZONE)

    try:
        dt_deadline = datetime.datetime.fromisoformat(deadline_ist_str)
        if dt_deadline.tzinfo is None:
            dt_deadline = dt_deadline.replace(tzinfo=IST_ZONE)
        else:
            dt_deadline = dt_deadline.astimezone(IST_ZONE)
    except Exception:
        return "Needs Verification", None, None, False

    delta = dt_deadline - now_ist
    total_seconds = delta.total_seconds()

    if total_seconds < 0:
        return "Deadline Passed", 0, 0, True

    total_hours = int(total_seconds // 3600)
    days_diff = (dt_deadline.date() - now_ist.date()).days

    if days_diff == 0:
        group = "Due Today"
    elif days_diff == 1:
        group = "Due Tomorrow"
    elif days_diff <= 7:
        group = "Due in the Next 7 Days"
    else:
        group = "Later"

    return group, days_diff, total_hours, False

def get_deadline_groups(
    conn: sqlite3.Connection,
    reference_time_utc: Optional[datetime.datetime] = None
) -> DeadlineSummaryResponse:
    """Computes deadline groups for all active events."""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, title, organizer, source_name, source_url, registration_url,
           deadline, timezone, verification_status, is_synthetic
    FROM events
    WHERE is_synthetic = 0
    ORDER BY id ASC;
    """)
    rows = cursor.fetchall()

    groups: Dict[str, List[DeadlineGroupItem]] = {
        "Due Today": [],
        "Due Tomorrow": [],
        "Due in the Next 7 Days": [],
        "Later": [],
        "Deadline Passed": [],
        "Needs Verification": [],
    }

    for r in rows:
        try:
            deadline_ist, formatted_ist, _ = convert_deadline_to_ist_safe(r["deadline"], timezone_name=r["timezone"])
        except Exception:
            deadline_ist = r["deadline"]
            formatted_ist = r["deadline"]

        group, remaining_days, remaining_hours, is_expired = calculate_deadline_group(
            deadline_ist,
            verification_status=r["verification_status"],
            reference_time_utc=reference_time_utc
        )

        item = DeadlineGroupItem(
            event_id=r["id"],
            title=r["title"],
            organizer=r["organizer"],
            source_name=r["source_name"],
            source_url=r["source_url"],
            registration_url=r["registration_url"] or r["source_url"],
            deadline_ist=deadline_ist,
            deadline_ist_formatted=formatted_ist,
            deadline_group=group,
            remaining_days=remaining_days,
            remaining_hours=remaining_hours,
            is_deadline_expired=is_expired,
            verification_status=r["verification_status"],
        )

        if group in groups:
            groups[group].append(item)
        else:
            groups["Later"].append(item)

    counts = {k: len(v) for k, v in groups.items()}
    return DeadlineSummaryResponse(groups=groups, counts=counts)

def evaluate_and_generate_notifications(
    conn: sqlite3.Connection,
    user_email: str = "student@ziro.local",
    reference_time_utc: Optional[datetime.datetime] = None
) -> int:
    """
    Evaluates upcoming deadlines, verified deadline changes, and matching events against user preferences.
    Generates notification items without duplicates using unique dedup keys.
    Excludes synthetic fixtures and only alerts on genuine matching skills.
    Returns the count of newly inserted notifications.
    """
    prefs = get_notification_preferences(conn, user_email)
    now_ist = (reference_time_utc or datetime.datetime.now(datetime.timezone.utc)).astimezone(IST_ZONE)
    now_utc_iso = (reference_time_utc or datetime.datetime.now(datetime.timezone.utc)).isoformat()

    cursor = conn.cursor()
    # Fetch real events only
    cursor.execute("""
    SELECT id, title, organizer, source_name, source_url, registration_url,
           deadline, timezone, verification_status, deadline_status, tags, retrieved_at, is_synthetic
    FROM events
    WHERE verification_status != 'unverified' AND is_synthetic = 0;
    """)
    events = cursor.fetchall()

    newly_inserted = 0

    # 1. Evaluate Deadline Reminders (strictly verified registration cutoffs only)
    if prefs.master_reminders_enabled and prefs.upcoming_deadlines_enabled:
        for ev in events:
            # Strictly exclude missing, unknown, inferred, or unverified registration deadlines
            if ev["deadline_status"] != "verified" or not ev["deadline"] or not str(ev["deadline"]).strip():
                continue

            try:
                deadline_ist, formatted_ist, _ = convert_deadline_to_ist_safe(ev["deadline"], timezone_name=ev["timezone"])
            except Exception:
                continue

            # Skip expired
            if is_deadline_expired(deadline_ist, reference_time_utc=reference_time_utc):
                continue

            dt_deadline = datetime.datetime.fromisoformat(deadline_ist)
            if dt_deadline.tzinfo is None:
                dt_deadline = dt_deadline.replace(tzinfo=IST_ZONE)
            else:
                dt_deadline = dt_deadline.astimezone(IST_ZONE)

            delta = dt_deadline - now_ist
            total_hours = delta.total_seconds() / 3600.0

            # 7-day interval: within 168h and > 48h
            if prefs.remind_7_days and 48.0 < total_hours <= 168.0:
                days_left = int(total_hours // 24)
                dedup_key = f"{user_email}:{ev['id']}:7d:{deadline_ist}"
                title = f"7-Day Deadline Reminder: {ev['title']}"
                message = f"Registration closes in {days_left} days. Deadline: {formatted_ist}. Check official registration page."
                inserted = _insert_notification_if_absent(
                    conn,
                    user_email=user_email,
                    event_id=ev["id"],
                    category="deadline_reminder",
                    reminder_interval="7d",
                    title=title,
                    message=message,
                    event_title=ev["title"],
                    deadline_ist=deadline_ist,
                    deadline_formatted=formatted_ist,
                    remaining_time=f"{days_left} days remaining",
                    official_url=ev["registration_url"] or ev["source_url"],
                    source_name=ev["source_name"],
                    created_at=now_utc_iso,
                    dedup_key=dedup_key,
                )
                if inserted:
                    newly_inserted += 1

            # 48-hour interval: within 48h and > 24h
            if prefs.remind_48_hours and 24.0 < total_hours <= 48.0:
                hours_left = int(total_hours)
                dedup_key = f"{user_email}:{ev['id']}:48h:{deadline_ist}"
                title = f"48-Hour Urgent Reminder: {ev['title']}"
                message = f"Registration closes in {hours_left} hours ({formatted_ist}). Complete registration before deadline."
                inserted = _insert_notification_if_absent(
                    conn,
                    user_email=user_email,
                    event_id=ev["id"],
                    category="deadline_reminder",
                    reminder_interval="48h",
                    title=title,
                    message=message,
                    event_title=ev["title"],
                    deadline_ist=deadline_ist,
                    deadline_formatted=formatted_ist,
                    remaining_time=f"{hours_left} hours remaining",
                    official_url=ev["registration_url"] or ev["source_url"],
                    source_name=ev["source_name"],
                    created_at=now_utc_iso,
                    dedup_key=dedup_key,
                )
                if inserted:
                    newly_inserted += 1

            # 24-hour interval: within 24h and > 0h
            if prefs.remind_24_hours and 0.0 < total_hours <= 24.0:
                hours_left = int(total_hours)
                dedup_key = f"{user_email}:{ev['id']}:24h:{deadline_ist}"
                title = f"Final 24-Hour Reminder: {ev['title']}"
                message = f"Final call! Registration deadline is today at {formatted_ist}. Check official registration page now."
                inserted = _insert_notification_if_absent(
                    conn,
                    user_email=user_email,
                    event_id=ev["id"],
                    category="deadline_reminder",
                    reminder_interval="24h",
                    title=title,
                    message=message,
                    event_title=ev["title"],
                    deadline_ist=deadline_ist,
                    deadline_formatted=formatted_ist,
                    remaining_time=f"{hours_left} hours remaining",
                    official_url=ev["registration_url"] or ev["source_url"],
                    source_name=ev["source_name"],
                    created_at=now_utc_iso,
                    dedup_key=dedup_key,
                )
                if inserted:
                    newly_inserted += 1

    # 2. Evaluate Verified Deadline Changes (alerts when an event deadline changes from prior notification)
    if prefs.master_reminders_enabled and prefs.deadline_changes_enabled:
        for ev in events:
            if ev["deadline_status"] != "verified" or not ev["deadline"] or not str(ev["deadline"]).strip():
                continue

            try:
                deadline_ist, formatted_ist, _ = convert_deadline_to_ist_safe(ev["deadline"], timezone_name=ev["timezone"])
            except Exception:
                continue

            cursor.execute("""
                SELECT deadline_ist, deadline_formatted FROM notifications
                WHERE LOWER(user_email) = LOWER(?) AND event_id = ?
                  AND category != 'deadline_change'
                  AND deadline_ist IS NOT NULL AND deadline_ist != '' AND deadline_ist != ?
                ORDER BY id DESC LIMIT 1;
            """, (user_email, ev["id"], deadline_ist))
            prev_row = cursor.fetchone()
            if prev_row:
                prev_deadline_ist = prev_row["deadline_ist"]
                prev_formatted_ist = prev_row["deadline_formatted"]
                if prev_deadline_ist and prev_deadline_ist != deadline_ist:
                    dedup_key = f"{user_email}:{ev['id']}:deadline_change:{prev_deadline_ist}->{deadline_ist}"
                    title = f"Deadline Changed: {ev['title']}"
                    message = f"Registration cutoff for {ev['title']} has been updated to {formatted_ist} (previously {prev_formatted_ist})."
                    inserted = _insert_notification_if_absent(
                        conn,
                        user_email=user_email,
                        event_id=ev["id"],
                        category="deadline_change",
                        reminder_interval=None,
                        title=title,
                        message=message,
                        event_title=ev["title"],
                        deadline_ist=deadline_ist,
                        deadline_formatted=formatted_ist,
                        remaining_time="Updated Deadline",
                        official_url=ev["registration_url"] or ev["source_url"],
                        source_name=ev["source_name"],
                        created_at=now_utc_iso,
                        dedup_key=dedup_key,
                    )
                    if inserted:
                        newly_inserted += 1

    # 3. Evaluate Matching Event Notifications (strictly for matching skills)
    if prefs.matching_events_enabled:
        cursor.execute("SELECT skills FROM student_profiles WHERE LOWER(student_email) = LOWER(?) LIMIT 1;", (user_email,))
        p_row = cursor.fetchone()
        skills = [s.strip().lower() for s in (p_row["skills"].split(",") if p_row and p_row["skills"] else []) if s.strip()]

        # Only evaluate if the student has configured technical skills
        if skills:
            for ev in events:
                tags_lower = [t.strip().lower() for t in (ev["tags"].split(",") if ev["tags"] else []) if t.strip()]
                has_match = any(s in tags_lower or any(s in tag for tag in tags_lower) for s in skills)
                if has_match:
                    try:
                        deadline_ist, formatted_ist, _ = convert_deadline_to_ist_safe(ev["deadline"], timezone_name=ev["timezone"])
                    except Exception:
                        deadline_ist = ev["deadline"]
                        formatted_ist = ev["deadline"]

                    if not is_deadline_expired(deadline_ist, reference_time_utc=reference_time_utc):
                        dedup_key = f"{user_email}:{ev['id']}:matching_contest"
                        title = f"Eligible Contest Match: {ev['title']}"
                        message = f"New hackathon opportunity matches your criteria: {ev['title']} ({ev['organizer']}). Deadline: {formatted_ist or 'See details'}."
                        inserted = _insert_notification_if_absent(
                            conn,
                            user_email=user_email,
                            event_id=ev["id"],
                            category="matching_event",
                            reminder_interval=None,
                            title=title,
                            message=message,
                            event_title=ev["title"],
                            deadline_ist=deadline_ist,
                            deadline_formatted=formatted_ist,
                            remaining_time="Active Registration",
                            official_url=ev["registration_url"] or ev["source_url"],
                            source_name=ev["source_name"],
                            created_at=now_utc_iso,
                            dedup_key=dedup_key,
                        )
                        if inserted:
                            newly_inserted += 1

    return newly_inserted

def _insert_notification_if_absent(
    conn: sqlite3.Connection,
    user_email: str,
    event_id: int,
    category: str,
    reminder_interval: Optional[str],
    title: str,
    message: str,
    event_title: str,
    deadline_ist: str,
    deadline_formatted: str,
    remaining_time: str,
    official_url: str,
    source_name: str,
    created_at: str,
    dedup_key: str,
) -> bool:
    """Helper to insert notification with stable deduplication."""
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO notifications (
        user_email, event_id, category, reminder_interval, title, message,
        event_title, deadline_ist, deadline_formatted, remaining_time,
        official_url, source_name, is_read, created_at, dedup_key
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?);
    """, (
        user_email.strip().lower(),
        event_id,
        category,
        reminder_interval,
        title,
        message,
        event_title,
        deadline_ist,
        deadline_formatted,
        remaining_time,
        official_url,
        source_name,
        created_at,
        dedup_key,
    ))
    conn.commit()
    return cursor.rowcount > 0
