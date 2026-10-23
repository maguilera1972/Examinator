import sys
sys.path.insert(0, "/opt/exam-simulator")

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.models import ImportLog, User
from app.services import mail_service
from app.services.mail_service import message_to_html, personalize, render_email_html, send_broadcast


def _user(first="Ada", last="Lovelace", email="ada@example.com"):
    return User(first_name=first, last_name=last, email=email)


def test_personalize_replaces_name_tokens():
    assert personalize("Bonjour {prénom} {nom} / {prenom}", _user()) == "Bonjour Ada Lovelace / Ada"


def test_message_to_html_escapes_and_formats():
    out = message_to_html("Hello <b>x</b>\nline2\n\n**Bold** https://example.com/a.")
    assert "&lt;b&gt;x&lt;/b&gt;" in out
    assert "<br>" in out
    assert out.count("<p ") == 2
    assert "<strong" in out and "Bold" in out
    assert 'href="https://example.com/a"' in out


def test_render_email_uses_site_palette_logo_and_button():
    html = render_email_html("Sujet {prénom}", "Corps", _user(), button_label="Go", button_url="https://site.example/")
    assert "#1B2B44" in html and "#7EE8FA" in html
    assert "cid:examinator-logo" in html
    assert "Sujet Ada" in html
    assert 'href="https://site.example/"' in html and ">Go<" in html
    assert "href" not in render_email_html("S", "Corps sans lien", _user()).split("Corps sans lien")[1].split("</td>")[0]


def test_send_broadcast_sends_individually_and_logs(monkeypatch):
    sent = []
    monkeypatch.setattr(mail_service, "_access_token", lambda client: "token")
    monkeypatch.setattr(
        mail_service, "_send_one",
        lambda client, token, email, name, subject, body: sent.append((email, subject, "Ada" in body or "Bob" in body)),
    )
    db = SessionLocal()
    try:
        users = [_user(), _user("Bob", "Marley", "bob@example.com")]
        result = send_broadcast(db, users, "Hi {prénom}", "Bonjour {prénom}", log_label="email_test_suite")
        assert result.sent == ["ada@example.com", "bob@example.com"]
        assert sent == [("ada@example.com", "Hi Ada", True), ("bob@example.com", "Hi Bob", True)]
        log = db.query(ImportLog).filter(ImportLog.source == "email_test_suite").order_by(ImportLog.id.desc()).first()
        assert "2/2" in log.message and log.status == "success"
    finally:
        db.query(ImportLog).filter(ImportLog.source == "email_test_suite").delete()
        db.commit()
        db.close()


def test_send_broadcast_requires_subject_and_body():
    db = SessionLocal()
    try:
        for subject, body in (("", "x"), ("x", "  ")):
            try:
                send_broadcast(db, [_user()], subject, body)
                assert False
            except ValueError:
                pass
    finally:
        db.close()


def test_admin_preview_endpoint_returns_branded_html():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.admin_email).first()
        if not admin:
            return
        client = TestClient(app)
        client.cookies.set(settings.session_cookie, str(admin.id))
        resp = client.post("/admin/email/preview", data={"subject": "Test", "body": "Bonjour {prénom}", "audience": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert "/static/img/logo.png" in data["html"]
        assert f"Bonjour {admin.first_name}" in data["html"]
        assert data["sender"] == settings.mail_sender
    finally:
        db.close()
