import sys
sys.path.insert(0, "/opt/exam-simulator")

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.models import Exam
from app.services.catalog_service import search_exams


def test_search_exams_by_code_and_keyword():
    db = SessionLocal()
    try:
        exam = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.code).first()
        assert exam is not None
        by_code = search_exams(db, exam.code)
        assert by_code["total"] >= 1
        assert any(e["exam"].id == exam.id for e in by_code["entries"])

        if exam.vendor:
            by_vendor = search_exams(db, exam.vendor.split()[0])
            assert by_vendor["total"] >= 1
    finally:
        db.close()


def test_search_empty_query_returns_no_entries():
    db = SessionLocal()
    try:
        result = search_exams(db, "   ")
        assert result["total"] == 0
        assert result["entries"] == []
        assert result["tokens"] == []
    finally:
        db.close()


def test_search_multi_token_narrows_results():
    db = SessionLocal()
    try:
        broad = search_exams(db, "Microsoft")
        narrow = search_exams(db, "Microsoft Azure")
        assert broad["total"] >= narrow["total"]
    finally:
        db.close()


def test_catalog_search_route():
    client = TestClient(app)
    r = client.get("/catalog/search")
    assert r.status_code == 200
    assert "Search simulators" in r.text
    assert 'name="q"' in r.text

    r = client.get("/catalog/search", params={"q": "AZ"})
    assert r.status_code == 200
    assert "simulator" in r.text.lower() or "No simulators" in r.text

    # sidebar search form present on other pages
    r = client.get("/catalog")
    assert r.status_code == 200
    assert 'action="/catalog/search"' in r.text
    assert 'name="q"' in r.text
