import datetime
import httpx
from typing import Optional
from app.adapters.base import BaseEventSourceAdapter, SourceFetchResult
from app.normalization import normalize_raw_event

UNSTOP_PORTAL_URL = "https://unstop.com/hackathons"
UNSTOP_SEARCH_URL = "https://unstop.com/api/public/opportunity/search-result"

class UnstopAdapter(BaseEventSourceAdapter):
    """
    Adapter for Unstop hackathon & contest platform.
    
    Access Analysis & Safety Compliance:
    - Direct automated HTTP requests to Unstop public search APIs encounter Cloudflare anti-bot
      protection (HTTP 403 Forbidden).
    - Unstop has no documented, public unauthenticated REST API for third-party automated aggregators.
    - As mandated by project safety rules, automated bypass (CAPTCHA evasion, headless browsers)
      is strictly prohibited.
    - If anti-bot controls or HTTP 403 are encountered, the adapter reports the limitation truthfully
      and directs users to the official Unstop portal.
    """
    @property
    def source_name(self) -> str:
        return "Unstop"

    def is_available(self) -> bool:
        return False

    def get_limitations(self) -> str:
        return (
            "Automated public access is restricted: Unstop public opportunity search endpoints require "
            "browser session authentication and are protected by Cloudflare bot management (HTTP 403). "
            f"In adherence to project safety rules, access bypass is disabled. Official portal: {UNSTOP_PORTAL_URL}"
        )

    def fetch_events(
        self,
        limit: int = 15,
        client: Optional[httpx.Client] = None,
        criteria: Optional[dict] = None,
    ) -> SourceFetchResult:
        """
        Evaluates Unstop access truthfully.
        
        Access Investigation:
        - Unstop does not offer a documented public API or API keys for automated event retrieval.
        - Unstop Terms of Service explicitly prohibit robots, scrapers, and automated access.
        - Automated requests encounter Cloudflare bot protection (HTTP 403).
        - In adherence to project guidelines ('If explicit terms prevent automated access, do not bypass them'),
          direct automated harvesting is disabled and a truthful restricted status is returned with the official link.
        - If an authorized or mock client is provided, handles HTTP 403 or parses valid JSON accordingly.
        """
        if client is None:
            return SourceFetchResult(
                source_name=self.source_name,
                status="restricted",
                events=[],
                events_count=0,
                notes=self.get_limitations(),
                error_message=f"Automated harvesting disabled: Unstop has no documented public API and Terms of Service prohibit unauthorized scrapers. Upstream Cloudflare access policy applies. Official portal: {UNSTOP_PORTAL_URL}"
            )

        try:
            resp = client.get(
                UNSTOP_SEARCH_URL,
                params={"opportunity": "hackathons", "per_page": limit},
                headers={
                    "User-Agent": "HackathonFinder/3.0",
                    "Accept": "application/json"
                },
                timeout=5.0
            )
            if resp.status_code == 403:
                return SourceFetchResult(
                    source_name=self.source_name,
                    status="restricted",
                    events=[],
                    events_count=0,
                    notes=self.get_limitations(),
                    error_message=f"HTTP 403 Forbidden: Cloudflare anti-bot verification required. Automated harvesting disabled due to upstream Cloudflare access policy. Official portal: {UNSTOP_PORTAL_URL}"
                )
            elif resp.status_code == 200:
                payload = resp.json()
                raw_items = payload.get("data", {}).get("data", [])
                events = []
                for item in raw_items:
                    opp_id = str(item.get("id"))
                    title = item.get("title") or "Untitled Hackathon"
                    pub_url = item.get("public_url") or ""
                    if pub_url.startswith("http://") or pub_url.startswith("https://"):
                        source_url = pub_url
                    elif pub_url:
                        source_url = f"https://unstop.com/{pub_url.lstrip('/')}"
                    else:
                        source_url = f"https://unstop.com/opportunity/{opp_id}"

                    org = (item.get("organisation") or {}).get("name") or "Unstop Partner"

                    regn = item.get("regnRequirements") or {}
                    deadline = regn.get("end_regn_dt")
                    min_team = regn.get("min_team_size") or 1
                    max_team = regn.get("max_team_size") or 4

                    payments = item.get("payment_services") or []
                    is_free = any(p.get("amount", 0) == 0 for p in payments) if payments else True
                    fee_status = "free" if is_free else "paid"
                    fee_amount = 0.0 if is_free else float(payments[0].get("amount", 0.0))

                    skills = [s.get("skill") for s in item.get("required_skills", []) if s.get("skill")]
                    filters = [f.get("name") for f in item.get("filters", []) if f.get("name")]
                    tags = list(dict.fromkeys(skills + filters))

                    addr = item.get("address_with_country_logo") or {}
                    city = addr.get("city")
                    state = addr.get("state")
                    country = (addr.get("country") or {}).get("name") if isinstance(addr.get("country"), dict) else None
                    location_parts = [p for p in (city, state, country) if p]
                    location = ", ".join(location_parts) if location_parts else "Online"

                    raw_dict = {
                        "title": title,
                        "organizer": org,
                        "source_name": "Unstop",
                        "source_event_id": opp_id,
                        "source_url": source_url,
                        "registration_url": source_url,
                        "description": f"Public opportunity hosted on Unstop by {org}.",
                        "format": "Online / Virtual" if "Online" in location or not location_parts else "In-Person",
                        "location": location,
                        "country": country or "India",
                        "deadline": deadline,
                        "team_min": min_team,
                        "team_max": max_team,
                        "fee_status": fee_status,
                        "fee_amount": fee_amount,
                        "tags": tags,
                        "eligibility": ", ".join(filters) if filters else "Open to students & professionals"
                    }
                    events.append(normalize_raw_event(raw_dict, is_synthetic=False))

                return SourceFetchResult(
                    source_name=self.source_name,
                    status="success",
                    events=events,
                    events_count=len(events),
                    notes="Successfully retrieved public opportunities from Unstop."
                )
            else:
                return SourceFetchResult(
                    source_name=self.source_name,
                    status="error",
                    events=[],
                    events_count=0,
                    notes=self.get_limitations(),
                    error_message=f"Unstop API returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
        except Exception as e:
            return SourceFetchResult(
                source_name=self.source_name,
                status="restricted",
                events=[],
                events_count=0,
                notes=self.get_limitations(),
                error_message=f"Automated harvesting disabled due to upstream Cloudflare access policy: {str(e)}. Official portal: {UNSTOP_PORTAL_URL}"
            )
