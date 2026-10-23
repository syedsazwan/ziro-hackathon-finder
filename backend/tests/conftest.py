import os
import tempfile
import sqlite3

# Ensure test temporary files and SQLite databases are created on Drive D
# where sufficient disk space is available (Drive C has 0 bytes free)
TEST_TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "tmp"))
os.makedirs(TEST_TEMP_DIR, exist_ok=True)
os.environ["TEMP"] = TEST_TEMP_DIR
os.environ["TMP"] = TEST_TEMP_DIR
tempfile.tempdir = TEST_TEMP_DIR

# CRITICAL SAFETY: Prevent tests from making outbound network calls to remote PostgreSQL/Neon.
# All tests must run against isolated local SQLite databases or mocked PostgreSQL connections.
os.environ["DATABASE_URL"] = ""

try:
    import app.config as app_config
    app_config.DATABASE_URL = ""
    app_config.IS_POSTGRES = False
except Exception:
    pass

try:
    import app.database as app_database
    app_database.DATABASE_URL = ""
    app_database.IS_POSTGRES = False
except Exception:
    pass
