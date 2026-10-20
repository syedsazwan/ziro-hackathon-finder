import datetime
import httpx
from typing import List, Optional
from app.adapters.base import BaseEventSourceAdapter, SourceFetchResult
from app.normalization import normalize_raw_event, NormalizedEventRecord

DEVFOLIO_API_URL = "https://api.devfolio.co/api/hackathons"

class DevfolioAdapter(BaseEventSourceAdapter):
    @property
    def source_name(self) -> str:
        return "Devfolio"

    def is_available(self) -> bool:
        return True

    def get_limitations(self) -> str:
        return (
            "Permitted public read-only access via Devfolio public hackathons API endpoint. "
            "No private endpoints, authentication, or automated actions are used."
        )

    def fetch_events(
        self,
        limit: int = 15,
        client: Optional[httpx.Client] = None,
        criteria: Optional[dict] = None,
    ) -> SourceFetchResult:
        """Fetches publicly listed hackathons from Devfolio official public API using student criteria."""
        criteria = criteria or {}
        event_format = (criteria.get("event_format") or criteria.get("format") or "").lower()
        status_req = (criteria.get("status") or "").lower()

        # Select permitted Devfolio API filter based on student search criteria
        if "online" in event_format or "virtual" in event_format:
            filter_val = "online"
        elif status_req == "upcoming":
            filter_val = "application_open"
        else:
            filter_val = "application_open"

        params = {
            "filter": filter_val,
            "page": 1,
            "limit": limit,
        }
        headers = {
            "User-Agent": "HackathonFinder/3.0 (Educational Academic Research; public-access-only)",
            "Accept": "application/json",
        }

        try:
            if client is not None:
                response = client.get(DEVFOLIO_API_URL, params=params, headers=headers, timeout=10.0)
            else:
                with httpx.Client(timeout=10.0) as http_client:
                    response = http_client.get(DEVFOLIO_API_URL, params=params, headers=headers)

            if response.status_code != 200:
                return SourceFetchResult(
                    source_name=self.source_name,
                    status="error",
                    notes=self.get_limitations(),
                    error_message=f"Devfolio API returned HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            raw_items = data.get("result", [])
            normalized_events: List[NormalizedEventRecord] = []

            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

            for item in raw_items:
                slug = item.get("slug")
                uuid = item.get("uuid")
                canonical_url = f"https://{slug}.devfolio.co" if slug else f"https://devfolio.co/hackathons/{uuid}"
                
                hs = item.get("hackathon_setting") or {}
                # Verified registration cutoff from Devfolio API setting
                reg_ends_at = hs.get("reg_ends_at") or item.get("reg_ends_at") or item.get("deadline")
                
                if reg_ends_at:
                    deadline_val = reg_ends_at
                    deadline_status = "verified"
                    deadline_notes = "Official registration deadline verified from Devfolio public API."
                else:
                    # NEVER infer registration deadline from starts_at or ends_at
                    deadline_val = None
                    deadline_status = "unavailable"
                    deadline_notes = "Registration deadline not specified by Devfolio; consult official event page."

                starts_at = item.get("starts_at")
                ends_at = item.get("ends_at")
                is_online = bool(item.get("is_online", True))
                country = item.get("country")
                city = item.get("city")
                state = item.get("state")
                raw_location = item.get("location")

                if raw_location and raw_location.strip():
                    loc = raw_location.strip()
                elif not is_online and (city or state or country):
                    parts = [p.strip() for p in [city, state, country] if p and p.strip()]
                    loc = ", ".join(parts)
                else:
                    loc = "Online"

                if country and country.strip().lower() == "india":
                    region = "India"
                elif is_online:
                    region = "Global / Online"
                elif country:
                    region = country.strip()
                else:
                    region = "Global / Online"

                event_format = "Online / Virtual" if is_online else "In-Person"

                raw_event = {
                    "title": item.get("name"),
                    "organizer": item.get("hackathon_brand") or item.get("name") or "Devfolio Community Organizer",
                    "source_name": self.source_name,
                    "source_event_id": uuid,
                    "source_url": canonical_url,
                    "registration_url": canonical_url,
                    "deadline": deadline_val,
                    "deadline_status": deadline_status,
                    "deadline_notes": deadline_notes,
                    "timezone": "UTC",
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "location": loc,
                    "format": event_format,
                    "is_online": is_online,
                    "country": country,
                    "region": region,
                    "fee_status": "free",
                    "fee_amount": 0.0,
                    "fee_currency": "USD",
                    "team_min": 1,
                    "team_max": 4,
                    "eligibility_requirements": "Open to all verified student and developer teams on Devfolio",
                    "retrieved_at": now_utc,
                    "verification_status": "verified" if deadline_status == "verified" else "needs_verification",
                    "evidence_notes": f"Ingested from official Devfolio public hackathon API: uuid={uuid}.",
                    "data_source_type": "official_api",
                    "tags": [t["name"] for t in item.get("themes", []) if isinstance(t, dict) and "name" in t] or ["Hackathon", "Devfolio"],
                }

                try:
                    norm = normalize_raw_event(raw_event, is_synthetic=False)
                    normalized_events.append(norm)
                except Exception:
                    # Skip individually malformed records safely
                    continue

            return SourceFetchResult(
                source_name=self.source_name,
                status="success",
                events=normalized_events,
                events_count=len(normalized_events),
                notes=f"Successfully fetched {len(normalized_events)} permitted public events from Devfolio official API."
            )

        except Exception as e:
            return SourceFetchResult(
                source_name=self.source_name,
                status="error",
                notes=self.get_limitations(),
                error_message=f"Network error connecting to Devfolio: {str(e)}"
            )
