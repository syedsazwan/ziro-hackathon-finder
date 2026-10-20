import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment from .env file or .env.example fallback
env_path = BASE_DIR / ".env"
env_example_path = BASE_DIR / ".env.example"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
elif env_example_path.exists():
    load_dotenv(dotenv_path=env_example_path)

# Database configuration
raw_db_path = os.getenv("SQLITE_DB_PATH", "events.db").strip()
p = Path(raw_db_path)
if p.is_absolute():
    DB_PATH = str(p)
else:
    DB_PATH = str((BASE_DIR / p).resolve())

# Application URLs
APP_ORIGIN = os.getenv("APP_ORIGIN", "http://localhost:5173")
BACKEND_ORIGIN = os.getenv("BACKEND_ORIGIN", "http://127.0.0.1:8000")

# CORS Origins
raw_cors = os.getenv("CORS_ORIGINS", "")
if raw_cors.strip():
    CORS_ORIGINS = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
else:
    CORS_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

# Google OAuth 2.0 / OpenID Connect credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    f"{BACKEND_ORIGIN}/api/auth/google/callback"
)

# Session Security
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "ziro-dev-session-secret-change-in-production-32b")
SESSION_COOKIE_NAME = "ziro_session_id"
SESSION_DURATION_DAYS = int(os.getenv("SESSION_DURATION_DAYS", "7"))
COOKIE_SECURE = os.getenv("ENVIRONMENT", "development").lower() == "production"
COOKIE_SAMESITE = "lax"
