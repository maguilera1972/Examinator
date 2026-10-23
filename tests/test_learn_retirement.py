import sys
from datetime import date
sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.models.models import Exam, ImportLog
from app.services.catalog_service import search_exams
from app.services.exam_admin_service import update_exam
from app.services.learn_retirement_service import (
    LEARN_RETIRED_SOURCE,
    STATUS_ACTIVE,
    STATUS_RETIRED,
    STATUS_RETIRING,
    LearnExamStatus,
    analyze_microsoft_retirements,
    parse_learn_exam_page,
    retire_exams,
)

TODAY = date(2026, 10, 23)

RETIRED_EXAM_PAGE = """
<html><head><meta name="retirementDate" content="2023-09-30T00:00:00Z" /></head>
<body><main><h1>Exam MS-100: Microsoft 365 Identity and Services</h1>
<p>Warning This exam retired on September 30, 2023. A replacement exam, Exam MS-102: Microsoft 365 Administrator ,
is available for those who are earning the certification for the first time.</p></main></body></html>
"""

RETIRED_CERT_PAGE = """
<html><body><main><h1>Microsoft Certified: Power Automate RPA Developer Associate</h1>
<p>Warning This certification and the renewal assessment are retired. Learn more .</p></main></body></html>
"""

RETIRING_EXAM_PAGE = """
<html><head><meta name="retirementDate" content="2027-03-31T00:00:00Z" /></head>
<body><p>This exam will retire on March 31, 2027.</p></body></html>
"""

ACTIVE_CERT_PAGE = """
<html><body><main><h1>Microsoft Certified: Azure Administrator Associate</h1>
<p>FAQ: What happens if my certification is retired? You keep your transcript.</p></main></body></html>
"""


def test_parse_retired_exam_with_replacement():
    st = parse_learn_exam_page("MS-100", RETIRED_EXAM_PAGE, today=TODAY)
    assert st.status == STATUS_RETIRED
    assert st.retirement_date == date(2023, 9, 30)
    assert st.replacement_code == "MS-102"


def test_parse_retired_certification_page_without_date():
    st = parse_learn_exam_page("PL-500", RETIRED_CERT_PAGE, today=TODAY)
    assert st.status == STATUS_RETIRED
    assert st.retirement_date is None


def test_parse_future_retirement_is_not_retired():
    st = parse_learn_exam_page("XX-100", RETIRING_EXAM_PAGE, today=TODAY)
    assert st.status == STATUS_RETIRING


def test_parse_active_page_ignores_generic_retirement_wording():
    st = parse_learn_exam_page("AZ-104", ACTIVE_CERT_PAGE, today=TODAY)
    assert st.status == STATUS_ACTIVE


def test_retire_exams_hides_exam_and_can_be_reactivated():
    db = SessionLocal()
    code = "ZZ-901"
    try:
        exam = Exam(code=code, name="Retirement Test Exam", vendor="Microsoft", duration_minutes=60)
        db.add(exam)
        db.commit()
        db.refresh(exam)

        statuses = {code: LearnExamStatus(code=code, status=STATUS_RETIRED, replacement_code="ZZ-902")}
        rows = analyze_microsoft_retirements(db, statuses=statuses)
        assert any(r["exam"].id == exam.id for r in rows)

        retired = retire_exams(db, [exam.id], statuses)
        db.refresh(exam)
        assert [e.code for e in retired] == [code]
        assert exam.is_active is False
        assert exam.external_source == LEARN_RETIRED_SOURCE
        assert all(entry["exam"].code != code for entry in search_exams(db, code)["entries"])
        log = db.query(ImportLog).filter(ImportLog.source == "learn_retirement").order_by(ImportLog.id.desc()).first()
        assert "ZZ-901 → ZZ-902" in log.message

        update_exam(
            db, exam.id, code=code, name=exam.name, vendor="Microsoft", duration_minutes=60, passing_score=700,
            questions_per_session=50, description="", overview="", level="", role="",
            product="", learn_url="", is_active=True,
        )
        db.refresh(exam)
        assert exam.is_active is True
        assert exam.external_source == ""
    finally:
        db.query(ImportLog).filter(ImportLog.source == "learn_retirement", ImportLog.message.contains(code)).delete(synchronize_session=False)
        db.query(Exam).filter(Exam.code == code).delete()
        db.commit()
        db.close()


def test_retire_exams_skips_custom_exams():
    db = SessionLocal()
    code = "ZZ-CUS"
    try:
        exam = Exam(code=code, name="Custom", vendor="Microsoft", duration_minutes=60, external_source="admin_custom")
        db.add(exam)
        db.commit()
        assert retire_exams(db, [exam.id]) == []
        db.refresh(exam)
        assert exam.is_active is True
    finally:
        db.query(Exam).filter(Exam.code == code).delete()
        db.commit()
        db.close()
