"""Run the suite against a throwaway copy of the database so tests never leave data in production.

The environment variable must be set before any `app` module is imported, because
`app.config.settings` and the SQLAlchemy engine are created at import time.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

_SOURCE_DB = Path(
    os.environ.get("EXAMINATOR_TEST_SOURCE_DB", "/opt/exam-simulator/data/exams.db")
)
_TMP_DIR = tempfile.mkdtemp(prefix="examinator-tests-")
_TEST_DB = Path(_TMP_DIR) / "exams.db"

if _SOURCE_DB.exists():
    with sqlite3.connect(_SOURCE_DB) as src, sqlite3.connect(_TEST_DB) as dst:
        src.backup(dst)

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP_DIR, ignore_errors=True)
