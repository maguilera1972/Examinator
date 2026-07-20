#!/usr/bin/env python3
"""Deduplicate pools and refill exams below minimum unique count."""

import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.config import settings
from app.database import SessionLocal
from app.models.models import Exam, Question
from app.services.import_service import MICROSOFT_EXAMS, import_questions_json
from app.services.question_quality import dedupe_exam_pool, ensure_fingerprints, run_quality_report
from scripts.seed_data import build_unique_pool


def main():
    db = SessionLocal()
    try:
        ensure_fingerprints(db)
        result = dedupe_exam_pool(db)
        print(f"Deactivated {result['deactivated']} duplicates in {result['duplicate_groups']} groups")

        meta_by_code = {m["code"]: m for m in MICROSOFT_EXAMS}
        for exam in db.query(Exam).filter(Exam.is_active.is_(True)).all():
            active = (
                db.query(Question)
                .filter(Question.exam_id == exam.id, Question.is_active.is_(True))
                .all()
            )
            fps = {q.text_fingerprint for q in active if q.text_fingerprint}
            need = settings.questions_per_session - len(fps)
            if need > 0:
                meta = meta_by_code.get(exam.code, {"sections": [("General", 100)]})
                payload = build_unique_pool(exam.code, meta, need + 5)
                # offset external ids to avoid collision
                for i, item in enumerate(payload):
                    item["external_id"] = f"repair-{exam.code}-{len(fps)+i+1}"
                import_questions_json(db, exam.code, payload, source="repair")
                print(f"Refilled {exam.code} with {len(payload)} questions")

        report = run_quality_report(db)
        print("Quality OK:" if report["ok"] else "Quality ISSUES:", report)
        if not report["ok"]:
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
