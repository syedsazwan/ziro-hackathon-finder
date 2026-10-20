from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field, EmailStr, field_validator

# Existing Stage 1 Schemas
class EligibilityResult(BaseModel):
    status: Literal["Eligible", "Not eligible", "Needs verification"]
    reasons: List[str]

class EligibilityCheckRequest(BaseModel):
    event_id: Optional[int] = None
    team_min: Optional[int] = None
    team_max: Optional[int] = None
    fee_status: Optional[str] = None
    fee_amount: Optional[float] = None
    team_size: int = Field(1, ge=1)
    budget: Optional[float] = None
    skills: List[str] = Field(default_factory=list)
    event_tags: List[str] = Field(default_factory=list)
    region: Optional[str] = None
    event_region: Optional[str] = None

class EventResponse(BaseModel):
    id: int
    title: str
    description: str
    organizer: str
    source_name: str = "Synthetic"
    source_event_id: Optional[str] = None
    source_url: str
    registration_url: Optional[str] = None
    retrieved_at: str
    team_min: int
    team_max: int
    fee_amount: Optional[float] = None
    fee_currency: str = "USD"
    fee_status: str
    deadline: Optional[str] = None
    timezone: str = "UTC"
    deadline_ist: Optional[str] = None
    deadline_ist_formatted: Optional[str] = None
    deadline_status: str = "verified"
    deadline_notes: Optional[str] = None
    is_deadline_expired: bool = False
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    start_date_ist_formatted: Optional[str] = None
    end_date_ist_formatted: Optional[str] = None
    location: str = "Online"
    format: str
    region: str
    country: Optional[str] = None
    prize_info: Optional[str] = None
    eligibility_requirements: str = "Open to eligible participants"
    verification_status: str = "verified"
    evidence_notes: Optional[str] = None
    is_synthetic: bool = True
    data_source_type: str
    tags: List[str]
    eligibility: EligibilityResult
    is_cached: bool = False
    last_synced_at: Optional[str] = None
    cache_status: str = "fresh"

class SourceSummary(BaseModel):
    source_name: str
    status: str
    events_fetched: int
    events_discovered: int = 0
    events_inserted: int = 0
    events_updated: int = 0
    events_skipped: int = 0
    events_failed: int = 0
    events_upserted: int = 0
    last_attempted_at: Optional[str] = None
    last_synced_at: Optional[str] = None
    notes: str
    error_message: Optional[str] = None

class DiscoveryMetadata(BaseModel):
    sources_searched: int = 0
    sources_available: int = 0
    sources_summary: List[SourceSummary] = Field(default_factory=list)
    total_candidates_retrieved: int = 0
    total_discovered: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    fresh_count: int = 0
    cached_count: int = 0
    sync_status: Optional[str] = "success"
    search_criteria_used: Optional[dict] = None

class EventsListResponse(BaseModel):
    total: int
    filter_applied: dict
    events: List[EventResponse]
    discovery_metadata: Optional[DiscoveryMetadata] = None

class RefreshSourcesResponse(BaseModel):
    status: str = "completed"
    sync_status: Optional[str] = "success"
    overall_status: Optional[str] = "success"
    refreshed_at: str
    total_fetched: int = 0
    total_upserted: int
    total_discovered: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    sources_summary: List[SourceSummary]

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    database: str
    version: str = "1.0.0"

# Stage 2: Safe Registration Workflow Schemas
RegistrationStatus = Literal[
    "pending_approval",
    "approved",
    "submitted",
    "confirmed",
    "failed",
    "needs_manual_verification",
    "cancelled"
]

class RegistrationActionCreate(BaseModel):
    event_id: int = Field(..., description="ID of the event to register for")
    student_email: str = Field(..., min_length=3, description="Student profile email identifier")
    student_name: str = Field(..., min_length=1, description="Student full name")
    team_size: int = Field(1, ge=1, le=20, description="Participating team size")
    notes: Optional[str] = Field(None, description="Optional registration notes or preferences")

class RegistrationApproveRequest(BaseModel):
    approver_name: str = Field(..., min_length=2, description="Name or role of the human approver")
    approval_notes: Optional[str] = Field(None, description="Notes recorded during human approval review")

    @field_validator("approver_name")
    @classmethod
    def validate_approver_name(cls, v: str) -> str:
        cleaned = v.strip()
        if cleaned.lower() in ("string", "placeholder", "test", "n/a", "none"):
            raise ValueError("Must provide a meaningful approver name rather than a placeholder.")
        return cleaned

class RegistrationSubmitRequest(BaseModel):
    simulate_outcome: Optional[str] = Field(
        "submitted",
        description="Outcome of simulated submission (never confirmed directly)"
    )
    failure_reason: Optional[str] = Field(None, description="Reason if simulated failure is chosen")

class RegistrationVerifyRequest(BaseModel):
    verified_by: str = Field(..., min_length=2, description="Operator or verifier identity")
    verification_status: Literal["confirmed", "failed", "needs_manual_verification"] = Field(
        ...,
        description="Target verified status"
    )
    evidence_notes: str = Field(..., min_length=8, description="Factual evidence notes justifying status")

    @field_validator("verified_by")
    @classmethod
    def validate_verified_by(cls, v: str) -> str:
        cleaned = v.strip()
        if cleaned.lower() in ("string", "placeholder", "test", "n/a", "none"):
            raise ValueError("Must provide a meaningful verifier identity rather than a placeholder.")
        return cleaned

    @field_validator("evidence_notes")
    @classmethod
    def validate_evidence_notes(cls, v: str) -> str:
        cleaned = v.strip()
        if cleaned.lower() in ("string", "placeholder", "test", "n/a", "none") or len(cleaned) < 8:
            raise ValueError("Must provide meaningful, factual verification evidence notes (minimum 8 non-placeholder characters).")
        return cleaned

class RegistrationCancelRequest(BaseModel):
    reason: Optional[str] = Field("Cancelled by student", description="Reason for cancellation")
    actor: Optional[str] = Field(None, description="Actor requesting cancellation")

class AuditLogResponse(BaseModel):
    id: int
    action_id: str
    from_status: Optional[str]
    to_status: str
    actor: str
    event_type: str
    details: str
    created_at: str

class AuditLogListResponse(BaseModel):
    total: int
    logs: List[AuditLogResponse]

class RegistrationActionResponse(BaseModel):
    id: str
    event_id: int
    student_email: str
    student_name: str
    team_size: int
    status: str
    created_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    approval_notes: Optional[str] = None
    submitted_at: Optional[str] = None
    verification_evidence: Optional[str] = None
    is_simulation: bool
    simulation_notice: str
    is_synthetic: bool = False

class RegistrationActionDetailResponse(RegistrationActionResponse):
    audit_logs: List[AuditLogResponse]

class RegistrationListResponse(BaseModel):
    total: int
    actions: List[RegistrationActionResponse]

# Stage 4C & 4E: Persisted Student Profile Schemas
class StudentProfilePayload(BaseModel):
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    team_size: int = Field(1, ge=1, le=20)
    region: Optional[str] = "All"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    institution: Optional[str] = None
    degree: Optional[str] = None
    graduation_year: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    bio: Optional[str] = None
    collaboration_preference: Optional[str] = None
    projects_json: Optional[str] = None
    participation_mode: Optional[str] = "All"

class StudentProfileResponse(BaseModel):
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    team_size: int = 2
    region: Optional[str] = "All"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    institution: Optional[str] = None
    degree: Optional[str] = None
    graduation_year: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    bio: Optional[str] = None
    collaboration_preference: Optional[str] = None
    projects_json: Optional[str] = None
    participation_mode: Optional[str] = "All"
    updated_at: Optional[str] = None

# Stage 4C: Data Source & Adapter Status Schemas
class AdapterStatusItem(BaseModel):
    source_name: str
    display_name: str
    access_mechanism: str
    compliance_status: str
    portal_url: Optional[str] = None
    last_synced_at: Optional[str] = None
    events_in_db: int = 0
    last_error: Optional[str] = None
    notes: Optional[str] = None

class AdapterStatusListResponse(BaseModel):
    adapters: List[AdapterStatusItem]

# Notification & Deadline Tracking Schemas
class NotificationPreferencesPayload(BaseModel):
    matching_events_enabled: bool = True
    upcoming_deadlines_enabled: bool = True
    deadline_changes_enabled: bool = True
    master_reminders_enabled: bool = True
    remind_7_days: bool = True
    remind_48_hours: bool = True
    remind_24_hours: bool = True
    browser_notifications_enabled: bool = False

class NotificationPreferencesResponse(BaseModel):
    user_email: str = "student@ziro.local"
    matching_events_enabled: bool = True
    upcoming_deadlines_enabled: bool = True
    deadline_changes_enabled: bool = True
    master_reminders_enabled: bool = True
    remind_7_days: bool = True
    remind_48_hours: bool = True
    remind_24_hours: bool = True
    browser_notifications_enabled: bool = False
    updated_at: Optional[str] = None

class NotificationItemResponse(BaseModel):
    id: int
    user_email: str
    event_id: Optional[int] = None
    category: str
    reminder_interval: Optional[str] = None
    title: str
    message: str
    event_title: str
    deadline_ist: Optional[str] = None
    deadline_formatted: Optional[str] = None
    remaining_time: Optional[str] = None
    official_url: Optional[str] = None
    source_name: Optional[str] = None
    is_read: bool = False
    created_at: str

class NotificationListResponse(BaseModel):
    unread_count: int
    total_count: int
    notifications: List[NotificationItemResponse]

class DeadlineGroupItem(BaseModel):
    event_id: int
    title: str
    organizer: str
    source_name: str
    source_url: str
    registration_url: Optional[str] = None
    deadline_ist: str
    deadline_ist_formatted: str
    deadline_group: str
    remaining_days: Optional[int] = None
    remaining_hours: Optional[int] = None
    is_deadline_expired: bool = False
    verification_status: str = "verified"

class DeadlineSummaryResponse(BaseModel):
    groups: Dict[str, List[DeadlineGroupItem]]
    counts: Dict[str, int]

# Authentication & User Session Schemas
class GoogleAuthUrlResponse(BaseModel):
    url: str
    auth_url: Optional[str] = None

class GoogleVerifyRequest(BaseModel):
    credential: str  # Google ID token
    return_to: Optional[str] = None

class AuthUser(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    is_profile_complete: bool = False

class ProfileCompletionStatus(BaseModel):
    is_complete: bool
    missing_fields: List[str] = []
    reason: Optional[str] = None

class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[AuthUser] = None
    profile_completion: Optional[ProfileCompletionStatus] = None
    session_token: Optional[str] = None
    csrf_token: Optional[str] = None
    return_to: Optional[str] = None

class LogoutResponse(BaseModel):
    success: bool
    message: str


