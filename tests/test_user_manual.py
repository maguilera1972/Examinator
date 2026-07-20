import sys
sys.path.insert(0, "/opt/exam-simulator")

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.user_manual_service import (
    MANUAL_LANGUAGES,
    MANUAL_VERSION,
    build_user_manual_pdf,
    generate_all_manuals,
    list_manual_languages,
    manual_disk_path,
    manual_filename,
)


def test_all_languages_generate_valid_pdf_with_images():
    for code in MANUAL_LANGUAGES:
        pdf = build_user_manual_pdf(code)
        assert pdf[:4] == b"%PDF", code
        assert len(pdf) > 200_000, code  # cover + screenshots
        assert pdf.count(b"/DCTDecode") >= 8, code  # screenshots + logo embeds
        assert manual_filename(code) == f"examinator_user_guide_{code}_v{MANUAL_VERSION}.pdf"
        assert pdf.count(b"/DCTDecode") >= 9, code  # logo + screenshots including search
        # Legal notice present (DejaVu embeds as compressed streams; check via content builder)
        from app.services.user_manual_service import _content
        legal = _content(code)["legal"]
        assert "Aguilera Lab" in legal
        assert len(legal) > 100


def test_generate_all_manuals_writes_disk_and_cleans_old():
    manuals_dir = Path("/opt/exam-simulator/app/static/docs/manuals")
    manuals_dir.mkdir(parents=True, exist_ok=True)
    stale = manuals_dir / "examinator_user_guide_fr_v1.pdf"
    stale.write_bytes(b"%PDF-old")
    written = generate_all_manuals()
    assert not stale.exists()
    for code, path in written.items():
        assert path.exists()
        assert path.stat().st_size > 200_000
        assert path == manual_disk_path(code)


def test_list_manual_languages_versioned():
    langs = list_manual_languages()
    assert len(langs) == 5
    assert all(f"?v={MANUAL_VERSION}" in item["url"] for item in langs)


def test_help_downloads_serve_prebuilt_files():
    generate_all_manuals()
    client = TestClient(app)
    r = client.get("/help")
    assert r.status_code == 200
    assert f"_v{MANUAL_VERSION}.pdf" in r.text or f"v={MANUAL_VERSION}" in r.text
    assert "English only" in r.text

    for code in ("fr", "en"):
        r = client.get(f"/help/manual/{code}.pdf?v={MANUAL_VERSION}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 200_000
        assert r.content.count(b"/DCTDecode") >= 8
        assert f"v{MANUAL_VERSION}" in r.headers.get("content-disposition", "")
        assert "no-store" in r.headers.get("cache-control", "")
