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


def test_parse_was_retired_wording_with_date_from_text():
    page = (
        "<html><body><h1>Exam AZ-800: Administering Windows Server Hybrid Core Infrastructure</h1>"
        "<p>Warning This exam was retired on September 30, 2026. You will no longer be able to earn "
        "or renew this certification after this date.</p><p>Retirement date: none</p></body></html>"
    )
    st = parse_learn_exam_page("AZ-800", page, today=TODAY)
    assert st.status == STATUS_RETIRED
    assert st.retirement_date == date(2026, 9, 30)


def test_replacement_inferred_from_same_certification():
    from app.services.learn_retirement_service import _infer_replacements

    slug = "windows-server-hybrid-administrator"
    keys = [("AZ-800", slug), ("AZ-801", slug), ("AZ-802", slug), ("MB-700", "fo-architect")]
    statuses = {
        "AZ-800": LearnExamStatus(code="AZ-800", status=STATUS_RETIRED),
        "AZ-801": LearnExamStatus(code="AZ-801", status=STATUS_RETIRED),
        "AZ-802": LearnExamStatus(code="AZ-802", status=STATUS_ACTIVE),
        "MB-700": LearnExamStatus(code="MB-700", status=STATUS_RETIRED),
        "MB-310": LearnExamStatus(code="MB-310", status=STATUS_ACTIVE),
    }
    cert_pages = {slug: {"AZ-802"}, "fo-architect": {"MB-700", "MB-310"}}
    _infer_replacements(keys, statuses, cert_pages)
    assert statuses["AZ-800"].replacement_code == "AZ-802"
    assert statuses["AZ-801"].replacement_code == "AZ-802"
    assert statuses["AZ-800"].replacement_inferred
    assert statuses["AZ-802"].replacement_code == ""
    assert statuses["MB-700"].replacement_code == ""


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


def test_sync_log_parsing_for_summary():
    from app.services.learn_retirement_service import _codes_after_prefix

    msg = "Synced 10 Microsoft families and 69 Microsoft exams; ... Added (2): AI-900, AZ-120. Poster fetch note: x"
    assert _codes_after_prefix(msg, "Added (") == ["AI-900", "AZ-120"]
    assert _codes_after_prefix("Synced. Added (0): -.", "Added (") == []
    assert _codes_after_prefix("Retired from catalog (2): MS-100 → MS-102, PL-500", "Retired from catalog (") == ["MS-100 → MS-102", "PL-500"]


def test_quality_report_is_sorted_by_vendor_then_code():
    from app.services.question_quality import run_quality_report

    db = SessionLocal()
    try:
        rank = {"Microsoft": 0, "CompTIA": 1, "Examinator": 2}
        keys = [(rank.get(e["vendor"], 9), e["vendor"], e["exam_code"]) for e in run_quality_report(db)["exams"]]
        assert keys == sorted(keys)
    finally:
        db.close()


def test_delete_retired_exam_is_ignored_by_sync_until_unignored():
    from app.models.models import IgnoredExamCode
    from app.services.learn_retirement_service import (
        delete_retired_exam,
        ignored_exam_codes,
        list_inactive_exams,
        reactivate_exam,
        unignore_code,
    )

    db = SessionLocal()
    code = "ZZ-903"
    try:
        exam = Exam(code=code, name="Delete Test", vendor="Microsoft", duration_minutes=60)
        db.add(exam)
        db.commit()
        exam_id = exam.id

        try:
            delete_retired_exam(db, exam_id)
            assert False, "active exams must not be deletable here"
        except ValueError:
            pass

        retire_exams(db, [exam_id])
        assert any(r["exam"].id == exam_id and r["bulk_deletable"] for r in list_inactive_exams(db))
        reactivate_exam(db, exam_id)
        db.refresh(exam)
        assert exam.is_active and exam.external_source == ""

        retire_exams(db, [exam_id])
        assert delete_retired_exam(db, exam_id) == code
        assert db.query(Exam).filter(Exam.code == code).count() == 0
        assert code in ignored_exam_codes(db)

        ignored = db.query(IgnoredExamCode).filter(IgnoredExamCode.code == code).first()
        unignore_code(db, ignored.id)
        assert code not in ignored_exam_codes(db)
    finally:
        db.query(IgnoredExamCode).filter(IgnoredExamCode.code == code).delete()
        db.query(ImportLog).filter(ImportLog.message.contains(code)).delete(synchronize_session=False)
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
