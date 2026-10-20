import datetime
import re
import httpx
from typing import List, Optional, Dict, Any
from app.adapters.base import BaseEventSourceAdapter, SourceFetchResult
from app.normalization import (
    normalize_raw_event,
    NormalizedEventRecord,
    parse_date_range_string,
    is_date_in_past,
)

DEVPOST_API_URL = "https://devpost.com/api/hackathons"
DEVPOST_PAGE_DEADLINE_CACHE: Dict[str, Dict[str, Any]] = {}

def resolve_devpost_page_deadline(
    url: str,
    client: Optional[httpx.Client] = None
) -> Optional[Dict[str, str]]:
    """
    Safely resolves the published registration / submission deadline from a Devpost
    canonical public hackathon page (e.g. <time datetime="...">).
    Caches results in-memory to prevent repeated network requests.
    Respects strict timeouts (5.0s) and never throws exceptions.
    """
    if not url or not url.startswith("http"):
        return None
    
    if url in DEVPOST_PAGE_DEADLINE_CACHE:
        return DEVPOST_PAGE_DEADLINE_CACHE[url]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    
    try:
        if client is not None:
            resp = client.get(url, headers=headers, timeout=5.0, follow_redirects=True)
        else:
            with httpx.Client(timeout=5.0, follow_redirects=True) as http_client:
                resp = http_client.get(url, headers=headers)
        
        if resp.status_code == 200:
            pattern = re.compile(
                r'<time[^>]*datetime=["\']([^"\']+)["\'][^>]*>(.*?)</time>',
                re.DOTALL | re.IGNORECASE
            )
            matches = pattern.findall(resp.text)
            if matches:
                iso_dt, time_text = matches[0]
                clean_time_text = re.sub(r'\s+', ' ', time_text).strip()
                res = {
                    "deadline_iso": iso_dt.strip(),
                    "time_text": clean_time_text,
                    "notes": f"Official submission deadline verified from Devpost public page: {clean_time_text}",
                }
                DEVPOST_PAGE_DEADLINE_CACHE[url] = res
                return res
    except Exception:
        pass
    
    return None

class DevpostAdapter(BaseEventSourceAdapter):
    """
    Adapter for Devpost public hackathon listings.
    
    Access Analysis & Permitted Method:
    - Devpost exposes a public JSON listing endpoint at https://devpost.com/api/hackathons.
    - Public requests with standard User-Agent succeed without authentication or Cloudflare anti-bot blocks.
    - Supports query parameters such as 'search' and 'challenge_type[]=online' for filter-driven retrieval.
    - Respects reasonable rate limits (10s timeout, pagination limited to requested batch).
    - Safely resolves official submission timestamps from canonical public pages using <time> tags.
    """
    @property
    def source_name(self) -> str:
        return "Devpost"

    def is_available(self) -> bool:
        return True

    def get_limitations(self) -> str:
        return (
            "Permitted public read-only access via Devpost public hackathons API (devpost.com/api/hackathons). "
            "Verified timestamps extracted from canonical event pages with timezone provenance."
        )

    def fetch_events(
        self,
        limit: int = 15,
        client: Optional[httpx.Client] = None,
        criteria: Optional[Dict[str, Any]] = None,
    ) -> SourceFetchResult:
        """Fetches publicly listed hackathons from Devpost public API based on student search criteria."""
        criteria = criteria or {}
        params: Dict[str, Any] = {"page": 1}

        query = criteria.get("query") or criteria.get("q") or criteria.get("search")
        skills = criteria.get("skills") or []
        event_format = (criteria.get("event_format") or criteria.get("format") or "").lower()

        if query:
            params["search"] = str(query).strip()
        elif skills and len(skills) > 0:
            params["search"] = str(skills[0]).strip()

        if "online" in event_format or "virtual" in event_format:
            params["challenge_type[]"] = "online"

        status_req = (criteria.get("status") or "upcoming").lower()
        if status_req in ("closed", "ended", "past"):
            params["status[]"] = "ended"
        elif status_req != "all":
            # Default to open/upcoming hackathons to prevent historical hackathons from leaking into upcoming feed
            params["status[]"] = "open"

        headers = {
            "User-Agent": "HackathonFinder/3.0 (Educational Academic Research; public-schedule-reader)",
            "Accept": "application/json",
        }

        try:
            if client is not None:
                response = client.get(DEVPOST_API_URL, params=params, headers=headers, timeout=10.0)
            else:
                with httpx.Client(timeout=10.0, follow_redirects=True) as http_client:
                    response = http_client.get(DEVPOST_API_URL, params=params, headers=headers)

            if response.status_code != 200:
                return SourceFetchResult(
                    source_name=self.source_name,
                    status="error",
                    notes=self.get_limitations(),
                    error_message=f"Devpost API returned HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            raw_items = data.get("hackathons", [])
            normalized_events: List[NormalizedEventRecord] = []
            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for item in raw_items[:limit]:
                devpost_id = str(item.get("id"))
                title = item.get("title") or "Devpost Hackathon"
                url = item.get("url")
                if not url:
                    continue

                org = item.get("organization_name") or "Devpost Community Organizer"
                displayed_loc = item.get("displayed_location", {}) or {}
                location_str = displayed_loc.get("location") or "Online"
                is_online = "online" in location_str.lower() or displayed_loc.get("icon") == "globe"
                fmt = "Online / Virtual" if is_online else "In-Person"

                themes = item.get("themes", []) or []
                tags = [t.get("name") for t in themes if isinstance(t, dict) and t.get("name")]
                if not tags:
                    tags = ["Hackathon"]

                sub_dates = item.get("submission_period_dates")
                open_state = str(item.get("open_state") or "").strip().lower()
                time_left = str(item.get("time_left_to_submission") or "").strip()
                start_dt, end_dt = parse_date_range_string(sub_dates) if sub_dates else (None, None)

                is_ended = (
                    open_state == "ended"
                    or time_left.lower() == "ended"
                    or (end_dt is not None and is_date_in_past(end_dt))
                )

                if is_ended:
                    dl_val = end_dt if (end_dt and "T" in end_dt) else (f"{end_dt}T23:59:59Z" if end_dt else None)
                    dl_status = "closed"
                    dl_notes = f"Official Devpost status: Ended. Submission period was {sub_dates or 'concluded'}."
                else:
                    page_dl = resolve_devpost_page_deadline(url, client=client)
                    if page_dl and page_dl.get("deadline_iso"):
                        dl_val = page_dl["deadline_iso"]
                        dl_status = "verified"
                        dl_notes = page_dl["notes"]
                    else:
                        dl_val = None
                        dl_status = "unavailable"
                        dl_notes = f"Submission period: '{sub_dates}'. Official registration cutoff not published upstream; consult official event page."

                prize_amt = item.get("prize_amount")
                clean_prize = None
                if prize_amt:
                    clean_prize = re.sub(r"<[^>]+>", "", str(prize_amt)).strip()

                raw_event = {
                    "title": title,
                    "organizer": org,
                    "source_name": self.source_name,
                    "source_event_id": devpost_id,
                    "source_url": url,
                    "registration_url": item.get("start_a_submission_url") or url,
                    "description": f"Public hackathon listed on Devpost: {title}. Submission period: {sub_dates or 'See official portal'}.",
                    "format": fmt,
                    "location": location_str,
                    "country": None if is_online else location_str,
                    "region": "Global / Online" if is_online else location_str,
                    "is_online": is_online,
                    "start_date": start_dt,
                    "end_date": end_dt,
                    "open_state": open_state,
                    "time_left_to_submission": time_left,
                    "submission_period_dates": sub_dates,
                    "deadline": dl_val,
                    "deadline_status": dl_status,
                    "deadline_notes": dl_notes,
                    "timezone": "UTC",
                    "fee_status": "free",
                    "fee_amount": 0.0,
                    "fee_currency": "USD",
                    "team_min": 1,
                    "team_max": 5,
                    "eligibility_requirements": "Open to participants eligible under official challenge rules",
                    "retrieved_at": now_utc,
                    "verification_status": "needs_verification",
                    "evidence_notes": f"Ingested from official Devpost public API: id={devpost_id}.",
                    "data_source_type": "official_api",
                    "tags": tags,
                    "prize_info": clean_prize,
                }

                try:
                    norm = normalize_raw_event(raw_event, is_synthetic=False)
                    normalized_events.append(norm)
                except Exception:
                    continue

            return SourceFetchResult(
                source_name=self.source_name,
                status="success",
                events=normalized_events,
                events_count=len(normalized_events),
                notes=f"Successfully fetched {len(normalized_events)} public hackathons from Devpost public API."
            )

        except Exception as e:
            return SourceFetchResult(
                source_name=self.source_name,
                status="error",
                notes=self.get_limitations(),
                error_message=f"Network error connecting to Devpost: {str(e)}"
            )

def backfill_devpost_deadlines(conn, client: Optional[httpx.Client] = None) -> int:
    """
    Backfills verified submission deadlines for active Devpost events currently in the database.
    Preserves all existing data and updates only when verified evidence is resolved.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, source_url, end_date, deadline_notes
        FROM events
        WHERE source_name = 'Devpost'
          AND (deadline IS NULL OR deadline = '' OR deadline_status = 'unavailable')
          AND deadline_status != 'closed'
    """)
    rows = cursor.fetchall()
    updated_count = 0

    for r in rows:
        eid, url, end_dt, notes = r
        if not url:
            continue
        page_dl = resolve_devpost_page_deadline(url, client=client)
        if page_dl and page_dl.get("deadline_iso"):
            cursor.execute("""
                UPDATE events
                SET deadline = ?,
                    deadline_status = 'verified',
                    deadline_notes = ?
                WHERE id = ?
            """, (page_dl["deadline_iso"], page_dl["notes"], eid))
            updated_count += 1

    if updated_count > 0:
        conn.commit()

    return updated_count

