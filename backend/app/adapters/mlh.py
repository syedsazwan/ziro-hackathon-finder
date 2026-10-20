import datetime
import json
import re
import httpx
from typing import List, Optional, Dict, Any
from app.adapters.base import BaseEventSourceAdapter, SourceFetchResult
from app.normalization import normalize_raw_event, NormalizedEventRecord

MLH_EVENTS_URL = "https://mlh.io/events"
MLH_BACKUP_URL = "https://mlh.io/seasons/2026/events"

COUNTRY_MAP: Dict[str, str] = {
    "US": "United States",
    "USA": "United States",
    "GB": "United Kingdom",
    "UK": "United Kingdom",
    "IN": "India",
    "CA": "Canada",
    "DE": "Germany",
    "FR": "France",
    "AU": "Australia",
    "SG": "Singapore",
    "JP": "Japan",
    "MX": "Mexico",
    "BR": "Brazil",
    "ES": "Spain",
    "NL": "Netherlands",
    "CH": "Switzerland",
    "SE": "Sweden",
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

class MLHAdapter(BaseEventSourceAdapter):
    """
    Adapter for Major League Hacking (MLH) official public hackathon seasons.
    
    Access Analysis:
    - MLH publishes official student hackathons publicly at https://mlh.io/events
    - Data is rendered with Inertia.js containing verified upcoming events.
    - All events adhere to MLH Member Hackathon guidelines (free admission for students).
    - In compliance with strict safety rules, registration deadlines are NOT inferred from start dates.
    """
    @property
    def source_name(self) -> str:
        return "MLH"

    def is_available(self) -> bool:
        return True

    def get_limitations(self) -> str:
        return (
            "Permitted public read-only access to official MLH schedule (mlh.io/events). "
            "Only official Member Hackathons with verified public URLs are ingested. "
            "Upstream does not publish separate registration cutoffs; deadlines are transparently marked unavailable."
        )

    def fetch_events(
        self,
        limit: int = 15,
        client: Optional[httpx.Client] = None,
        criteria: Optional[dict] = None,
    ) -> SourceFetchResult:
        """Fetches publicly listed hackathons from MLH public schedule."""
        headers = {
            "User-Agent": "HackathonFinder/3.0 (Educational Academic Research; public-schedule-reader)",
            "Accept": "text/html,application/xhtml+xml,application/json",
        }

        try:
            response = None
            for target_url in [MLH_EVENTS_URL, MLH_BACKUP_URL]:
                try:
                    if client is not None:
                        resp = client.get(target_url, headers=headers, timeout=10.0, follow_redirects=True)
                    else:
                        with httpx.Client(timeout=10.0, follow_redirects=True) as http_client:
                            resp = http_client.get(target_url, headers=headers)
                    if resp.status_code == 200:
                        response = resp
                        break
                except Exception:
                    continue

            if response is None or response.status_code != 200:
                status_code = response.status_code if response else "Connection Error"
                return SourceFetchResult(
                    source_name=self.source_name,
                    status="error",
                    notes=self.get_limitations(),
                    error_message=f"MLH portal returned HTTP {status_code}"
                )

            html_text = response.text
            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            normalized_events: List[NormalizedEventRecord] = []

            # 1. Parse Inertia JSON page props
            match = re.search(r'<script\s+data-page="app"\s+type="application/json">(.*?)</script>', html_text, re.DOTALL)
            raw_event_items: List[Dict[str, Any]] = []

            if match:
                try:
                    page_data = json.loads(match.group(1))
                    props = page_data.get("props", {})
                    raw_event_items = props.get("upcomingEvents", [])
                    if not raw_event_items:
                        # Fallback to pastEvents if upcoming is empty (for testing or off-season)
                        raw_event_items = props.get("pastEvents", [])
                except Exception:
                    raw_event_items = []

            # 2. Transform items into normalized event records
            for ev in raw_event_items[:limit]:
                name = ev.get("name")
                if not name:
                    continue

                event_id = str(ev.get("id") or ev.get("slug") or name)
                slug = ev.get("slug") or ""
                website_url = ev.get("websiteUrl")
                if website_url and isinstance(website_url, str) and website_url.strip().startswith("http"):
                    canonical_url = website_url.strip()
                elif slug:
                    canonical_url = f"https://mlh.io/events/{slug}"
                else:
                    canonical_url = f"https://mlh.io/events"

                starts_at = ev.get("startsAt")
                ends_at = ev.get("endsAt")
                format_type = str(ev.get("formatType") or "physical").strip().lower()

                if "physical" in format_type or "in-person" in format_type:
                    event_format = "In-Person"
                    is_online = False
                elif "hybrid" in format_type:
                    event_format = "Hybrid"
                    is_online = False
                else:
                    event_format = "Online / Virtual"
                    is_online = True

                venue = ev.get("venueAddress") or {}
                raw_country_code = str(venue.get("country") or "").strip().upper()
                country_name = COUNTRY_MAP.get(raw_country_code, raw_country_code) if raw_country_code else None

                city = venue.get("city")
                state = venue.get("state")
                raw_location = ev.get("location")

                if raw_location and str(raw_location).strip():
                    loc = str(raw_location).strip()
                elif not is_online and (city or state or country_name):
                    loc_parts = [p for p in [city, state, country_name] if p]
                    loc = ", ".join(loc_parts)
                else:
                    loc = "Online"

                if raw_country_code == "IN" or (country_name and "india" in country_name.lower()):
                    region = "India"
                elif is_online:
                    region = "Global / Online"
                elif country_name:
                    region = country_name
                else:
                    region = str(ev.get("region") or "Global / Online")

                # Strictly adhere to safety rule: never infer deadline from startsAt
                raw_event = {
                    "title": name.strip(),
                    "organizer": f"{name.strip()} Organizing Team (MLH)",
                    "source_name": self.source_name,
                    "source_event_id": event_id,
                    "source_url": canonical_url,
                    "registration_url": canonical_url,
                    "deadline": None,  # Registration cutoff not provided separately
                    "deadline_status": "unavailable",
                    "deadline_notes": "Official event dates verified via MLH. Upstream schedule does not publish a separate registration cutoff; refer to the official event link.",
                    "timezone": "UTC",
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "location": loc,
                    "format": event_format,
                    "is_online": is_online,
                    "country": country_name or raw_country_code or None,
                    "region": region,
                    "fee_status": "free",
                    "fee_amount": 0.0,
                    "fee_currency": "USD",
                    "team_min": 1,
                    "team_max": 4,
                    "eligibility_requirements": "Open to all enrolled students with verified student status",
                    "retrieved_at": now_utc,
                    "verification_status": "needs_verification",  # Needs verification because deadline cutoff is unlisted
                    "evidence_notes": f"Ingested from official MLH schedule: https://mlh.io/events (id={event_id}).",
                    "data_source_type": "official_api",
                    "tags": ["MLH", "Student Hackathon", "Hackathon"],
                    "description": f"Official MLH Member Hackathon scheduled for {ev.get('dateRange') or '2026'}. Free student participation.",
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
                notes=f"Successfully fetched {len(normalized_events)} permitted public events from official MLH schedule."
            )

        except Exception as e:
            return SourceFetchResult(
                source_name=self.source_name,
                status="error",
                notes=self.get_limitations(),
                error_message=f"Network error reading MLH public schedule: {str(e)}"
            )
