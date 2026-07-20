#!/usr/bin/env python3
"""Generate per-exam Excel question bank templates on disk."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.models.models import Exam
from app.services.excel_import_service import build_question_bank_workbook, exam_template_filename

OUTPUT_DIR = Path("/opt/exam-simulator/data/excel-templates")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        global_path = OUTPUT_DIR / "examinator_question_bank_template.xlsx"
        global_path.write_bytes(build_question_bank_workbook(db))
        print(f"Wrote {global_path}")

        exams = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.vendor, Exam.code).all()
        for exam in exams:
            path = OUTPUT_DIR / exam_template_filename(exam.code)
            path.write_bytes(build_question_bank_workbook(db, exam_code=exam.code))
        print(f"Wrote {len(exams)} per-exam template(s) to {OUTPUT_DIR}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
