# Hackathon & Contest Finder (Stage 1, Stage 2 & Stage 3)

A full-stack platform designed to help students discover hackathons and competitive programming contests tailored to their skills, team size, budget, and availability, with automatic **IST timezone conversion**, **eligibility evaluation**, a **Safe Registration Workflow**, and **Safe Public Event Discovery & Source Provenance**.

> [!IMPORTANT]
> **Safety & Provenance Notice:**
> - **Synthetic demo events** are permanently labeled with `is_synthetic: True` and prefixed with `[SYNTHETIC DEMO]`. They are never presented as real listings.
> - **Real discovered events** are ingested strictly through permitted public official sources with canonical provenance URLs.
> - **No automated external registrations** are performed, and no website access controls, CAPTCHAs, or rate limits are bypassed.
> - Background scraping is **disabled on startup**; ingestion runs exclusively through explicit manual refresh.

---

## Tech Stack

- **Frontend:** React + TypeScript + Vite, Vanilla CSS design system (responsive, dark-themed, glassmorphic UI). Ready for Vercel deployment.
- **Backend:** Python + FastAPI + SQLite, timezone-aware datetime processing (`zoneinfo` + `tzdata`), Pydantic validation. Ready for Render/Railway deployment.
- **Testing:** Pytest + FastAPI TestClient (24/24 automated tests passing across isolated test databases).

---

## Project Structure

```text
d:/Ziro/
├── .gitignore                   # Ignores venv, node_modules, dist, sqlite DBs, .env
├── .env.example                 # Root environment variable template
├── README.md                    # Project documentation and setup guide
│
├── backend/
│   ├── .env.example             # Backend environment variable template
│   ├── requirements.txt         # FastAPI, uvicorn, pydantic, pytest, httpx, tzdata
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, CORS, events and registration routes
│   │   ├── config.py            # Environment configurations & DB path
│   │   ├── database.py          # SQLite connection manager, foreign keys, table schemas & migration
│   │   ├── schemas.py           # Pydantic schemas (events, registration actions, audit logs, refresh)
│   │   ├── seed.py              # Synthetic demo event fixtures
│   │   ├── utils.py             # Timezone conversion (PST -> IST) & eligibility engine
│   │   ├── normalization.py     # Stage 3: Event validation, non-guessing IST conversion & expiration
│   │   ├── event_service.py     # Stage 3: Source sync coordination & SQLite upsert deduplication
│   │   ├── registration_service.py # Stage 2: Safe registration business rules & audit log
│   │   └── adapters/            # Stage 3: Source adapters
│   │       ├── __init__.py      # Adapter registry
│   │       ├── base.py          # BaseEventSourceAdapter & SourceFetchResult contract
│   │       ├── devfolio.py      # Devfolio official public API adapter
│   │       ├── unstop.py        # Unstop safe restricted-access stub (documents Cloudflare 403)
│   │       └── mlh.py           # MLH official public schedule adapter
│   └── tests/
│       ├── __init__.py
│       ├── test_api.py          # Pytest suite (health, eligibility, PST-to-IST, Stage 2 safe workflow)
│       └── test_event_discovery.py # Stage 3 Pytest suite (adapters, URL validation, non-guessing tz, dedup)
│
└── frontend/
    ├── .env                     # Local environment file (VITE_API_BASE_URL=http://127.0.0.1:8000)
    ├── .env.example             # Frontend environment variable template
    ├── package.json             # React 19 + TypeScript + Vite configuration
    ├── tsconfig.json            # TypeScript configuration
    ├── vite.config.ts           # Vite bundler configuration with dev reverse proxy
    ├── index.html               # Semantic HTML5 entry with Google Fonts (Outfit & Inter) and SEO tags
    └── src/
        ├── App.tsx              # Main dashboard: profile state, tabs, filter pills, error/empty/loading states
        ├── main.tsx             # React entrypoint
        ├── index.css            # Dark mode design system (HSL tokens, glassmorphism, responsive grid)
        ├── types.ts             # Data contracts for student profile, events, registration, audit logs
        ├── api.ts               # API fetch client for events, health, registrations, and refresh
        └── components/
            ├── Header.tsx       # Brand header, synthetic demo badge, and live API health indicator
            ├── ProfileForm.tsx  # Student profile input form (skills, team, region, dates, budget)
            └── EventCard.tsx    # Card displaying eligibility badge, IST deadline, & source evidence
```

---

## Safe Event Discovery & Source Provenance (Stage 3)

### Supported Source Adapters & Access Policy

| Source | Status | Access Mechanism | Limitation & Compliance Notes |
| :--- | :--- | :--- | :--- |
| **Devfolio** | **Active** | Official public API (`https://api.devfolio.co/api/hackathons?filter=all`) | Permitted read-only public endpoint. No private endpoints or auth used. Free entry events verified. |
| **MLH** | **Active** | Official public season schedule (`https://mlh.io/seasons/`) | Public student hackathon listings ingested with canonical source links. |
| **Unstop** | **Restricted Stub** | Documented restricted stub | Direct automated access blocked by upstream Cloudflare (HTTP 403) requiring browser cookies/session. **Safety compliance:** Automated bypass (CAPTCHA/headless scraping) is strictly disabled. |

### Normalization & Safety Guarantees
1. **URL Validation:** All real events must provide a valid HTTP/HTTPS official source URL; malformed or missing URLs are rejected with `NormalizationError`.
2. **Non-Guessing Timezone Conversion:** Converting deadlines to IST rejects timezone-naive timestamps with ambiguous or unrecognized abbreviations.
3. **Accurate Expiration Computation:** `is_deadline_expired` dynamically checks whether the converted IST deadline is in the past.
4. **Transparent Fee Incompleteness:** Events with unstated or missing fees are marked with `fee_status: "unknown"` and `verification_status: "needs_verification"`.
5. **Deduplication:** Events are deduplicated on `(source_name, source_event_id)` and canonical `source_url`. Repeated refreshes update existing records rather than producing duplicates.
6. **Synthetic Separation:** Seeded fixtures are permanently tagged `is_synthetic: 1` (`[SYNTHETIC DEMO]`). `GET /api/events` allows querying with `include_synthetic=false` or `source=devfolio`.
7. **Registration Workflow Safety:** Event discovery operations do not approve, submit, or confirm any registration action.

---

## API Endpoints

### Event Discovery & Synchronization
- `GET /health` - Service health and database check
- `GET /api/events` - List events with eligibility evaluation, IST deadlines, and provenance fields:
  - Query parameters: `skills`, `team_size`, `region`, `start_date`, `end_date`, `budget`, `source`, `include_synthetic`
- `POST /api/events/refresh` - Manual ingestion from permitted public source adapters:
  - Query parameters: `source` (`'all'`, `'devfolio'`, `'mlh'`, `'unstop'`), `limit_per_source` (default 10)

### Safe Registration Workflow (Stage 2)
- `POST /api/registrations` - Request demo registration (starts as `pending_approval`)
- `POST /api/registrations/{action_id}/approve` - Record human approval (transitions to `approved`)
- `POST /api/registrations/{action_id}/submit` - Execute simulated submission (blocked if unapproved)
- `POST /api/registrations/{action_id}/verify` - Record manual verification outcome with evidence
- `GET /api/registrations/{action_id}` - Retrieve action details along with its full audit trail
- `GET /api/registrations` - List registration actions

---

## Automated Tests & Verification

### Run Pytest Suite
```bash
backend\.venv\Scripts\pytest backend\tests
```
**Test Coverage: 24/24 Passing**
- **14 Tests in `test_api.py`:** Health check, event listing, team size eligibility, fee verification, PST-to-IST conversion, approval requirement guard, duplicate action prevention, append-only audit trail, anti-placeholder validation.
- **10 Tests in `test_event_discovery.py`:** Devfolio adapter ingestion, URL validation, non-guessing timezone conversion, expired deadline accuracy, missing fee status marking, event deduplication, Unstop restriction compliance, source failure resilience, synthetic/real separation, registration workflow isolation.

### Run Frontend Production Build Check
```bash
cd frontend
npm run build
```
Typechecking and bundling completed with 0 errors.

---

## Google OAuth 2.0 & OpenID Connect Authentication

Ziro features a production-ready authentication architecture leveraging Google's official OAuth 2.0 / OpenID Connect flow with backend identity verification.

### 1. Google Cloud Console Setup Instructions

To enable real Google Sign-In for your deployment:

1. Visit the [Google Cloud Console Credentials Page](https://console.cloud.google.com/apis/credentials).
2. Create or select your Google Cloud project.
3. Configure the **OAuth consent screen**:
   - User Type: **External** (allows any valid Google account to authenticate; no college-domain restrictions).
   - App Name: **Ziro Hackathon & Contest Finder**
   - User Support Email: your contact email.
   - Scopes: `openid`, `email`, `profile`.
4. Create an **OAuth Client ID**:
   - Application Type: **Web application**
   - Name: `Ziro Web Client`
   - **Authorized JavaScript origins**:
     - `http://localhost:5173`
     - `http://127.0.0.1:5173`
     - *(In production, add your public HTTPS domain, e.g. `https://ziro.example.com`)*
   - **Authorized redirect URIs**:
     - `http://127.0.0.1:8000/api/auth/google/callback`
     - `http://localhost:8000/api/auth/google/callback`
     - *(In production, add your backend callback URL, e.g. `https://api.ziro.example.com/api/auth/google/callback`)*
5. Copy your **Client ID** and **Client Secret**.
6. Create `backend/.env` (copying `backend/.env.example`) and fill in:
   ```env
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
   APP_ORIGIN=http://localhost:5173
   BACKEND_ORIGIN=http://127.0.0.1:8000
   SESSION_SECRET_KEY=generate-a-random-32-byte-hex-string
   ```

### 2. Authentication Flows & Identity Rules

- **Universal Sign-In:** Any genuine Google account can sign in; sign-in is not restricted to college domains.
- **Backend Verification:** The backend directly contacts Google and validates token signature, issuer, audience (`GOOGLE_CLIENT_ID`), expiry, and required claims using `google.oauth2.id_token.verify_oauth2_token`.
- **Primary External Key:** The stable Google `sub` claim is used as the external identity identifier (`user_identities.provider_sub`).
- **CSRF & Replay Defense:** Cryptographically random `state` and `nonce` parameters are generated on login start, stored with a 10-minute expiry, and consumed immediately upon callback receipt.
- **Open Redirect Guard:** Return URLs are sanitized; only validated relative internal paths (e.g. `/events`, `/my-registrations`) are permitted.
- **First-Time Login Onboarding:**
  1. Google authentication creates user and identity records without inventing mock profile data.
  2. The user is redirected to `My Profile` with an onboarding explanation banner.
  3. Minimum required fields: Full Name, Student Email, Institution, Degree Program, 4-digit Graduation Year, and at least 1 Technical Skill.
  4. Once satisfied, `users.is_profile_complete` becomes `true` and the full application is unlocked.
- **Existing User Login:**
  1. Identifies existing account via previously linked Google `sub`.
  2. Preserves all saved criteria, registration actions, append-only audit logs, and notifications.
  3. Skips onboarding if the profile was previously completed, continuing directly to the intended destination.

