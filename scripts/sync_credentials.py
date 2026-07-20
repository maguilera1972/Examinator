#!/usr/bin/env python3
"""Sync certification families and exam metadata from Microsoft sources."""

import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.services.credentials_sync_service import sync_credentials_catalog


def main():
    db = SessionLocal()
    try:
        log = sync_credentials_catalog(db, enrich_learn=True)
        print(log.message)
    finally:
        db.close()


if __name__ == "__main__":
    main()
