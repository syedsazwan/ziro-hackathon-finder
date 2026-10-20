import asyncio
import datetime
import sqlite3
import urllib.parse
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, Query, HTTPException, status, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.database import get_db, init_db, get_connection
from app.config import (
    CORS_ORIGINS,
    APP_ORIGIN,
    BACKEND_ORIGIN,
    SESSION_COOKIE_NAME,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    SESSION_DURATION_DAYS,
)
from app.schemas import (
    HealthResponse,
    EventsListResponse,
    EventResponse,
    EligibilityResult,
    EligibilityCheckRequest,
    RefreshSourcesResponse,
    SourceSummary,
    DiscoveryMetadata,
    RegistrationActionCreate,
    RegistrationApproveRequest,
    RegistrationSubmitRequest,
    RegistrationVerifyRequest,
    RegistrationCancelRequest,
    RegistrationActionResponse,
    RegistrationActionDetailResponse,
    RegistrationListResponse,
    AuditLogResponse,
    AuditLogListResponse,
    StudentProfilePayload,
    StudentProfileResponse,
    AdapterStatusListResponse,
    NotificationPreferencesPayload,
    NotificationPreferencesResponse,
    NotificationItemResponse,
    NotificationListResponse,
    DeadlineGroupItem,
    DeadlineSummaryResponse,
    GoogleAuthUrlResponse,
    GoogleVerifyRequest,
    AuthUser,
    AuthStatusResponse,
    LogoutResponse,
    ProfileCompletionStatus,
)
from app.auth_service import (
    generate_google_auth_url,
    verify_and_consume_state,
    exchange_code_for_tokens,
    verify_google_id_token,
    get_or_create_user_from_google,
    create_user_session,
    get_session_user,
    destroy_user_session,
    evaluate_profile_completion,
    AuthError,
    MissingOAuthConfigError,
    InvalidStateError,
    TokenVerificationError,
)
from app.utils import convert_to_ist, calculate_eligibility
from app.normalization import is_deadline_expired, parse_date_range_string, is_date_in_past
from app.event_service import refresh_events_from_sources, get_adapter_statuses
from app.adapters import get_all_adapters
from app.registration_service import (
    create_registration_action,
    approve_registration_action,
    simulate_submission,
    verify_registration,
    cancel_registration_action,
    get_registration_action,
    list_registration_actions,
    get_recent_audit_logs,
    EventNotFoundError,
    DuplicateActionError,
    ActionNotFoundError,
    ApprovalRequiredError,
    InvalidStateTransitionError,
)
from app.notification_service import (
    get_notification_preferences,
    save_notification_preferences,
    get_user_notifications,
    mark_notification_read,
    mark_all_notifications_read,
    get_deadline_groups,
    evaluate_and_generate_notifications,
)

async def periodic_notification_worker():
    """Background worker that periodically re-evaluates upcoming deadlines and matching events."""
    while True:
        try:
            await asyncio.sleep(600)  # Every 10 minutes
            conn = get_connection()
            try:
                evaluate_and_generate_notifications(conn)
            finally:
                conn.close()
        except asyncio.CancelledError:
            break
        except Exception:
            # Continue running resiliently
            pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist on startup (no synthetic seeding)
    init_db()
    # Initial evaluation of upcoming deadlines
    init_conn = get_connection()
    try:
        evaluate_and_generate_notifications(init_conn)
    finally:
        init_conn.close()

    worker_task = asyncio.create_task(periodic_notification_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Hackathon & Contest Finder API",
    description="Backend API for discovering hackathons and contests with eligibility checks, IST timezone conversion, and safe registration workflow.",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Authentication Dependencies & Session Management
# ---------------------------------------------------------

def get_current_user_optional(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    """
    Extracts and validates active session identifier from:
    1. HTTP-only cookie (SESSION_COOKIE_NAME)
    2. Authorization: Bearer <session_id>
    3. X-Session-ID header
    Returns user dict with session details or None if unauthenticated.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_id = auth_header[7:].strip()
    if not session_id:
        session_id = request.headers.get("X-Session-ID")

    if not session_id:
        return None

    return get_session_user(conn, session_id)


def get_current_user(
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
) -> Dict[str, Any]:
    """Enforces authentication: raises HTTP 401 if request has no valid session."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with Google.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ---------------------------------------------------------
# Authentication & Google OAuth Endpoints
# ---------------------------------------------------------

@app.get(
    "/api/auth/google/url",
    response_model=GoogleAuthUrlResponse,
    summary="Initiate Google OAuth 2.0 / OpenID Connect authorization code flow"
)
def get_google_auth_url_endpoint(
    request: Request,
    return_to: Optional[str] = Query(None, description="Optional relative destination after login"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Generates a cryptographically secure Google OAuth authorization URL
    with one-time state and nonce stored in backend for CSRF and replay protection.
    """
    try:
        calling_origin = None
        origin_header = request.headers.get("origin") or request.headers.get("referer")
        if origin_header:
            parsed = urllib.parse.urlparse(origin_header)
            cand = f"{parsed.scheme}://{parsed.netloc}"
            if cand in CORS_ORIGINS:
                calling_origin = cand

        auth_url = generate_google_auth_url(conn, return_to=return_to, client_origin=calling_origin)
        return GoogleAuthUrlResponse(url=auth_url)
    except MissingOAuthConfigError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    "/api/auth/google/callback",
    summary="Handle Google OAuth 2.0 authorization code callback"
)
async def google_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Backend callback handler:
    1. Validates one-time state token to prevent login CSRF.
    2. Exchanges authorization code with Google token endpoint.
    3. Validates ID token signature, issuer, audience, expiry, and nonce.
    4. Identifies or creates user via stable Google sub claim without fabricating profile data.
    5. Sets secure HTTP-only session cookie.
    6. Appends session_token to redirect URL for cross-site bearer token resiliency.
    7. Redirects new or incomplete profiles to My Profile with onboarding banner.
    """
    login_url = f"{APP_ORIGIN}/login"

    if error:
        err_msg = error_description or error or "Google authentication was cancelled or denied."
        return RedirectResponse(url=f"{login_url}?error={urllib.parse.quote(err_msg)}", status_code=303)

    if not code or not state:
        return RedirectResponse(
            url=f"{login_url}?error={urllib.parse.quote('Invalid authorization callback parameters.')}",
            status_code=303
        )

    try:
        state_record = verify_and_consume_state(conn, state)
    except InvalidStateError:
        return RedirectResponse(
            url=f"{login_url}?error={urllib.parse.quote('Invalid or expired login session state. Please retry sign-in.')}",
            status_code=303
        )

    try:
        tokens = await exchange_code_for_tokens(code)
        raw_id_token = tokens.get("id_token")
        if not raw_id_token:
            return RedirectResponse(
                url=f"{login_url}?error={urllib.parse.quote('Google token exchange did not return an ID token.')}",
                status_code=303
            )
        claims = verify_google_id_token(raw_id_token, expected_nonce=state_record.get("nonce"))
    except AuthError as e:
        return RedirectResponse(url=f"{login_url}?error={urllib.parse.quote(e.message)}", status_code=303)
    except Exception as e:
        return RedirectResponse(
            url=f"{login_url}?error={urllib.parse.quote(f'Authentication verification failed: {str(e)}')}",
            status_code=303
        )

    user, is_new = get_or_create_user_from_google(conn, claims)
    session_id, _ = create_user_session(conn, user["id"])

    # Determine destination:
    # If profile is incomplete -> always My Profile with onboarding prompt
    target_origin = state_record.get("client_origin") or APP_ORIGIN
    target_path = state_record.get("return_to") or "/events"
    if not user["is_profile_complete"]:
        target_path = "/profile?onboarding=1"

    separator = "&" if "?" in target_path else "?"
    redirect_url = f"{target_origin}{target_path}{separator}session_token={session_id}"
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=SESSION_DURATION_DAYS * 86400,
        path="/",
    )
    return response


@app.post(
    "/api/auth/google/verify",
    response_model=AuthStatusResponse,
    summary="Direct Google ID token verification (Google Identity Services / OneTap)"
)
def verify_google_credential_endpoint(
    payload: GoogleVerifyRequest,
    response: Response,
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Directly validates a Google ID token provided by Google Identity Services.
    Validates token signature, issuer, audience, expiry on backend and establishes a session.
    """
    try:
        claims = verify_google_id_token(payload.credential)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Google validation failed: {str(e)}")

    user, is_new = get_or_create_user_from_google(conn, claims)
    session_id, _ = create_user_session(conn, user["id"])

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=SESSION_DURATION_DAYS * 86400,
        path="/",
    )

    safe_return_to = None
    if payload.return_to and payload.return_to.startswith("/") and not payload.return_to.startswith("//"):
        safe_return_to = payload.return_to

    missing_fields = []
    if not user["is_profile_complete"]:
        missing_fields = ["institution", "degree", "graduation_year", "skills"]

    return AuthStatusResponse(
        authenticated=True,
        user=AuthUser(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            picture=user["picture"],
            is_profile_complete=user["is_profile_complete"],
        ),
        profile_completion=ProfileCompletionStatus(
            is_complete=user["is_profile_complete"],
            missing_fields=missing_fields,
            reason=None if user["is_profile_complete"] else "Please complete required profile fields to access all features of Ziro.",
        ),
        session_token=session_id,
        return_to=safe_return_to,
    )


@app.get(
    "/api/auth/me",
    response_model=AuthStatusResponse,
    summary="Get active authenticated user identity and profile onboarding status"
)
def get_current_user_me(
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Returns the authenticated identity of the current session or unauthenticated status."""
    if not user:
        return AuthStatusResponse(
            authenticated=False,
            user=None,
            profile_completion=None,
            session_token=None,
        )

    # Re-evaluate profile completion based on database profile record
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM student_profiles WHERE user_id = ? ORDER BY id DESC LIMIT 1;", (user["user_id"],))
    p_row = cursor.fetchone()
    is_complete = False
    missing_fields = []

    if p_row:
        p_dict = dict(p_row)
        skills_list = [s.strip() for s in (p_row["skills"] or "").split(",") if s.strip()]
        p_dict["skills"] = skills_list
        is_complete = evaluate_profile_completion(p_dict)
        if not is_complete:
            if not p_dict.get("student_name") or not str(p_dict.get("student_name")).strip():
                missing_fields.append("student_name")
            if not p_dict.get("student_email") or not str(p_dict.get("student_email")).strip():
                missing_fields.append("student_email")
            if not p_dict.get("institution") or not str(p_dict.get("institution")).strip():
                missing_fields.append("institution")
            if not p_dict.get("degree") or not str(p_dict.get("degree")).strip():
                missing_fields.append("degree")
            if not p_dict.get("graduation_year") or not str(p_dict.get("graduation_year")).strip():
                missing_fields.append("graduation_year")
            if not skills_list:
                missing_fields.append("skills")
    else:
        missing_fields = ["student_name", "student_email", "institution", "degree", "graduation_year", "skills"]

    # Keep users.is_profile_complete in sync
    if is_complete != user["is_profile_complete"]:
        cursor.execute("UPDATE users SET is_profile_complete = ? WHERE id = ?;", (1 if is_complete else 0, user["user_id"]))
        conn.commit()

    return AuthStatusResponse(
        authenticated=True,
        user=AuthUser(
            id=user["user_id"],
            email=user["email"],
            name=user["name"],
            picture=user["picture"],
            is_profile_complete=is_complete,
        ),
        profile_completion=ProfileCompletionStatus(
            is_complete=is_complete,
            missing_fields=missing_fields,
            reason=None if is_complete else "Please complete required profile fields to access all features of Ziro.",
        ),
        session_token=user["session_id"],
    )


@app.post(
    "/api/auth/logout",
    response_model=LogoutResponse,
    summary="Invalidate active session and clear session cookie"
)
def logout_endpoint(
    response: Response,
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Terminates session on backend and clears client HTTP-only cookie."""
    if user and user.get("session_id"):
        destroy_user_session(conn, user["session_id"])

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
    )
    return LogoutResponse(success=True, message="Successfully signed out of Ziro.")


# ---------------------------------------------------------
# Stage 1: Health & Event Discovery Endpoints
# ---------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health_check(conn: sqlite3.Connection = Depends(get_db)):
    """Health check endpoint verifying database connectivity."""
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    cursor.fetchone()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        database="connected",
        version="2.0.0"
    )

@app.get("/api/events", response_model=EventsListResponse)
def list_events(
    skills: Optional[str] = Query(None, description="Comma-separated student skills"),
    team_size: int = Query(1, ge=1, description="Student team size"),
    region: Optional[str] = Query(None, description="Preferred region"),
    country: Optional[str] = Query(None, description="Preferred country (e.g. 'India', 'United States')"),
    event_format: Optional[str] = Query(None, description="Event format ('Online / Virtual', 'In-Person', 'Hybrid')"),
    start_date: Optional[str] = Query(None, description="Availability start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Availability end date (YYYY-MM-DD)"),
    budget: Optional[float] = Query(None, ge=0.0, description="Max budget for registration fee"),
    source: Optional[str] = Query(None, description="Filter by event source name (e.g. 'Devfolio', 'MLH', 'Devpost', 'Unstop')"),
    status_filter: Optional[str] = Query(None, alias="status", description="Event status ('upcoming', 'closed', 'all')"),
    search: Optional[str] = Query(None, alias="q", description="Keyword or title search query"),
    live_search: bool = Query(False, description="When true, triggers real-time public source discovery using criteria"),
    include_synthetic: bool = Query(False, description="Whether to include synthetic demo fixtures"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Returns events enriched with eligibility evaluation, IST timezone conversion,
    and provenance metadata. Safely distinguishes real discovered events from synthetic demo fixtures.
    When live_search=true, queries authorized public internet sources (Devfolio, MLH, Devpost, Unstop)
    using the student's selected criteria, normalizes and persists candidates, and returns matched results.
    """
    parsed_skills: List[str] = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
    discovery_meta: Optional[DiscoveryMetadata] = None

    if live_search:
        criteria = {
            "skills": parsed_skills,
            "team_size": team_size,
            "region": region,
            "country": country,
            "event_format": event_format,
            "budget": budget,
            "status": status_filter,
            "query": search,
        }
        try:
            refresh_report = refresh_events_from_sources(
                conn,
                source_name=source,
                limit_per_source=15,
                criteria=criteria,
            )
            raw_summaries = refresh_report.get("sources_summary", [])
            sources_summary = [SourceSummary(**s) for s in raw_summaries]
            total_cand = sum(s.events_fetched for s in sources_summary if s.status == "success")
            discovery_meta = DiscoveryMetadata(
                sources_searched=len(sources_summary),
                sources_available=len([s for s in sources_summary if s.status == "success"]),
                sources_summary=sources_summary,
                total_candidates_retrieved=total_cand,
                total_discovered=refresh_report.get("total_discovered", 0),
                total_inserted=refresh_report.get("total_inserted", 0),
                total_updated=refresh_report.get("total_updated", 0),
                total_skipped=refresh_report.get("total_skipped", 0),
                total_failed=refresh_report.get("total_failed", 0),
                fresh_count=refresh_report.get("total_discovered", 0) + refresh_report.get("total_updated", 0),
                cached_count=0,
                sync_status=refresh_report.get("sync_status", "success"),
                search_criteria_used=criteria,
            )
        except Exception as e:
            discovery_meta = DiscoveryMetadata(
                sources_searched=1,
                sources_available=0,
                sources_summary=[
                    SourceSummary(
                        source_name=source or "Public Sources",
                        status="error",
                        events_fetched=0,
                        events_discovered=0,
                        events_inserted=0,
                        events_updated=0,
                        events_skipped=0,
                        events_failed=1,
                        events_upserted=0,
                        notes="Live discovery query encountered a runtime error.",
                        error_message=str(e),
                    )
                ],
                total_candidates_retrieved=0,
                total_discovered=0,
                total_inserted=0,
                total_updated=0,
                total_skipped=0,
                total_failed=1,
                fresh_count=0,
                cached_count=0,
                sync_status="error",
                search_criteria_used=criteria,
            )

    cursor = conn.cursor()
    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if not include_synthetic:
        query += " AND is_synthetic = 0"

    if source and source.lower() not in ("all", "*", ""):
        query += " AND LOWER(source_name) = ?"
        params.append(source.strip().lower())

    if country and country.lower() not in ("all", "any", ""):
        c_lower = country.strip().lower()
        if c_lower in ("global / online", "global", "online"):
            query += " AND (LOWER(region) LIKE '%global%' OR LOWER(region) LIKE '%online%' OR LOWER(format) LIKE '%online%')"
        else:
            query += " AND (LOWER(country) = ? OR LOWER(region) = ? OR LOWER(country) LIKE ?)"
            params.extend([c_lower, c_lower, f"%{c_lower}%"])
    elif region and region.lower() not in ("all", "any", ""):
        r_lower = region.strip().lower()
        if r_lower in ("global / online", "global", "online"):
            query += " AND (LOWER(region) LIKE '%global%' OR LOWER(region) LIKE '%online%')"
        else:
            query += " AND LOWER(region) LIKE ?"
            params.append(f"%{r_lower}%")

    if event_format and event_format.lower() not in ("all", "any", ""):
        query += " AND LOWER(format) LIKE ?"
        params.append(f"%{event_format.lower()}%")

    if search and search.strip():
        q_term = f"%{search.strip().lower()}%"
        query += " AND (LOWER(title) LIKE ? OR LOWER(organizer) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(description) LIKE ? OR LOWER(location) LIKE ?)"
        params.extend([q_term, q_term, q_term, q_term, q_term])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    parsed_skills: List[str] = [s.strip() for s in skills.split(",") if s.strip()] if skills else []

    event_responses: List[EventResponse] = []
    for row in rows:
        row_keys = row.keys()
        tags_list = [t.strip() for t in row["tags"].split(",") if t.strip()]
        
        # Read start & end dates (parse from deadline_notes if not explicitly saved)
        start_dt = row["start_date"] if "start_date" in row_keys and row["start_date"] else None
        end_dt = row["end_date"] if "end_date" in row_keys and row["end_date"] else None
        dl_notes = row["deadline_notes"] if "deadline_notes" in row_keys and row["deadline_notes"] else ""
        if (not start_dt or not end_dt) and dl_notes:
            s_parsed, e_parsed = parse_date_range_string(dl_notes)
            start_dt = start_dt or s_parsed
            end_dt = end_dt or e_parsed

        # Safe Deadline Conversion to IST
        raw_dl = row["deadline"]
        if raw_dl and str(raw_dl).strip():
            deadline_ist, deadline_ist_formatted = convert_to_ist(str(raw_dl), row["timezone"])
            deadline_expired = is_deadline_expired(deadline_ist)
        else:
            deadline_ist = None
            deadline_ist_formatted = None
            deadline_expired = False

        # Format start & end dates
        _, start_date_ist_formatted = convert_to_ist(start_dt, row["timezone"]) if start_dt else (None, None)
        _, end_date_ist_formatted = convert_to_ist(end_dt, row["timezone"]) if end_dt else (None, None)

        # Detect concluded/ended event accurately from official dates, deadline notes, or explicit status
        explicit_dl_status = row["deadline_status"] if "deadline_status" in row_keys and row["deadline_status"] else None
        is_past_event = (end_dt is not None and is_date_in_past(end_dt)) or explicit_dl_status == "closed" or deadline_expired

        if is_past_event:
            deadline_status = "closed"
            deadline_expired = True
            if not deadline_ist_formatted or deadline_ist_formatted == "Deadline Unavailable":
                deadline_ist_formatted = "Registration Closed"
        elif explicit_dl_status:
            deadline_status = explicit_dl_status
        elif raw_dl:
            deadline_status = "verified"
        else:
            deadline_status = "unavailable"

        deadline_notes = dl_notes or (row["deadline_notes"] if "deadline_notes" in row_keys else None)
        country_val = row["country"] if "country" in row_keys else None
        prize_info = row["prize_info"] if "prize_info" in row_keys else None
        verification_status = row["verification_status"] if "verification_status" in row_keys else ("needs_verification" if row["fee_status"] == "unknown" or deadline_status in ("unavailable", "unverified") else "verified")
        evidence_notes = row["evidence_notes"] if "evidence_notes" in row_keys else None
        is_synthetic = bool(row["is_synthetic"]) if "is_synthetic" in row_keys else (row["data_source_type"] == "synthetic_demo_fixture")

        # Apply status filtering (defaults to 'upcoming' so ended/closed events are excluded from default feed)
        sf_clean = (status_filter or "upcoming").strip().lower()
        if sf_clean == "upcoming":
            if deadline_expired or deadline_status == "closed" or is_past_event:
                continue
        elif sf_clean in ("closed", "ended", "past"):
            if not (deadline_expired or deadline_status == "closed" or is_past_event):
                continue
        # If sf_clean == "all", include all events (both upcoming and closed)

        # Calculate eligibility with strict ended, unlisted-cutoff, and verification enforcement
        eligibility_data = calculate_eligibility(
            team_min=row["team_min"],
            team_max=row["team_max"],
            fee_status=row["fee_status"],
            fee_amount=row["fee_amount"],
            team_size=team_size,
            budget=budget,
            skills=parsed_skills,
            event_tags=tags_list,
            region=region,
            event_region=row["region"],
            deadline_status=deadline_status,
            is_deadline_expired=deadline_expired,
            verification_status=verification_status,
            event_end_date=end_dt,
            is_closed=(deadline_status == "closed"),
        )

        # Read provenance & normalization fields safely
        source_name = row["source_name"] if "source_name" in row_keys else "Synthetic"
        source_event_id = row["source_event_id"] if "source_event_id" in row_keys else None
        registration_url = row["registration_url"] if "registration_url" in row_keys else None
        location = row["location"] if "location" in row_keys else ("Online" if "Online" in row["format"] else "In-Person")
        eligibility_reqs = row["eligibility_requirements"] if "eligibility_requirements" in row_keys else "Open to eligible participants"

        # Determine cache status vs fresh discovery
        retrieved_at_val = row["retrieved_at"] if "retrieved_at" in row_keys and row["retrieved_at"] else ""
        is_fresh = False
        if retrieved_at_val:
            try:
                dt_retrieved = datetime.datetime.fromisoformat(retrieved_at_val.replace("Z", "+00:00"))
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                if (now_dt - dt_retrieved).total_seconds() < 3600:
                    is_fresh = True
            except Exception:
                pass
        cache_status = "fresh" if is_fresh else "cached"
        is_cached = not is_fresh

        event_responses.append(
            EventResponse(
                id=row["id"],
                title=row["title"],
                description=row["description"],
                organizer=row["organizer"],
                source_name=source_name,
                source_event_id=source_event_id,
                source_url=row["source_url"],
                registration_url=registration_url,
                retrieved_at=row["retrieved_at"],
                team_min=row["team_min"],
                team_max=row["team_max"],
                fee_amount=row["fee_amount"],
                fee_currency=row["fee_currency"],
                fee_status=row["fee_status"],
                deadline=raw_dl if (raw_dl and str(raw_dl).strip()) else None,
                timezone=row["timezone"],
                deadline_ist=deadline_ist,
                deadline_ist_formatted=deadline_ist_formatted,
                deadline_status=deadline_status,
                deadline_notes=deadline_notes,
                is_deadline_expired=deadline_expired,
                start_date=start_dt,
                end_date=end_dt,
                start_date_ist_formatted=start_date_ist_formatted,
                end_date_ist_formatted=end_date_ist_formatted,
                location=location,
                format=row["format"],
                eligibility_requirements=eligibility_reqs,
                verification_status=verification_status,
                evidence_notes=evidence_notes,
                is_synthetic=is_synthetic,
                data_source_type=row["data_source_type"],
                tags=tags_list,
                region=row["region"],
                country=country_val,
                prize_info=prize_info,
                eligibility=EligibilityResult(**eligibility_data),
                is_cached=is_cached,
                last_synced_at=row["retrieved_at"],
                cache_status=cache_status,
            )
        )

    # Populate discovery metadata if not already generated by live_search
    if discovery_meta is None:
        all_ad = get_all_adapters()
        cached_sources: List[SourceSummary] = []
        for ad in all_ad:
            cursor.execute("""
                SELECT status, events_fetched, events_upserted, notes, error_message, synced_at
                FROM adapter_sync_logs WHERE LOWER(source_name) = ?
                ORDER BY id DESC LIMIT 1;
            """, (ad.source_name.lower(),))
            s_row = cursor.fetchone()
            if s_row:
                cached_sources.append(SourceSummary(
                    source_name=ad.source_name,
                    status=s_row[0],
                    events_fetched=s_row[1] or 0,
                    events_upserted=s_row[2] or 0,
                    last_synced_at=s_row[5],
                    notes=s_row[3] or "",
                    error_message=s_row[4],
                ))
            else:
                cached_sources.append(SourceSummary(
                    source_name=ad.source_name,
                    status="restricted" if not ad.is_available() else "idle",
                    events_fetched=0,
                    notes=ad.get_limitations(),
                    error_message=None if ad.is_available() else ad.get_limitations(),
                ))
        cached_count_val = sum(1 for e in event_responses if e.is_cached)
        fresh_count_val = sum(1 for e in event_responses if not e.is_cached)
        has_success = any(s.status == "success" for s in cached_sources)
        has_restricted = any(s.status == "restricted" for s in cached_sources)
        cached_sync_status = "partial_success" if (has_success and has_restricted) else ("success" if has_success else "idle")
        discovery_meta = DiscoveryMetadata(
            sources_searched=len(cached_sources),
            sources_available=len([s for s in cached_sources if s.status == "success"]),
            sources_summary=cached_sources,
            total_candidates_retrieved=len(event_responses),
            total_discovered=0,
            total_inserted=0,
            total_updated=0,
            total_skipped=0,
            total_failed=0,
            fresh_count=fresh_count_val,
            cached_count=cached_count_val,
            sync_status=cached_sync_status,
            search_criteria_used={
                "skills": parsed_skills,
                "team_size": team_size,
                "region": region,
                "country": country,
                "event_format": event_format,
                "budget": budget,
                "status": status_filter,
                "query": search,
            },
        )

    return EventsListResponse(
        total=len(event_responses),
        filter_applied={
            "skills": parsed_skills,
            "team_size": team_size,
            "region": region,
            "country": country,
            "event_format": event_format,
            "start_date": start_date,
            "end_date": end_date,
            "budget": budget,
            "source": source,
            "status": status_filter,
            "search": search,
            "include_synthetic": include_synthetic,
        },
        events=event_responses,
        discovery_metadata=discovery_meta,
    )

@app.post(
    "/api/events/refresh",
    response_model=RefreshSourcesResponse,
    summary="Manual refresh of permitted public event sources"
)
def refresh_events(
    source: Optional[str] = Query(None, description="Specific source to refresh ('devfolio', 'mlh', 'devpost', 'unstop') or omit for all"),
    limit_per_source: int = Query(10, ge=1, le=50, description="Max events to fetch per adapter"),
    skills: Optional[str] = Query(None, description="Comma-separated student skills to drive targeted discovery"),
    event_format: Optional[str] = Query(None, description="Event format ('Online / Virtual', 'In-Person', 'Hybrid')"),
    status_filter: Optional[str] = Query(None, alias="status", description="Event status ('upcoming', 'closed', 'all')"),
    search: Optional[str] = Query(None, alias="q", description="Keyword or title search query"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Manually triggers permitted public source ingestion driven by student criteria.
    SAFE DESIGN:
    - Never runs on startup or as an unmonitored background loop.
    - Only queries permitted public endpoints.
    - Does not bypass restricted sources (reports clear limitation status).
    - Preserves existing registration actions and audit records.
    """
    criteria = {
        "skills": [s.strip() for s in skills.split(",") if s.strip()] if skills else [],
        "event_format": event_format,
        "status": status_filter,
        "query": search,
    }
    try:
        report = refresh_events_from_sources(
            conn,
            source_name=source,
            limit_per_source=limit_per_source,
            criteria=criteria,
        )
        return report
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post(
    "/api/eligibility/check",
    response_model=EligibilityResult,
    summary="Direct eligibility calculation for student profile"
)
def check_eligibility(
    payload: EligibilityCheckRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Evaluates eligibility constraints for given parameters or an existing event ID.
    Enforces that unknown fee status and uncertain eligibility require verification.
    """
    team_min = payload.team_min or 1
    team_max = payload.team_max or 20
    fee_status = payload.fee_status or "free"
    fee_amount = payload.fee_amount
    event_tags = payload.event_tags
    event_region = payload.event_region
    deadline_status = None
    is_deadline_expired_val = False
    verification_status = None
    event_end_date = None

    if payload.event_id is not None:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT team_min, team_max, fee_status, fee_amount, tags, region,
                   deadline, timezone, deadline_status, is_synthetic,
                   verification_status, start_date, end_date, deadline_notes
            FROM events WHERE id = ?
        """, (payload.event_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {payload.event_id} not found.")
        team_min = row["team_min"]
        team_max = row["team_max"]
        fee_status = row["fee_status"]
        fee_amount = row["fee_amount"]
        event_tags = [t.strip() for t in row["tags"].split(",") if t.strip()]
        event_region = row["region"]
        raw_dl = row["deadline"]
        tz = row["timezone"]
        end_date = row["end_date"]
        dl_notes = row["deadline_notes"] or ""
        if not end_date and dl_notes:
            _, end_date = parse_date_range_string(dl_notes)
        event_end_date = end_date

        if raw_dl and str(raw_dl).strip():
            dl_ist, _ = convert_to_ist(str(raw_dl), tz)
            is_deadline_expired_val = is_deadline_expired(dl_ist)

        explicit_status = row["deadline_status"] or "verified"
        if (event_end_date and is_date_in_past(event_end_date)) or explicit_status == "closed" or is_deadline_expired_val:
            deadline_status = "closed"
            is_deadline_expired_val = True
        else:
            deadline_status = explicit_status

        verification_status = row["verification_status"]

    result = calculate_eligibility(
        team_min=team_min,
        team_max=team_max,
        fee_status=fee_status,
        fee_amount=fee_amount,
        team_size=payload.team_size,
        budget=payload.budget,
        skills=payload.skills,
        event_tags=event_tags,
        region=payload.region,
        event_region=event_region,
        deadline_status=deadline_status,
        is_deadline_expired=is_deadline_expired_val,
        verification_status=verification_status,
        event_end_date=event_end_date,
        is_closed=(deadline_status == "closed"),
    )
    return EligibilityResult(**result)

# ---------------------------------------------------------
# Stage 2: Safe Registration Workflow Endpoints
# ---------------------------------------------------------

@app.post(
    "/api/registrations",
    response_model=RegistrationActionDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a demo registration action"
)
def request_registration(
    data: RegistrationActionCreate,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Creates a new registration action in 'pending_approval' status.
    Enforces uniqueness per (event_id, student_email) to prevent duplicate submissions.
    """
    try:
        action = create_registration_action(conn, data)
        return action
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DuplicateActionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(e),
                "existing_action_id": e.action_id,
                "status": e.status,
                "event_id": e.event_id,
                "student_email": e.student_email,
            }
        )

@app.post(
    "/api/registrations/{action_id}/approve",
    response_model=RegistrationActionDetailResponse,
    summary="Explicit human approval for registration"
)
def approve_registration(
    action_id: str,
    data: RegistrationApproveRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Records explicit human approval. Transitions status from 'pending_approval' to 'approved'.
    """
    try:
        updated = approve_registration_action(conn, action_id, data)
        return updated
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post(
    "/api/registrations/{action_id}/submit",
    response_model=RegistrationActionDetailResponse,
    summary="Simulate registration submission"
)
def submit_registration_simulation(
    action_id: str,
    data: RegistrationSubmitRequest = RegistrationSubmitRequest(),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Executes a simulated submission.
    REQUIREMENT: Blocked if human approval has not been granted ('pending_approval').
    CRITICAL: Registrations are NEVER marked 'confirmed' upon submission.
    """
    try:
        updated = simulate_submission(conn, action_id, data)
        return updated
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ApprovalRequiredError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except (InvalidStateTransitionError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.post(
    "/api/registrations/{action_id}/verify",
    response_model=RegistrationActionDetailResponse,
    summary="Record manual verification outcome"
)
def verify_registration_outcome(
    action_id: str,
    data: RegistrationVerifyRequest,
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Records an explicit manual verification result with evidence notes.
    Allowed only after submission attempt has occurred.
    """
    try:
        updated = verify_registration(conn, action_id, data)
        return updated
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get(
    "/api/registrations/{action_id}",
    response_model=RegistrationActionDetailResponse,
    summary="Get registration action status and audit trail"
)
def get_registration(
    action_id: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Retrieves full details of a registration action including its complete audit history."""
    action = get_registration_action(conn, action_id)
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration action '{action_id}' not found."
        )
    return action

@app.get(
    "/api/registrations",
    response_model=RegistrationListResponse,
    summary="List registration actions"
)
def list_registrations(
    event_id: Optional[int] = Query(None, description="Filter by event ID"),
    student_email: Optional[str] = Query(None, description="Filter by student email"),
    status: Optional[str] = Query(None, description="Filter by action status"),
    include_synthetic: bool = Query(False, description="Filter by synthetic demo fixture status (defaults to False for genuine records only)"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Lists registration actions matching filter parameters."""
    actions = list_registration_actions(
        conn,
        event_id=event_id,
        student_email=student_email,
        status=status,
        include_synthetic=include_synthetic,
    )
    return RegistrationListResponse(
        total=len(actions),
        actions=actions,
    )

@app.post(
    "/api/registrations/{action_id}/cancel",
    response_model=RegistrationActionDetailResponse,
    summary="Cancel a registration action"
)
def cancel_registration(
    action_id: str,
    payload: RegistrationCancelRequest = RegistrationCancelRequest(),
    conn: sqlite3.Connection = Depends(get_db),
):
    """
    Cancels an active registration action.
    Allowed from 'pending_approval', 'approved', or 'needs_manual_verification'.
    Terminal states ('confirmed', 'failed', 'cancelled') cannot be cancelled.
    """
    try:
        updated = cancel_registration_action(
            conn,
            action_id=action_id,
            reason=payload.reason,
            actor=payload.actor,
        )
        return updated
    except ActionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# ---------------------------------------------------------
# Stage 4C: Audit History & Adapter Status Endpoints
# ---------------------------------------------------------

@app.get(
    "/api/audit-logs",
    response_model=AuditLogListResponse,
    summary="Get recent audit logs across all registration actions"
)
def get_audit_logs(
    limit: int = Query(50, ge=1, le=100, description="Max logs to return"),
    action_id: Optional[str] = Query(None, description="Filter logs for a specific action ID"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Retrieves recent append-only audit trail logs from registration actions."""
    if action_id:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, action_id, from_status, to_status, actor, event_type, details, created_at
        FROM registration_audit_logs
        WHERE action_id = ?
        ORDER BY id DESC
        LIMIT ?;
        """, (action_id, limit))
        rows = cursor.fetchall()
        logs = [dict(r) for r in rows]
    else:
        logs = get_recent_audit_logs(conn, limit=limit)

    return AuditLogListResponse(
        total=len(logs),
        logs=[AuditLogResponse(**log) for log in logs],
    )

@app.get(
    "/api/adapters/status",
    response_model=AdapterStatusListResponse,
    summary="Get real status and sync history for all event sources"
)
def get_sources_status(conn: sqlite3.Connection = Depends(get_db)):
    """
    Returns actual adapter status, access compliance mechanisms,
    last refresh timestamp, and event counts from the database.
    """
    statuses = get_adapter_statuses(conn)
    return AdapterStatusListResponse(adapters=statuses)

# ---------------------------------------------------------
# Stage 4C: Persisted Student Profile Endpoints
# ---------------------------------------------------------

@app.get(
    "/api/profile",
    response_model=StudentProfileResponse,
    summary="Retrieve persisted student profile data"
)
def get_student_profile(
    conn: sqlite3.Connection = Depends(get_db),
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Retrieves the persisted student profile from the backend database.
    If authenticated, returns the user's isolated profile.
    Returns defaults if no profile record exists yet.
    """
    cursor = conn.cursor()
    row = None
    if user:
        cursor.execute("""
        SELECT student_name, student_email, skills, team_size, region, start_date, end_date, budget,
               institution, degree, graduation_year, github_url, linkedin_url, portfolio_url, bio,
               collaboration_preference, projects_json, participation_mode, updated_at
        FROM student_profiles
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1;
        """, (user["user_id"],))
        row = cursor.fetchone()
        if not row:
            # Check if there is an unassigned legacy profile to associate safely
            cursor.execute("""
            SELECT id, student_name, student_email, skills, team_size, region, start_date, end_date, budget,
                   institution, degree, graduation_year, github_url, linkedin_url, portfolio_url, bio,
                   collaboration_preference, projects_json, participation_mode, updated_at
            FROM student_profiles
            WHERE user_id IS NULL
            ORDER BY id ASC LIMIT 1;
            """)
            unassigned = cursor.fetchone()
            if unassigned:
                cursor.execute("UPDATE student_profiles SET user_id = ? WHERE id = ?;", (user["user_id"], unassigned["id"]))
                conn.commit()
                row = unassigned

    if not row:
        cursor.execute("""
        SELECT student_name, student_email, skills, team_size, region, start_date, end_date, budget,
               institution, degree, graduation_year, github_url, linkedin_url, portfolio_url, bio,
               collaboration_preference, projects_json, participation_mode, updated_at
        FROM student_profiles
        ORDER BY id DESC LIMIT 1;
        """)
        row = cursor.fetchone()

    if row and ((row["student_email"] and row["student_email"].strip().lower() == "alex.chen@university.edu") or
                (row["student_name"] and row["student_name"].strip().lower() == "alex chen")):
        row = None

    if not row:
        return StudentProfileResponse(
            student_name=user["name"] if user else None,
            student_email=user["email"] if user else None,
            skills=[],
            team_size=2,
            region="All",
            start_date=None,
            end_date=None,
            budget=None,
            institution=None,
            degree=None,
            graduation_year=None,
            github_url=None,
            linkedin_url=None,
            portfolio_url=None,
            bio=None,
            collaboration_preference=None,
            projects_json=None,
            participation_mode="All",
            updated_at=None,
        )

    skills_list = [s.strip() for s in row["skills"].split(",") if s.strip()] if row["skills"] else []
    return StudentProfileResponse(
        student_name=row["student_name"] or (user["name"] if user else None),
        student_email=row["student_email"] or (user["email"] if user else None),
        skills=skills_list,
        team_size=row["team_size"] or 2,
        region=row["region"] or "All",
        start_date=row["start_date"],
        end_date=row["end_date"],
        budget=row["budget"],
        institution=row["institution"],
        degree=row["degree"],
        graduation_year=row["graduation_year"],
        github_url=row["github_url"],
        linkedin_url=row["linkedin_url"],
        portfolio_url=row["portfolio_url"],
        bio=row["bio"],
        collaboration_preference=row["collaboration_preference"],
        projects_json=row["projects_json"],
        participation_mode=row["participation_mode"] or "All",
        updated_at=row["updated_at"],
    )

@app.put(
    "/api/profile",
    response_model=StudentProfileResponse,
    summary="Persist student profile data to backend database"
)
def update_student_profile(
    payload: StudentProfilePayload,
    conn: sqlite3.Connection = Depends(get_db),
    user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    Persists student profile information into the SQLite database.
    Enforces real backend persistence and associates record with active user.
    """
    cursor = conn.cursor()
    skills_str = ", ".join(payload.skills) if payload.skills is not None else ""
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    existing = None
    if user:
        cursor.execute("SELECT id FROM student_profiles WHERE user_id = ? ORDER BY id DESC LIMIT 1;", (user["user_id"],))
        existing = cursor.fetchone()

    if not existing:
        cursor.execute("SELECT id FROM student_profiles ORDER BY id ASC LIMIT 1;")
        existing = cursor.fetchone()

    if existing:
        cursor.execute("""
        UPDATE student_profiles
        SET student_name = ?,
            student_email = ?,
            skills = ?,
            team_size = ?,
            region = ?,
            start_date = ?,
            end_date = ?,
            budget = ?,
            institution = ?,
            degree = ?,
            graduation_year = ?,
            github_url = ?,
            linkedin_url = ?,
            portfolio_url = ?,
            bio = ?,
            collaboration_preference = ?,
            projects_json = ?,
            participation_mode = ?,
            updated_at = ?,
            user_id = COALESCE(user_id, ?)
        WHERE id = ?;
        """, (
            payload.student_name.strip() if payload.student_name else None,
            payload.student_email.strip().lower() if payload.student_email else None,
            skills_str,
            payload.team_size,
            payload.region or "All",
            payload.start_date,
            payload.end_date,
            payload.budget,
            payload.institution.strip() if payload.institution else None,
            payload.degree.strip() if payload.degree else None,
            payload.graduation_year.strip() if payload.graduation_year else None,
            payload.github_url.strip() if payload.github_url else None,
            payload.linkedin_url.strip() if payload.linkedin_url else None,
            payload.portfolio_url.strip() if payload.portfolio_url else None,
            payload.bio.strip() if payload.bio else None,
            payload.collaboration_preference.strip() if payload.collaboration_preference else None,
            payload.projects_json.strip() if payload.projects_json else None,
            payload.participation_mode or "All",
            now_str,
            user["user_id"] if user else None,
            existing["id"],
        ))
    else:
        cursor.execute("""
        INSERT INTO student_profiles (
            user_id, student_name, student_email, skills, team_size, region, start_date, end_date, budget,
            institution, degree, graduation_year, github_url, linkedin_url, portfolio_url, bio,
            collaboration_preference, projects_json, participation_mode, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            user["user_id"] if user else None,
            payload.student_name.strip() if payload.student_name else None,
            payload.student_email.strip().lower() if payload.student_email else None,
            skills_str,
            payload.team_size,
            payload.region or "All",
            payload.start_date,
            payload.end_date,
            payload.budget,
            payload.institution.strip() if payload.institution else None,
            payload.degree.strip() if payload.degree else None,
            payload.graduation_year.strip() if payload.graduation_year else None,
            payload.github_url.strip() if payload.github_url else None,
            payload.linkedin_url.strip() if payload.linkedin_url else None,
            payload.portfolio_url.strip() if payload.portfolio_url else None,
            payload.bio.strip() if payload.bio else None,
            payload.collaboration_preference.strip() if payload.collaboration_preference else None,
            payload.projects_json.strip() if payload.projects_json else None,
            payload.participation_mode or "All",
            now_str,
        ))

    if user:
        is_complete = evaluate_profile_completion(payload.model_dump())
        cursor.execute("UPDATE users SET is_profile_complete = ? WHERE id = ?;", (1 if is_complete else 0, user["user_id"]))

    conn.commit()

    return StudentProfileResponse(
        student_name=payload.student_name.strip() if payload.student_name else None,
        student_email=payload.student_email.strip().lower() if payload.student_email else None,
        skills=payload.skills,
        team_size=payload.team_size,
        region=payload.region or "All",
        start_date=payload.start_date,
        end_date=payload.end_date,
        budget=payload.budget,
        institution=payload.institution.strip() if payload.institution else None,
        degree=payload.degree.strip() if payload.degree else None,
        graduation_year=payload.graduation_year.strip() if payload.graduation_year else None,
        github_url=payload.github_url.strip() if payload.github_url else None,
        linkedin_url=payload.linkedin_url.strip() if payload.linkedin_url else None,
        portfolio_url=payload.portfolio_url.strip() if payload.portfolio_url else None,
        bio=payload.bio.strip() if payload.bio else None,
        collaboration_preference=payload.collaboration_preference.strip() if payload.collaboration_preference else None,
        projects_json=payload.projects_json.strip() if payload.projects_json else None,
        participation_mode=payload.participation_mode or "All",
        updated_at=now_str,
    )

# ---------------------------------------------------------
# Notifications & Deadline Tracking Endpoints
# ---------------------------------------------------------

@app.get(
    "/api/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Get user notification and deadline reminder preferences"
)
def get_user_notification_prefs(
    user_email: str = Query("student@ziro.local", description="User email for preferences"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Retrieves persisted in-app notification preferences and deadline reminder intervals."""
    return get_notification_preferences(conn, user_email=user_email)

@app.put(
    "/api/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    summary="Save user notification and deadline reminder preferences"
)
def update_user_notification_prefs(
    payload: NotificationPreferencesPayload,
    user_email: str = Query("student@ziro.local", description="User email for preferences"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Persists notification and deadline reminder preferences to the backend database."""
    return save_notification_preferences(conn, user_email=user_email, payload=payload)

@app.get(
    "/api/notifications",
    response_model=NotificationListResponse,
    summary="Get user in-app notifications with unread count"
)
def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    user_email: str = Query("student@ziro.local", description="User email"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Retrieves all notifications for the user with stable deduplication and delivery timestamps."""
    return get_user_notifications(conn, user_email=user_email, limit=limit)

@app.post(
    "/api/notifications/{notification_id}/read",
    summary="Mark single notification as read"
)
def read_notification(
    notification_id: int,
    user_email: str = Query("student@ziro.local"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Marks a single notification as read."""
    success = mark_notification_read(conn, notification_id=notification_id, user_email=user_email)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "id": notification_id}

@app.post(
    "/api/notifications/read-all",
    summary="Mark all user notifications as read"
)
def read_all_user_notifications(
    user_email: str = Query("student@ziro.local"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """Marks all notifications for the user as read."""
    count = mark_all_notifications_read(conn, user_email=user_email)
    return {"status": "success", "marked_read_count": count}

@app.post(
    "/api/notifications/evaluate",
    summary="Trigger evaluation of upcoming deadlines and matching events"
)
def trigger_notification_evaluation(
    user_email: str = Query("student@ziro.local"),
    conn: sqlite3.Connection = Depends(get_db)
):
    """
    Evaluates real event deadlines in the database against user reminder preferences (7d, 48h, 24h).
    Generates new notifications if due, strictly suppressing duplicates via unique dedup keys.
    """
    new_count = evaluate_and_generate_notifications(conn, user_email=user_email)
    list_res = get_user_notifications(conn, user_email=user_email)
    return {
        "status": "success",
        "newly_generated": new_count,
        "unread_count": list_res.unread_count,
        "total_notifications": list_res.total_count,
    }

@app.get(
    "/api/events/deadlines/groups",
    response_model=DeadlineSummaryResponse,
    summary="Retrieve hackathons grouped by deadline urgency"
)
def get_deadline_categorized_events(conn: sqlite3.Connection = Depends(get_db)):
    """
    Returns events grouped into 'Due Today', 'Due Tomorrow', 'Due in the Next 7 Days',
    'Later', 'Deadline Passed', and 'Needs Verification' based on converted IST timestamps.
    """
    return get_deadline_groups(conn)


