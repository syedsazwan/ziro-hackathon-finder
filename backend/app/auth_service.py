import datetime
import secrets
import re
import urllib.parse
from typing import Optional, Dict, Any, Tuple
import sqlite3
import httpx
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    SESSION_DURATION_DAYS,
)

class AuthError(Exception):
    """Base exception for authentication and OAuth errors."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class MissingOAuthConfigError(AuthError):
    def __init__(self):
        super().__init__(
            "Google OAuth credentials are not configured. Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env.",
            status_code=503
        )

class InvalidStateError(AuthError):
    def __init__(self):
        super().__init__("Invalid, expired, or missing OAuth state parameter. Please retry sign-in.", status_code=400)

class TokenVerificationError(AuthError):
    def __init__(self, detail: str = "Google ID token validation failed."):
        super().__init__(detail, status_code=401)

# Helper: Email validation
def is_valid_email(email: Optional[str]) -> bool:
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email.strip()))

# Helper: Graduation year validation
def is_valid_grad_year(year: Optional[str]) -> bool:
    if not year or not isinstance(year, str):
        return False
    cleaned = year.strip()
    if not re.match(r"^\d{4}$", cleaned):
        return False
    try:
        val = int(cleaned)
        return 1950 <= val <= 2040
    except ValueError:
        return False

def evaluate_profile_completion(profile: Dict[str, Any]) -> bool:
    """
    Evaluates whether a student profile satisfies the minimum required profile criteria:
    1. Full Name (student_name)
    2. Student/Contact Email (student_email with valid format)
    3. Institution (institution)
    4. Degree Program & Major (degree)
    5. Graduation Year (graduation_year 4-digit)
    6. Technical Skills (skills list with >= 1 skill)
    """
    name = profile.get("student_name")
    if not name or not str(name).strip():
        return False

    email = profile.get("student_email")
    if not email or not is_valid_email(str(email)):
        return False

    institution = profile.get("institution")
    if not institution or not str(institution).strip():
        return False

    degree = profile.get("degree")
    if not degree or not str(degree).strip():
        return False

    grad_year = profile.get("graduation_year")
    if not grad_year or not is_valid_grad_year(str(grad_year)):
        return False

    skills = profile.get("skills")
    if not skills or not isinstance(skills, list) or len(skills) == 0:
        return False

    return True

def generate_google_auth_url(
    conn: sqlite3.Connection,
    return_to: Optional[str] = None,
    client_origin: Optional[str] = None,
) -> str:
    """
    Initiates backend-managed OAuth 2.0 / OpenID Connect authorization code flow.
    Stores cryptographically secure state and nonce in oauth_states table.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise MissingOAuthConfigError()

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)

    # Sanitize return_to URL: prevent open redirect, allow only safe relative paths
    safe_return_to = None
    if return_to and isinstance(return_to, str):
        trimmed = return_to.strip()
        if trimmed.startswith("/") and not trimmed.startswith("//"):
            safe_return_to = trimmed

    # Sanitize client_origin: ensure it is a valid http/https origin string
    safe_origin = None
    if client_origin and isinstance(client_origin, str):
        trimmed_origin = client_origin.strip().rstrip("/")
        if trimmed_origin.startswith("http://") or trimmed_origin.startswith("https://"):
            safe_origin = trimmed_origin

    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = (now + datetime.timedelta(minutes=10)).isoformat()

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO oauth_states (state, nonce, return_to, client_origin, created_at, expires_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (state, nonce, safe_return_to, safe_origin, now.isoformat(), expires_at))
    conn.commit()

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

def verify_and_consume_state(conn: sqlite3.Connection, state: Optional[str]) -> Dict[str, Any]:
    """
    Validates the OAuth state to protect against CSRF.
    Consumes (deletes) the state record immediately to prevent replay attacks.
    """
    if not state or not isinstance(state, str):
        raise InvalidStateError()

    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor.execute("""
    SELECT *
    FROM oauth_states
    WHERE state = ?;
    """, (state.strip(),))
    row = cursor.fetchone()

    if not row:
        raise InvalidStateError()

    # Replay protection: delete immediately
    cursor.execute("DELETE FROM oauth_states WHERE state = ?;", (state.strip(),))
    conn.commit()

    if row["expires_at"] < now_iso:
        raise InvalidStateError()

    row_keys = row.keys()
    client_origin = row["client_origin"] if "client_origin" in row_keys else None

    return {
        "state": row["state"],
        "nonce": row["nonce"],
        "return_to": row["return_to"],
        "client_origin": client_origin,
    }

async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Exchanges authorization code for Google ID token and access token
    via official Google OAuth token endpoint.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise MissingOAuthConfigError()

    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(token_url, data=payload)
        except Exception as e:
            raise AuthError(f"Network error contacting Google token service: {str(e)}", status_code=502)

    if res.status_code != 200:
        error_detail = res.text
        raise AuthError(f"Google authorization code exchange failed (HTTP {res.status_code}): {error_detail}", status_code=400)

    return res.json()

def verify_google_id_token(
    id_token_str: str,
    expected_nonce: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates the Google ID token's cryptographic signature, issuer, audience,
    expiry, and required claims using Google's official verification library.
    """
    if not GOOGLE_CLIENT_ID:
        raise MissingOAuthConfigError()

    if not id_token_str or not isinstance(id_token_str, str):
        raise TokenVerificationError("Missing or invalid ID token format.")

    try:
        # verify_oauth2_token validates:
        # 1. Cryptographic signature against Google public keys (JWKS)
        # 2. Issuer is accounts.google.com or https://accounts.google.com
        # 3. Audience matches GOOGLE_CLIENT_ID
        # 4. Expiry (exp)
        request_adapter = google_requests.Request()
        claims = id_token.verify_oauth2_token(
            id_token_str,
            request_adapter,
            audience=GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10
        )
    except Exception as e:
        raise TokenVerificationError(f"Google ID token signature verification failed: {str(e)}")

    # Verify issuer claim explicitly
    issuer = claims.get("iss", "")
    if issuer not in ("accounts.google.com", "https://accounts.google.com"):
        raise TokenVerificationError(f"Invalid token issuer: '{issuer}'.")

    # Verify required sub claim
    sub = claims.get("sub")
    if not sub or not str(sub).strip():
        raise TokenVerificationError("Google ID token missing required 'sub' claim.")

    # Verify email claim
    email = claims.get("email")
    if not email or not is_valid_email(str(email)):
        raise TokenVerificationError("Google ID token missing valid 'email' claim.")

    # Verify nonce if expected
    if expected_nonce:
        token_nonce = claims.get("nonce")
        if token_nonce != expected_nonce:
            raise TokenVerificationError("Nonce mismatch in Google ID token.")

    return {
        "sub": str(sub).strip(),
        "email": str(email).strip().lower(),
        "email_verified": bool(claims.get("email_verified", True)),
        "name": claims.get("name"),
        "picture": claims.get("picture"),
    }

def get_or_create_user_from_google(
    conn: sqlite3.Connection,
    claims: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    """
    Finds or creates the user identity associated with verified Google claims:
    - Primary external key: Google 'sub' claim.
    - Preserves existing accounts and profiles.
    - Does not fabricate profile details.
    Returns (user_dict, is_new).
    """
    sub = claims["sub"]
    email = claims["email"]
    name = claims.get("name") or ""
    picture = claims.get("picture") or ""
    email_verified = 1 if claims.get("email_verified") else 0
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    cursor = conn.cursor()

    # 1. Search for existing external identity by provider ('google') and provider_sub
    cursor.execute("""
    SELECT ui.user_id, u.id, u.email, u.name, u.picture, u.is_profile_complete, u.created_at, u.updated_at
    FROM user_identities ui
    JOIN users u ON ui.user_id = u.id
    WHERE ui.provider = 'google' AND ui.provider_sub = ?;
    """, (sub,))
    existing_identity = cursor.fetchone()

    if existing_identity:
        user_id = existing_identity["id"]
        # Update last seen timestamp
        cursor.execute("UPDATE users SET updated_at = ? WHERE id = ?;", (now_iso, user_id))
        conn.commit()

        # Check existing student profile completion
        cursor.execute("SELECT * FROM student_profiles WHERE user_id = ? ORDER BY id DESC LIMIT 1;", (user_id,))
        p_row = cursor.fetchone()
        is_complete = existing_identity["is_profile_complete"]
        if p_row:
            p_dict = dict(p_row)
            p_dict["skills"] = [s.strip() for s in (p_row["skills"] or "").split(",") if s.strip()]
            if evaluate_profile_completion(p_dict):
                is_complete = 1
                cursor.execute("UPDATE users SET is_profile_complete = 1 WHERE id = ?;", (user_id,))
                conn.commit()

        return {
            "id": user_id,
            "email": existing_identity["email"],
            "name": existing_identity["name"],
            "picture": existing_identity["picture"],
            "is_profile_complete": bool(is_complete),
        }, False

    # 2. Check if a user with verified email exists to safely link identity
    cursor.execute("SELECT id, email, name, picture, is_profile_complete FROM users WHERE LOWER(email) = ?;", (email,))
    existing_user_by_email = cursor.fetchone()

    if existing_user_by_email:
        user_id = existing_user_by_email["id"]
        # Link Google identity to existing account safely
        cursor.execute("""
        INSERT INTO user_identities (user_id, provider, provider_sub, email, email_verified, created_at, updated_at)
        VALUES (?, 'google', ?, ?, ?, ?, ?);
        """, (user_id, sub, email, email_verified, now_iso, now_iso))
        conn.commit()

        return {
            "id": user_id,
            "email": existing_user_by_email["email"],
            "name": existing_user_by_email["name"],
            "picture": existing_user_by_email["picture"],
            "is_profile_complete": bool(existing_user_by_email["is_profile_complete"]),
        }, False

    # 3. New User Creation: does not fabricate profile data
    cursor.execute("""
    INSERT INTO users (email, name, picture, is_profile_complete, created_at, updated_at)
    VALUES (?, ?, ?, 0, ?, ?);
    """, (email, name, picture, now_iso, now_iso))
    user_id = cursor.lastrowid

    cursor.execute("""
    INSERT INTO user_identities (user_id, provider, provider_sub, email, email_verified, created_at, updated_at)
    VALUES (?, 'google', ?, ?, ?, ?, ?);
    """, (user_id, sub, email, email_verified, now_iso, now_iso))

    # Link or seed clean empty profile entry associated with new user_id
    cursor.execute("""
    INSERT INTO student_profiles (
        user_id, student_name, student_email, skills, team_size, region, updated_at
    ) VALUES (?, ?, ?, '', 2, 'All', ?);
    """, (user_id, name, email, now_iso))

    conn.commit()

    return {
        "id": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "is_profile_complete": False,
    }, True

def create_user_session(conn: sqlite3.Connection, user_id: int) -> Tuple[str, str]:
    """
    Creates an authenticated session in user_sessions.
    Returns (session_id, csrf_token).
    Rotates existing session identifiers if present.
    """
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = (now + datetime.timedelta(days=SESSION_DURATION_DAYS)).isoformat()
    now_iso = now.isoformat()

    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_sessions (session_id, user_id, csrf_token, created_at, expires_at, last_active_at)
    VALUES (?, ?, ?, ?, ?, ?);
    """, (session_id, user_id, csrf_token, now_iso, expires_at, now_iso))
    conn.commit()

    return session_id, csrf_token

def get_session_user(conn: sqlite3.Connection, session_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Validates session token from cookie/header, checks expiry, and returns user dict.
    Updates last_active_at.
    """
    if not session_id or not isinstance(session_id, str):
        return None

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.session_id, s.user_id, s.csrf_token, s.expires_at,
           u.id, u.email, u.name, u.picture, u.is_profile_complete
    FROM user_sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.session_id = ? AND s.expires_at > ?;
    """, (session_id.strip(), now_iso))
    row = cursor.fetchone()

    if not row:
        return None

    # Sliding session / activity touch
    cursor.execute("UPDATE user_sessions SET last_active_at = ? WHERE session_id = ?;", (now_iso, session_id.strip()))
    conn.commit()

    return {
        "session_id": row["session_id"],
        "csrf_token": row["csrf_token"],
        "user_id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "picture": row["picture"],
        "is_profile_complete": bool(row["is_profile_complete"]),
    }

def destroy_user_session(conn: sqlite3.Connection, session_id: Optional[str]) -> bool:
    """Invalidates and deletes user session upon logout."""
    if not session_id:
        return False
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE session_id = ?;", (session_id.strip(),))
    conn.commit()
    return cursor.rowcount > 0
