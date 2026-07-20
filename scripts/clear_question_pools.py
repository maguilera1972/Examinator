#!/usr/bin/env python3
"""Deactivate all active questions across every exam simulator."""

import sys

sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.services.excel_import_service import clear_all_question_pools


def main() -> None:
    db = SessionLocal()
    try:
        result = clear_all_question_pools(db)
        print(f"Deactivated {result['deactivated']} active question(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
