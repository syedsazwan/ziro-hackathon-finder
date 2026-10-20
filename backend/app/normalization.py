import datetime
import re
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field

IST_ZONE = ZoneInfo("Asia/Kolkata")

TZ_ALIASES = {
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "UTC": "UTC",
    "GMT": "UTC",
    "IST": "Asia/Kolkata",
}

COUNTRY_NAME_MAP: Dict[str, str] = {
    "IN": "India",
    "IND": "India",
    "US": "United States",
    "USA": "United States",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "CA": "Canada",
    "CAN": "Canada",
    "DE": "Germany",
    "DEU": "Germany",
    "FR": "France",
    "FRA": "France",
    "AU": "Australia",
    "AUS": "Australia",
    "SG": "Singapore",
    "SGP": "Singapore",
    "JP": "Japan",
    "JPN": "Japan",
    "MX": "Mexico",
    "MEX": "Mexico",
    "BR": "Brazil",
    "BRA": "Brazil",
    "ES": "Spain",
    "ESP": "Spain",
    "NL": "Netherlands",
    "NLD": "Netherlands",
    "CH": "Switzerland",
    "CHE": "Switzerland",
    "SE": "Sweden",
    "SWE": "Sweden",
    "IE": "Ireland",
    "IRL": "Ireland",
    "FI": "Finland",
    "FIN": "Finland",
    "IT": "Italy",
    "ITA": "Italy",
    "NO": "Norway",
    "NOR": "Norway",
    "DK": "Denmark",
    "DNK": "Denmark",
    "PL": "Poland",
    "POL": "Poland",
    "AT": "Austria",
    "AUT": "Austria",
    "BE": "Belgium",
    "BEL": "Belgium",
    "NZ": "New Zealand",
    "NZL": "New Zealand",
    "PT": "Portugal",
    "PRT": "Portugal",
}

def normalize_country_name(raw: Optional[str]) -> Optional[str]:
    """
    Normalizes ISO country codes (e.g. 'IN', 'US', 'GB', 'DE', 'CA', 'FI')
    and inconsistent strings to readable standard country names.
    """
    if not raw or not isinstance(raw, str):
        return None
    val = raw.strip()
    if not val:
        return None
    upper = val.upper()
    if upper in COUNTRY_NAME_MAP:
        return COUNTRY_NAME_MAP[upper]
    for full_name in COUNTRY_NAME_MAP.values():
        if full_name.lower() == val.lower():
            return full_name
    return val

class NormalizationError(ValueError):
    """Raised when an event fails strict safety validation or normalization."""
    pass

def validate_source_url(url: Optional[str], is_synthetic: bool = False) -> str:
    """
    Validates official source URLs.
    Rejects missing or malformed URLs for real discovered events.
    """
    if not url or not isinstance(url, str):
        raise NormalizationError("Missing source URL. All real events must provide an official source URL.")
    
    trimmed = url.strip()
    if is_synthetic:
        # Synthetic demo fixtures may use mock fixture URLs
        if trimmed.startswith("https://demo-fixtures.local") or trimmed.startswith("http://") or trimmed.startswith("https://"):
            return trimmed
        raise NormalizationError(f"Malformed synthetic source URL: '{trimmed}'.")

    parsed = urllib.parse.urlparse(trimmed)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
        raise NormalizationError(f"Invalid or malformed source URL for real event: '{trimmed}'. Must be a valid HTTP/HTTPS URL.")
    
    return trimmed

def validate_registration_url(url: Optional[str]) -> Optional[str]:
    """Validates registration URLs. If provided, must be valid HTTP/HTTPS."""
    if not url:
        return None
    trimmed = url.strip()
    parsed = urllib.parse.urlparse(trimmed)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return trimmed

def convert_deadline_to_ist_safe(deadline_str: str, timezone_name: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Safely parses and converts a deadline timestamp to Indian Standard Time (IST, UTC+05:30).
    NEVER silently guesses ambiguous or unresolvable timezones.
    
    Returns:
        (iso_ist_string, formatted_ist_string, resolved_source_timezone)
    """
    if not deadline_str or not isinstance(deadline_str, str):
        raise NormalizationError("Missing deadline timestamp string.")
    
    cleaned_deadline = deadline_str.strip()
    
    # Handle ISO string with explicit 'Z' suffix
    normalized_iso = cleaned_deadline.replace("Z", "+00:00") if cleaned_deadline.endswith("Z") else cleaned_deadline

    try:
        dt = datetime.datetime.fromisoformat(normalized_iso)
    except ValueError as e:
        raise NormalizationError(f"Malformed deadline format '{deadline_str}': {e}")

    resolved_tz_name = "UTC"
    if dt.tzinfo is not None:
        # Timezone offset is explicitly present in the ISO string
        resolved_tz_name = timezone_name.strip() if timezone_name else "UTC"
    else:
        # Naive datetime: must have an unambiguous, resolvable timezone name
        if not timezone_name or not timezone_name.strip():
            raise NormalizationError(
                f"Deadline '{deadline_str}' is timezone-naive and no timezone was specified. "
                "Refusing to silently guess ambiguous timezone."
            )
        tz_lookup = timezone_name.strip()
        canonical_tz = TZ_ALIASES.get(tz_lookup.upper(), tz_lookup)
        try:
            tz_obj = ZoneInfo(canonical_tz)
        except ZoneInfoNotFoundError:
            raise NormalizationError(
                f"Ambiguous or unrecognized timezone '{timezone_name}' cannot be safely converted to IST without guessing."
            )
        dt = dt.replace(tzinfo=tz_obj)
        resolved_tz_name = canonical_tz

    # Convert to IST (Asia/Kolkata)
    dt_ist = dt.astimezone(IST_ZONE)
    iso_ist = dt_ist.isoformat()
    formatted_ist = dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    return iso_ist, formatted_ist, resolved_tz_name

def format_event_date_to_ist(date_str: Optional[str], timezone_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Safely formats an event date (starts_at/ends_at) to IST display format."""
    if not date_str or not isinstance(date_str, str):
        return None, None
    try:
        cleaned = date_str.strip()
        normalized_iso = cleaned.replace("Z", "+00:00") if cleaned.endswith("Z") else cleaned
        dt = datetime.datetime.fromisoformat(normalized_iso)
        if dt.tzinfo is None:
            tz_lookup = timezone_name.strip() if timezone_name else "UTC"
            canonical_tz = TZ_ALIASES.get(tz_lookup.upper(), tz_lookup)
            try:
                dt = dt.replace(tzinfo=ZoneInfo(canonical_tz))
            except Exception:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
        dt_ist = dt.astimezone(IST_ZONE)
        return dt_ist.isoformat(), dt_ist.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return None, None

def is_deadline_expired(deadline_ist_iso: Optional[str], reference_time_utc: Optional[datetime.datetime] = None) -> bool:
    """Accurately checks whether a converted IST deadline has already passed."""
    if not deadline_ist_iso:
        return False
    try:
        dt_deadline = datetime.datetime.fromisoformat(deadline_ist_iso)
        now_ist = (reference_time_utc or datetime.datetime.now(datetime.timezone.utc)).astimezone(IST_ZONE)
        return dt_deadline < now_ist
    except Exception:
        return False

def parse_date_range_string(s: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Safely parses common date range formats into ISO date strings (YYYY-MM-DD), e.g.:
    - 'Jun 19 - 22, 2024' -> ('2024-06-19', '2024-06-22')
    - 'Aug 31 - Oct 23, 2026' -> ('2026-08-31', '2026-10-23')
    - 'Dec 15, 2025 - Jan 15, 2026' -> ('2025-12-15', '2026-01-15')
    - 'Sep 12, 2026' -> ('2026-09-12', '2026-09-12')
    """
    if not s or not isinstance(s, str):
        return None, None
    cleaned = s.strip()
    
    # 1. 'Jun 19 - 22, 2024'
    m1 = re.match(r"^([A-Za-z]{3,9})\s+(\d{1,2})\s*-\s*(\d{1,2}),\s*(\d{4})$", cleaned)
    if m1:
        mon, d1, d2, yr = m1.groups()
        try:
            start = datetime.datetime.strptime(f"{mon[:3]} {d1} {yr}", "%b %d %Y").date().isoformat()
            end = datetime.datetime.strptime(f"{mon[:3]} {d2} {yr}", "%b %d %Y").date().isoformat()
            return start, end
        except Exception:
            pass

    # 2. 'Aug 31 - Oct 23, 2026'
    m2 = re.match(r"^([A-Za-z]{3,9})\s+(\d{1,2})\s*-\s*([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})$", cleaned)
    if m2:
        m_start, d1, m_end, d2, yr = m2.groups()
        try:
            start = datetime.datetime.strptime(f"{m_start[:3]} {d1} {yr}", "%b %d %Y").date().isoformat()
            end = datetime.datetime.strptime(f"{m_end[:3]} {d2} {yr}", "%b %d %Y").date().isoformat()
            return start, end
        except Exception:
            pass

    # 3. 'Dec 15, 2025 - Jan 15, 2026'
    m3 = re.match(r"^([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s*-\s*([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})$", cleaned)
    if m3:
        m1_name, d1, y1, m2_name, d2, y2 = m3.groups()
        try:
            start = datetime.datetime.strptime(f"{m1_name[:3]} {d1} {y1}", "%b %d %Y").date().isoformat()
            end = datetime.datetime.strptime(f"{m2_name[:3]} {d2} {y2}", "%b %d %Y").date().isoformat()
            return start, end
        except Exception:
            pass

    # 4. 'Sep 12, 2026'
    m4 = re.match(r"^([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})$", cleaned)
    if m4:
        mon, d, yr = m4.groups()
        try:
            dt = datetime.datetime.strptime(f"{mon[:3]} {d} {yr}", "%b %d %Y").date().isoformat()
            return dt, dt
        except Exception:
            pass

    return None, None

def is_date_in_past(date_str: Optional[str], reference_date: Optional[datetime.date] = None) -> bool:
    """Checks whether an ISO date string (YYYY-MM-DD or ISO timestamp) is strictly in the past."""
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        ref = reference_date or datetime.datetime.now(datetime.timezone.utc).date()
        cleaned = date_str.strip()
        if "T" in cleaned:
            dt = datetime.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            return dt.date() < ref
        d = datetime.date.fromisoformat(cleaned)
        return d < ref
    except Exception:
        return False

class NormalizedEventRecord(BaseModel):
    title: str
    organizer: str
    source_name: str
    source_event_id: Optional[str] = None
    source_url: str
    registration_url: Optional[str] = None
    description: str
    format: str = "Online / Virtual"
    location: str = "Online"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_date_ist_formatted: Optional[str] = None
    end_date_ist_formatted: Optional[str] = None
    deadline: Optional[str] = None
    timezone: str = "UTC"
    deadline_ist: Optional[str] = None
    deadline_ist_formatted: Optional[str] = None
    deadline_status: str = "verified"  # "verified", "unverified", "unavailable", "closed"
    deadline_notes: Optional[str] = None
    is_deadline_expired: bool = False
    team_min: int = 1
    team_max: int = 4
    eligibility_requirements: str = "Open to eligible participants"
    fee_amount: Optional[float] = None
    fee_currency: str = "USD"
    fee_status: str = "unknown"
    retrieved_at: str
    verification_status: str = "verified"
    evidence_notes: Optional[str] = None
    is_synthetic: bool = False
    data_source_type: str = "official_api"
    tags: List[str] = Field(default_factory=list)
    region: str = "Global / Online"
    country: Optional[str] = None
    prize_info: Optional[str] = None

def normalize_raw_event(raw: Dict[str, Any], is_synthetic: bool = False) -> NormalizedEventRecord:
    """
    Transforms and validates raw source event data into a NormalizedEventRecord.
    Enforces safety rules:
    - URL validation
    - Non-guessing IST conversion
    - Never infers a registration deadline from start/end dates
    - Explicit deadline status: verified, unverified, unavailable, closed
    - Accurate expiration detection
    - Explicit fee status marking ('Needs verification' if unknown)
    """
    title = str(raw.get("title") or raw.get("name") or "").strip()
    if not title:
        raise NormalizationError("Event record is missing a valid title.")

    organizer = str(raw.get("organizer") or raw.get("hackathon_brand") or "Independent / Community").strip()
    source_name = str(raw.get("source_name") or "Public Source").strip()
    source_event_id = str(raw.get("source_event_id") or raw.get("uuid") or "").strip() or None

    # Validate source URL
    source_url = validate_source_url(raw.get("source_url"), is_synthetic=is_synthetic)
    registration_url = validate_registration_url(raw.get("registration_url"))

    # Event dates
    start_date = raw.get("start_date") or raw.get("starts_at")
    end_date = raw.get("end_date") or raw.get("ends_at")

    deadline_notes = raw.get("deadline_notes")
    if (not start_date or not end_date) and raw.get("submission_period_dates"):
        s_parsed, e_parsed = parse_date_range_string(raw.get("submission_period_dates"))
        start_date = start_date or s_parsed
        end_date = end_date or e_parsed
    if (not start_date or not end_date) and deadline_notes:
        s_parsed, e_parsed = parse_date_range_string(deadline_notes)
        start_date = start_date or s_parsed
        end_date = end_date or e_parsed

    _, start_date_ist_formatted = format_event_date_to_ist(start_date, raw.get("timezone"))
    _, end_date_ist_formatted = format_event_date_to_ist(end_date, raw.get("timezone"))

    # Official source status & end date evaluation
    open_state = str(raw.get("open_state") or "").strip().lower()
    time_left = str(raw.get("time_left_to_submission") or "").strip().lower()
    is_source_ended = (open_state == "ended") or (time_left == "ended")
    is_end_date_past = is_date_in_past(end_date)
    explicit_status = str(raw.get("deadline_status") or "").strip().lower()
    is_event_concluded = is_source_ended or is_end_date_past or (explicit_status == "closed")

    # Registration Deadline: NEVER infer from start_date or end_date
    raw_deadline = raw.get("deadline") or raw.get("reg_ends_at")

    if is_event_concluded:
        final_deadline = str(raw_deadline) if (raw_deadline and str(raw_deadline).strip()) else None
        deadline_ist = None
        deadline_ist_formatted = "Registration Closed"
        deadline_expired = True
        deadline_status = "closed"
        resolved_tz = raw.get("timezone") or "UTC"
        if not deadline_notes or "consult official" in deadline_notes.lower():
            deadline_notes = f"Official event status: Ended. Event concluded on {end_date or 'past schedule'}."
    elif raw_deadline and str(raw_deadline).strip():
        deadline_ist, deadline_ist_formatted, resolved_tz = convert_deadline_to_ist_safe(
            str(raw_deadline),
            timezone_name=raw.get("timezone")
        )
        deadline_expired = is_deadline_expired(deadline_ist)
        if deadline_expired:
            deadline_status = "closed"
        elif explicit_status in ("verified", "unverified", "unavailable", "closed"):
            deadline_status = explicit_status
        else:
            deadline_status = "verified"
        final_deadline = str(raw_deadline)
    else:
        # Registration deadline is not specified by upstream source
        final_deadline = None
        deadline_ist = None
        deadline_ist_formatted = "Deadline Unavailable"
        deadline_expired = False
        deadline_status = "unavailable"
        resolved_tz = raw.get("timezone") or "UTC"
        if not deadline_notes:
            deadline_notes = "Registration deadline not specified by provider; consult official event page."

    # Format & Location
    is_online = raw.get("is_online", True)
    location = raw.get("location") or ("Online" if is_online else "In-Person")
    raw_format = str(raw.get("format") or "").strip()
    if raw_format:
        event_format = raw_format
    elif is_online:
        event_format = "Online / Virtual"
    else:
        event_format = "In-Person"

    # Team size
    team_min = int(raw.get("team_min") or 1)
    team_max = int(raw.get("team_max") or 4)
    if team_min < 1:
        team_min = 1
    if team_max < team_min:
        team_max = team_min

    # Fee evaluation
    raw_fee_status = str(raw.get("fee_status") or "").strip().lower()
    fee_amount = raw.get("fee_amount")
    fee_currency = str(raw.get("fee_currency") or "USD").strip().upper()

    if fee_amount is not None:
        try:
            fee_amount = float(fee_amount)
            if fee_amount == 0.0:
                fee_status = "free"
            else:
                fee_status = "paid"
        except (ValueError, TypeError):
            fee_amount = None
            fee_status = "unknown"
    elif raw_fee_status in ("free", "paid", "unknown"):
        fee_status = raw_fee_status
        if fee_status == "free":
            fee_amount = 0.0
    else:
        fee_status = "unknown"

    # Verification status
    raw_verification = str(raw.get("verification_status") or "verified").strip().lower()
    if fee_status == "unknown" or deadline_status in ("unavailable", "unverified"):
        verification_status = "needs_verification"
    elif raw_verification in ("verified", "needs_verification", "unverified"):
        verification_status = raw_verification
    else:
        verification_status = "verified"

    # Retrieved at
    retrieved_at = raw.get("retrieved_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Description & Tags
    description = str(raw.get("description") or f"Public contest listing retrieved from {source_name}.").strip()
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif isinstance(raw_tags, list):
        tags = [t["name"] if isinstance(t, dict) and "name" in t else str(t).strip() for t in raw_tags if t]
    else:
        tags = ["Hackathon"]

    # Country & Region
    raw_country = raw.get("country")
    country = normalize_country_name(raw_country)
    raw_region = raw.get("region")
    region_candidate = normalize_country_name(raw_region) if raw_region else None
    region = str(region_candidate or country or ("Global / Online" if raw.get("is_online") or event_format == "Online / Virtual" else "Global / Online")).strip()
    if region in COUNTRY_NAME_MAP:
        region = COUNTRY_NAME_MAP[region]

    evidence_notes = raw.get("evidence_notes") or f"Retrieved via permitted public feed from {source_name}."
    prize_info = raw.get("prize_info")

    return NormalizedEventRecord(
        title=title,
        organizer=organizer,
        source_name=source_name,
        source_event_id=source_event_id,
        source_url=source_url,
        registration_url=registration_url,
        description=description,
        format=event_format,
        location=location,
        start_date=start_date,
        end_date=end_date,
        start_date_ist_formatted=start_date_ist_formatted,
        end_date_ist_formatted=end_date_ist_formatted,
        deadline=final_deadline,
        timezone=resolved_tz,
        deadline_ist=deadline_ist,
        deadline_ist_formatted=deadline_ist_formatted,
        deadline_status=deadline_status,
        deadline_notes=deadline_notes,
        is_deadline_expired=deadline_expired,
        team_min=team_min,
        team_max=team_max,
        eligibility_requirements=str(raw.get("eligibility_requirements") or "Open to all eligible participants"),
        fee_amount=fee_amount,
        fee_currency=fee_currency,
        fee_status=fee_status,
        retrieved_at=retrieved_at,
        verification_status=verification_status,
        evidence_notes=evidence_notes,
        is_synthetic=is_synthetic,
        data_source_type="synthetic_demo_fixture" if is_synthetic else str(raw.get("data_source_type") or "official_api"),
        tags=tags,
        region=region,
        country=country,
        prize_info=prize_info,
    )
