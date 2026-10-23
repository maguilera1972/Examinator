"""Branded e-mail broadcast to registered users through Microsoft Graph (app-only, Mail.Send)."""

import base64
import html
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import ImportLog, User, UserStatus

GRAPH_URL = "https://graph.microsoft.com/v1.0"
LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "img" / "logo.png"
LOGO_CID = "examinator-logo"
# Exchange Online allows 30 messages per minute per mailbox.
SEND_INTERVAL_SECONDS = 2.1
PACING_THRESHOLD = 25

AUDIENCES = {
    "all": "Tous les utilisateurs enregistrés",
    "approved": "Utilisateurs approuvés uniquement",
}

_URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]])")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


class MailConfigError(RuntimeError):
    pass


@dataclass
class BroadcastResult:
    sent: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def mail_configured() -> bool:
    return bool(settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret and settings.mail_sender)


def get_recipients(db: Session, audience: str = "all") -> list[User]:
    query = db.query(User).filter(User.email.isnot(None), User.email != "")
    if audience == "approved":
        query = query.filter(User.status == UserStatus.APPROVED)
    return query.order_by(User.last_name, User.first_name).all()


def personalize(text: str, user: User | None) -> str:
    first = (user.first_name if user else "") or ""
    last = (user.last_name if user else "") or ""
    for token, value in (
        ("{prénom}", first), ("{prenom}", first), ("{first_name}", first),
        ("{nom}", last), ("{last_name}", last),
    ):
        text = text.replace(token, value)
    return text


def message_to_html(text: str) -> str:
    """Plain text with blank-line paragraphs, **bold** and bare URLs → inline-styled HTML."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    out = []
    for para in paragraphs:
        safe = html.escape(para)
        safe = _BOLD_RE.sub(r'<strong style="color:#ffffff;">\1</strong>', safe)
        safe = _URL_RE.sub(r'<a href="\1" style="color:#7EE8FA;text-decoration:underline;">\1</a>', safe)
        safe = safe.replace("\n", "<br>")
        out.append(f'<p style="margin:0 0 16px;font-size:15px;line-height:1.65;color:#dbe4f2;">{safe}</p>')
    return "\n".join(out)


def render_email_html(
    subject: str,
    body: str,
    user: User | None = None,
    *,
    button_label: str = "",
    button_url: str = "",
    logo_src: str = f"cid:{LOGO_CID}",
) -> str:
    title = html.escape(personalize(subject, user))
    content = message_to_html(personalize(body, user))
    button = ""
    if button_url.strip():
        label = html.escape(button_label.strip() or "Ouvrir Examinator")
        url = html.escape(button_url.strip(), quote=True)
        button = f"""
          <tr><td align="center" style="padding:8px 32px 28px;">
            <a href="{url}" style="display:inline-block;padding:12px 28px;border-radius:10px;background-color:#7EE8FA;background-image:linear-gradient(90deg,#7EE8FA,#9D50BB);color:#1B2B44;font-weight:700;font-size:15px;text-decoration:none;">{label}</a>
          </td></tr>"""
    site_link = ""
    if settings.public_url:
        site = html.escape(settings.public_url, quote=True)
        site_link = f' · <a href="{site}" style="color:#7EE8FA;text-decoration:none;">{site}</a>'
    sender = html.escape(settings.mail_sender)
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>{title}</title></head>
<body style="margin:0;padding:0;background-color:#142033;font-family:Inter,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#142033;">
    <tr><td align="center" style="padding:28px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background-color:#1B2B44;border:1px solid #334d73;border-radius:14px;overflow:hidden;">
        <tr><td align="center" style="background-color:#223654;padding:20px 24px 12px;">
          <img src="{logo_src}" alt="Examinator" width="300" style="display:block;width:300px;max-width:100%;height:auto;border:0;">
        </td></tr>
        <tr><td style="height:4px;line-height:4px;font-size:0;background-color:#7EE8FA;background-image:linear-gradient(90deg,#7EE8FA,#9D50BB);">&nbsp;</td></tr>
        <tr><td style="padding:28px 32px 8px;">
          <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;font-weight:700;color:#e8eef8;">{title}</h1>
          {content}
        </td></tr>{button}
        <tr><td style="padding:18px 32px 24px;border-top:1px solid #334d73;">
          <p style="margin:0;font-size:12px;line-height:1.6;color:#9bb0cc;">
            Vous recevez ce message car vous êtes inscrit(e) sur Examinator — IT Exam Platform.<br>
            Envoyé par {sender}{site_link}
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _access_token(client: httpx.Client) -> str:
    if not mail_configured():
        raise MailConfigError("Envoi d’e-mails non configuré (GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET dans .env)")
    resp = client.post(
        f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
    )
    data = resp.json()
    if resp.status_code != 200 or "access_token" not in data:
        raise MailConfigError(f"Authentification Microsoft refusée : {data.get('error_description', resp.text)[:200]}")
    return data["access_token"]


def _logo_attachment() -> dict:
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "examinator-logo.png",
        "contentType": "image/png",
        "contentId": LOGO_CID,
        "isInline": True,
        "contentBytes": base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii"),
    }


def _send_one(client: httpx.Client, token: str, to_email: str, to_name: str, subject: str, html_body: str) -> None:
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": to_email, "name": to_name}}],
            "attachments": [_logo_attachment()],
        },
        "saveToSentItems": True,
    }
    resp = client.post(
        f"{GRAPH_URL}/users/{settings.mail_sender}/sendMail",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 429:
        time.sleep(int(resp.headers.get("Retry-After", "10")))
        resp = client.post(
            f"{GRAPH_URL}/users/{settings.mail_sender}/sendMail",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 202:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"HTTP {resp.status_code} : {detail[:200]}")


def send_broadcast(
    db: Session,
    recipients: list[User],
    subject: str,
    body: str,
    *,
    button_label: str = "",
    button_url: str = "",
    log_label: str = "email_broadcast",
) -> BroadcastResult:
    subject = subject.strip()
    if not subject or not body.strip():
        raise ValueError("L’objet et le message sont obligatoires")
    if not recipients:
        raise ValueError("Aucun destinataire")
    result = BroadcastResult()
    pace = len(recipients) > PACING_THRESHOLD
    with httpx.Client(timeout=30) as client:
        token = _access_token(client)
        for index, user in enumerate(recipients):
            if pace and index:
                time.sleep(SEND_INTERVAL_SECONDS)
            name = f"{user.first_name} {user.last_name}".strip()
            try:
                _send_one(
                    client, token, user.email, name,
                    personalize(subject, user),
                    render_email_html(subject, body, user, button_label=button_label, button_url=button_url),
                )
                result.sent.append(user.email)
            except Exception as exc:
                result.failed.append((user.email, str(exc)))
    message = f"'{subject}' sent to {len(result.sent)}/{len(recipients)} recipient(s) from {settings.mail_sender}."
    if result.failed:
        message += " Failed: " + "; ".join(f"{email} ({err})" for email, err in result.failed)[:1500]
    db.add(ImportLog(
        source=log_label,
        message=message,
        questions_added=len(result.sent),
        status="success" if not result.failed else ("partial" if result.sent else "error"),
    ))
    db.commit()
    return result
