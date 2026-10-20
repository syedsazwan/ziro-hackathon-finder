import datetime
from zoneinfo import ZoneInfo
from typing import Tuple, List, Optional, Dict, Any

IST_ZONE = ZoneInfo("Asia/Kolkata")

# Timezone alias mapping for common representations
TZ_ALIASES = {
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "UTC": "UTC",
    "GMT": "UTC",
    "IST": "Asia/Kolkata",
}

def resolve_timezone(tz_name: str) -> ZoneInfo:
    resolved_name = TZ_ALIASES.get(tz_name.upper(), tz_name)
    return ZoneInfo(resolved_name)

def convert_to_ist(deadline_str: Optional[str], timezone_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses a deadline string and converts it to Indian Standard Time (IST, UTC+05:30).
    Handles ISO formatted strings with timezone offsets and timezone-naive strings
    paired with timezone_name.
    
    Returns:
        (iso_string, formatted_display_string) or (None, None) if missing.
        e.g. ("2026-11-16T13:29:00+05:30", "16 Nov 2026, 01:29 PM IST")
    """
    if not deadline_str or not str(deadline_str).strip():
        return None, None

    cleaned_deadline = str(deadline_str).strip()
    normalized_iso = cleaned_deadline.replace("Z", "+00:00") if cleaned_deadline.endswith("Z") else cleaned_deadline

    # Parse ISO string
    dt = datetime.datetime.fromisoformat(normalized_iso)
    
    if dt.tzinfo is None:
        if timezone_name:
            tz = resolve_timezone(timezone_name)
            dt = dt.replace(tzinfo=tz)
        else:
            # Fallback to UTC if unspecified
            dt = dt.replace(tzinfo=datetime.timezone.utc)
            
    # Convert timezone-aware datetime to IST
    dt_ist = dt.astimezone(IST_ZONE)
    iso_output = dt_ist.isoformat()
    formatted_output = dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    return iso_output, formatted_output

def calculate_eligibility(
    team_min: int,
    team_max: int,
    fee_status: str,
    fee_amount: Optional[float],
    team_size: int = 1,
    budget: Optional[float] = None,
    skills: Optional[List[str]] = None,
    event_tags: Optional[List[str]] = None,
    region: Optional[str] = None,
    event_region: Optional[str] = None,
    deadline_status: Optional[str] = None,
    is_deadline_expired: bool = False,
    verification_status: Optional[str] = None,
    event_end_date: Optional[str] = None,
    is_closed: bool = False,
) -> Dict[str, Any]:
    """
    Evaluates student eligibility for an event:
    - Verifies event has not ended or closed
    - Team size check
    - Unknown fee requiring verification
    - Budget limit check
    - Unlisted/unverified registration cutoff requiring verification
    - Unverified event details requiring verification
    - Informational notes for skills and region matching
    """
    from app.normalization import is_date_in_past

    reasons: List[str] = []
    is_not_eligible = False
    needs_verification = False

    # 1. Closed / Ended Event Check
    norm_dl_status = (deadline_status or "").strip().lower()
    event_ended = (
        is_closed
        or is_deadline_expired
        or norm_dl_status == "closed"
        or (event_end_date is not None and is_date_in_past(event_end_date))
    )
    if event_ended:
        is_not_eligible = True
        reasons.append("Event registration is closed or the event has ended.")

    # 2. Team size validation
    if team_size < team_min:
        is_not_eligible = True
        reasons.append(f"Team size {team_size} is below the minimum required ({team_min}).")
    elif team_size > team_max:
        is_not_eligible = True
        reasons.append(f"Team size {team_size} exceeds the maximum allowed ({team_max}).")
    else:
        reasons.append(f"Team size {team_size} fits requirement ({team_min}-{team_max}).")

    # 3. Fee & Budget validation
    normalized_fee_status = fee_status.strip().lower()
    if normalized_fee_status == "unknown" or (fee_amount is None and normalized_fee_status != "free"):
        needs_verification = True
        reasons.append("Registration fee status is unknown; requires verification.")
    elif normalized_fee_status == "free" or (fee_amount is not None and fee_amount == 0):
        reasons.append("Free registration.")
    elif normalized_fee_status == "paid":
        if budget is not None and fee_amount is not None and fee_amount > budget:
            is_not_eligible = True
            reasons.append(f"Entry fee (${fee_amount:.2f}) exceeds your budget (${budget:.2f}).")
        elif fee_amount is not None:
            reasons.append(f"Entry fee: ${fee_amount:.2f} within budget.")

    # 4. Registration Cutoff Verification Check
    # Safety invariant: Never mark an event Eligible solely because team size and fee appear compatible
    # when the registration cutoff date is unlisted or unverified
    if not event_ended:
        if norm_dl_status in ("unavailable", "unverified"):
            needs_verification = True
            reasons.append("Registration cutoff is unlisted or unverified upstream; manual verification required on official portal.")

    # 5. Event Verification Status Check
    norm_ver_status = (verification_status or "").strip().lower()
    if not event_ended:
        if norm_ver_status in ("needs_verification", "unverified"):
            needs_verification = True
            reasons.append("Eligibility rules and event details require verification from official event page.")

    # 6. Informational skills match
    if skills and event_tags:
        student_skills_lower = {s.strip().lower() for s in skills if s.strip()}
        event_tags_lower = {t.strip().lower() for t in event_tags if t.strip()}
        matches = student_skills_lower.intersection(event_tags_lower)
        if matches:
            matched_str = ", ".join(sorted(matches))
            reasons.append(f"Matched skills: {matched_str}.")

    # 7. Final status determination
    if is_not_eligible:
        status = "Not eligible"
    elif needs_verification:
        status = "Needs verification"
    else:
        status = "Eligible"

    return {
        "status": status,
        "reasons": reasons,
    }
