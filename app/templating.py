from fastapi.templating import Jinja2Templates

from app.services.gravatar import gravatar_url


def page_section(path: str) -> str:
    """Map URL path to a theme key for section-specific backgrounds."""
    if path.startswith("/catalog"):
        return "catalog"
    if path.startswith("/profile"):
        return "profile"
    if path.startswith("/calendar"):
        return "calendar"
    if path.startswith("/admin"):
        return "admin"
    if path.startswith("/register"):
        return "register"
    if path.startswith("/help"):
        return "help"
    if path.startswith("/exam") or path.startswith("/session"):
        return "exam"
    return "home"


templates = Jinja2Templates(directory="/opt/exam-simulator/app/templates")
templates.env.globals["gravatar_url"] = gravatar_url
templates.env.globals["page_section"] = page_section
