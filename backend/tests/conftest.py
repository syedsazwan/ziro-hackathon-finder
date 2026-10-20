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
