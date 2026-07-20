#!/usr/bin/env python3
"""Run pool quality checks (for cron / CI). Exit 1 if issues found."""

import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.services.question_quality import dedupe_exam_pool, ensure_fingerprints, run_quality_report


def main():
    db = SessionLocal()
    try:
        ensure_fingerprints(db)
        dedupe_exam_pool(db)
        report = run_quality_report(db)
        for exam in report["exams"]:
            print(
                f"{exam['exam_code']}: unique={exam['unique_count']} "
                f"dup_groups={exam['duplicate_groups']} ready={exam['can_run_session']}"
            )
        if not report["ok"]:
            print("QUALITY CHECK FAILED", file=sys.stderr)
            sys.exit(1)
        print("QUALITY CHECK OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
