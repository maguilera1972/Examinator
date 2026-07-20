"""Generate branded Examinator user manuals (PDF) with cover page and screenshots."""

from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    Flowable,
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Examinator visual identity
BG = colors.HexColor("#1B2B44")
BG_DEEP = colors.HexColor("#142033")
SURFACE = colors.HexColor("#223654")
MUTED = colors.HexColor("#9bb0cc")
TEXT = colors.HexColor("#e8eef8")
ACCENT_CYAN = colors.HexColor("#7EE8FA")
ACCENT_PURPLE = colors.HexColor("#9D50BB")
BODY_TEXT = colors.HexColor("#1a202c")
BODY_MUTED = colors.HexColor("#4a5568")
NOTE_BG = colors.HexColor("#ebf8ff")

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
LOGO_PATH = Path("/opt/exam-simulator/app/static/img/logo.png")
SHOT_DIR = Path("/opt/exam-simulator/app/static/docs/screenshots/pdf")
MANUALS_DIR = Path("/opt/exam-simulator/app/static/docs/manuals")

MANUAL_VERSION = "10"

MANUAL_LANGUAGES = {
    "fr": {"label": "Français", "flag": "🇫🇷"},
    "en": {"label": "English", "flag": "🇬🇧"},
    "it": {"label": "Italiano", "flag": "🇮🇹"},
    "es": {"label": "Español", "flag": "🇪🇸"},
    "de": {"label": "Deutsch", "flag": "🇩🇪"},
}

_FONTS_READY = False


def _ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    _FONTS_READY = True


def _styles():
    _ensure_fonts()
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "M3H1", fontName="DejaVu-Bold", fontSize=14,
            textColor=BG, spaceBefore=10, spaceAfter=6, leading=18,
        ),
        "body": ParagraphStyle(
            "M3Body", fontName="DejaVu", fontSize=10,
            textColor=BODY_TEXT, leading=14, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "M3Note", fontName="DejaVu", fontSize=9.5,
            textColor=BG, leading=13, alignment=TA_LEFT,
        ),
        "note_title": ParagraphStyle(
            "M3NoteTitle", fontName="DejaVu-Bold", fontSize=11,
            textColor=BG, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "M3Bullet", fontName="DejaVu", fontSize=10,
            textColor=BODY_TEXT, leading=13.5,
        ),
        "caption": ParagraphStyle(
            "M3Caption", fontName="DejaVu", fontSize=8.5,
            textColor=BODY_MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10,
        ),
        "toc": ParagraphStyle(
            "M3Toc", fontName="DejaVu", fontSize=11,
            textColor=BODY_TEXT, leading=18, leftIndent=2,
        ),
        "toc_title": ParagraphStyle(
            "M3TocTitle", fontName="DejaVu-Bold", fontSize=14,
            textColor=BG, spaceAfter=8,
        ),
        "footer": ParagraphStyle(
            "M3Footer", fontName="DejaVu", fontSize=8,
            textColor=BODY_MUTED, alignment=TA_CENTER,
        ),
        "legal_title": ParagraphStyle(
            "M3LegalTitle", fontName="DejaVu-Bold", fontSize=12,
            textColor=BG, spaceAfter=8, alignment=TA_LEFT,
        ),
        "legal_body": ParagraphStyle(
            "M3LegalBody", fontName="DejaVu", fontSize=9,
            textColor=BODY_TEXT, leading=13, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "shot_title": ParagraphStyle(
            "M3ShotTitle", fontName="DejaVu-Bold", fontSize=9,
            textColor=ACCENT_CYAN, alignment=TA_LEFT, spaceBefore=2, spaceAfter=4,
        ),
    }


class BottomAnchored(Flowable):
    """Occupy the rest of the page and draw child flowables pinned to the bottom.

    If the remaining space is too small for the children, claim more than available
    so ReportLab postpones this flowable to the next page (no blank intermediate page
    from an extra PageBreak).
    """

    def __init__(self, flowables: list):
        super().__init__()
        self._flowables = flowables
        self._avail_width = 0.0
        self._avail_height = 0.0

    def _content_height(self, availWidth: float) -> float:
        total = 0.0
        for flowable in self._flowables:
            flowable.canv = getattr(self, "canv", None)
            _w, h = flowable.wrap(availWidth, 30 * cm)
            total += h
        return total

    def wrap(self, availWidth, availHeight):
        self._avail_width = availWidth
        needed = self._content_height(availWidth) + 2 * mm
        if availHeight < needed:
            # Does not fit on this page → postpone to a fresh page.
            return availWidth, availHeight + 1
        self._avail_height = max(0.0, availHeight)
        return availWidth, self._avail_height

    def draw(self):
        dims = []
        for flowable in self._flowables:
            flowable.canv = self.canv
            _w, h = flowable.wrap(self._avail_width, self._avail_height)
            dims.append((flowable, h))
        # Draw from the bottom of this flowable's box upward.
        y = 0.0
        for flowable, h in reversed(dims):
            flowable.drawOn(self.canv, 0, y)
            y += h


def _gradient_line(canv, x, y, width, height=3.5):
    steps = 48
    step_w = width / steps
    for i in range(steps):
        t = i / max(steps - 1, 1)
        r = (0x7E + (0x9D - 0x7E) * t) / 255
        g = (0xE8 + (0x50 - 0xE8) * t) / 255
        b = (0xFA + (0xBB - 0xFA) * t) / 255
        canv.setFillColor(colors.Color(r, g, b))
        canv.rect(x + i * step_w, y, step_w + 0.4, height, stroke=0, fill=1)


def _draw_cover_page(canv: pdfcanvas.Canvas, content: dict, lang: str):
    """Full-page branded cover (page de garde)."""
    _ensure_fonts()
    page_w, page_h = A4

    # Full bleed background
    canv.setFillColor(BG_DEEP)
    canv.rect(0, 0, page_w, page_h, stroke=0, fill=1)

    # Decorative orbs
    canv.setFillColor(colors.Color(0x7E / 255, 0xE8 / 255, 0xFA / 255, alpha=0.08))
    canv.circle(page_w * 0.15, page_h * 0.82, 90, stroke=0, fill=1)
    canv.setFillColor(colors.Color(0x9D / 255, 0x50 / 255, 0xBB / 255, alpha=0.10))
    canv.circle(page_w * 0.88, page_h * 0.25, 120, stroke=0, fill=1)

    # Top accent bar
    _gradient_line(canv, 0, page_h - 8, page_w, 8)

    # Logo
    if LOGO_PATH.exists():
        logo_w = 11 * cm
        logo_h = logo_w * 440 / 800
        canv.drawImage(
            str(LOGO_PATH),
            (page_w - logo_w) / 2,
            page_h - 4.2 * cm - logo_h,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
        )
        title_y = page_h - 4.2 * cm - logo_h - 1.4 * cm
    else:
        title_y = page_h * 0.55

    canv.setFillColor(ACCENT_CYAN)
    canv.setFont("DejaVu-Bold", 12)
    canv.drawCentredString(page_w / 2, title_y, "EXAMINATOR")

    canv.setFillColor(TEXT)
    canv.setFont("DejaVu-Bold", 28)
    canv.drawCentredString(page_w / 2, title_y - 1.1 * cm, content["doc_title"])

    canv.setFillColor(MUTED)
    canv.setFont("DejaVu", 12)
    # wrap subtitle roughly
    subtitle = content["subtitle"]
    canv.drawCentredString(page_w / 2, title_y - 1.9 * cm, subtitle)

    _gradient_line(canv, page_w / 2 - 4 * cm, title_y - 2.5 * cm, 8 * cm, 3)

    canv.setFillColor(MUTED)
    canv.setFont("DejaVu", 11)
    canv.drawCentredString(
        page_w / 2,
        title_y - 3.3 * cm,
        f"{MANUAL_LANGUAGES[lang]['label']}  ·  {datetime.utcnow().strftime('%d %B %Y')}",
    )

    # Bottom info card
    card_y = 3.2 * cm
    canv.setFillColor(SURFACE)
    canv.roundRect(2 * cm, card_y, page_w - 4 * cm, 3.4 * cm, 10, stroke=0, fill=1)
    canv.setStrokeColor(ACCENT_CYAN)
    canv.setLineWidth(1.5)
    canv.roundRect(2 * cm, card_y, page_w - 4 * cm, 3.4 * cm, 10, stroke=1, fill=0)

    canv.setFillColor(ACCENT_CYAN)
    canv.setFont("DejaVu-Bold", 10)
    canv.drawString(2.6 * cm, card_y + 2.5 * cm, content["ui_note_title"])
    canv.setFillColor(TEXT)
    canv.setFont("DejaVu", 8.5)
    # Simple text wrap for UI note
    note = content["ui_note"]
    max_chars = 95
    words = note.split()
    lines, current = [], ""
    for w in words:
        trial = f"{current} {w}".strip()
        if len(trial) <= max_chars:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    y = card_y + 1.9 * cm
    for line in lines[:5]:
        canv.drawString(2.6 * cm, y, line)
        y -= 11

    # Bottom gradient
    _gradient_line(canv, 0, 0, page_w, 6)
    canv.setFillColor(MUTED)
    canv.setFont("DejaVu", 8)
    canv.drawCentredString(page_w / 2, 1.1 * cm, content["footer"])


def _header_footer(canv: pdfcanvas.Canvas, doc):
    if doc.page == 1:
        return  # cover has its own design
    canv.saveState()
    page_w, page_h = A4
    canv.setFillColor(BG)
    canv.rect(0, page_h - 20, page_w, 20, stroke=0, fill=1)
    _gradient_line(canv, 0, page_h - 22, page_w, 2.5)
    canv.setFillColor(ACCENT_CYAN)
    canv.setFont("DejaVu-Bold", 8)
    canv.drawString(1.8 * cm, page_h - 13, "Examinator")
    canv.setFillColor(MUTED)
    canv.setFont("DejaVu", 8)
    canv.drawRightString(page_w - 1.8 * cm, page_h - 13, "User guide")
    canv.setFillColor(BG_DEEP)
    canv.rect(0, 0, page_w, 18, stroke=0, fill=1)
    canv.setFillColor(MUTED)
    canv.setFont("DejaVu", 8)
    canv.drawCentredString(page_w / 2, 6, str(doc.page))
    canv.restoreState()


def _on_first_page(canv, doc, content, lang):
    _draw_cover_page(canv, content, lang)


def _content(lang: str) -> dict:
    shots = {
        "home": ("01_home.jpg", {
            "fr": "Figure — Accueil Examinator (menu latéral et programmes)",
            "en": "Figure — Examinator home (sidebar and programmes)",
            "it": "Figura — Home Examinator (menu laterale e programmi)",
            "es": "Figura — Inicio Examinator (menú lateral y programas)",
            "de": "Abbildung — Examinator-Startseite (Seitenmenü und Programme)",
        }),
        "register": ("02_register.jpg", {
            "fr": "Figure — Page Register (inscription / connexion par e-mail)",
            "en": "Figure — Register page (sign-up / sign-in by email)",
            "it": "Figura — Pagina Register (registrazione / accesso e-mail)",
            "es": "Figura — Página Register (registro / acceso por correo)",
            "de": "Abbildung — Register-Seite (Anmeldung per E-Mail)",
        }),
        "catalog": ("03_catalog.jpg", {
            "fr": "Figure — Certification tracks (catalogue des filières)",
            "en": "Figure — Certification tracks catalogue",
            "it": "Figura — Catalogo Certification tracks",
            "es": "Figura — Catálogo Certification tracks",
            "de": "Abbildung — Katalog Certification tracks",
        }),
        "search": ("09_search.jpg", {
            "fr": "Figure — Recherche de simulateurs (barre latérale et résultats)",
            "en": "Figure — Simulator search (sidebar bar and results)",
            "it": "Figura — Ricerca simulatori (barra laterale e risultati)",
            "es": "Figura — Búsqueda de simuladores (barra lateral y resultados)",
            "de": "Abbildung — Simulator-Suche (Seitenleiste und Ergebnisse)",
        }),
        "briefing": ("07_briefing.jpg", {
            "fr": "Figure — Briefing avant le démarrage de la simulation",
            "en": "Figure — Briefing before starting the simulation",
            "it": "Figura — Briefing prima della simulazione",
            "es": "Figura — Briefing antes de la simulación",
            "de": "Abbildung — Briefing vor der Simulation",
        }),
        "results": ("08_results.jpg", {
            "fr": "Figure — Results (score, sections, revue des questions)",
            "en": "Figure — Results (score, sections, question review)",
            "it": "Figura — Results (punteggio e revisione)",
            "es": "Figura — Results (puntuación y revisión)",
            "de": "Abbildung — Results (Punktzahl und Übersicht)",
        }),
        "profile": ("05_profile.jpg", {
            "fr": "Figure — My profile (historique et Export PDF)",
            "en": "Figure — My profile (history and PDF export)",
            "it": "Figura — My profile (cronologia ed export PDF)",
            "es": "Figura — My profile (historial y exportación PDF)",
            "de": "Abbildung — My profile (Verlauf und PDF-Export)",
        }),
        "calendar": ("06_calendar.jpg", {
            "fr": "Figure — My calendar (sessions du mois)",
            "en": "Figure — My calendar (monthly sessions)",
            "it": "Figura — My calendar (sessioni mensili)",
            "es": "Figura — My calendar (sesiones del mes)",
            "de": "Abbildung — My calendar (Monatssitzungen)",
        }),
        "help": ("04_help.jpg", {
            "fr": "Figure — User guide (choix de la langue du PDF)",
            "en": "Figure — User guide (PDF language selection)",
            "it": "Figura — User guide (scelta lingua PDF)",
            "es": "Figura — User guide (elección del idioma PDF)",
            "de": "Abbildung — User guide (PDF-Sprache wählen)",
        }),
    }

    # Reuse previous multilingual texts (compact)
    data = {
        "fr": {
            "doc_title": "Mode d'emploi",
            "subtitle": "Guide utilisateur des simulateurs de certification IT",
            "ui_note_title": "Langue de l'interface",
            "ui_note": (
                "Important : l'interface d'utilisation des simulateurs Examinator "
                "(menus, boutons, écrans d'examen, résultats) est disponible uniquement en anglais. "
                "Ce mode d'emploi est fourni dans plusieurs langues pour vous aider à vous orienter, "
                "mais les libellés affichés dans l'application restent en anglais."
            ),
            "toc_title": "Sommaire",
            "sections": [
                ("1. Présentation", [
                    "Examinator est une plateforme de simulation d'examens de certification IT "
                    "(Microsoft, CompTIA et programmes personnalisés). Elle permet de s'entraîner "
                    "dans des conditions proches de l'examen réel : durée limitée, questions à choix "
                    "unique ou multiple, et correction détaillée.",
                    "Le menu de gauche donne accès à l'accueil, à la barre de recherche, "
                    "aux filières (Certification tracks), au profil, au calendrier et à ce mode "
                    "d'emploi (User guide).",
                ], "home"),
                ("2. Créer un compte et se connecter", [
                    "Ouvrez Register depuis le menu de gauche.",
                    "Saisissez votre prénom, nom et adresse e-mail, puis validez.",
                    "Aucun mot de passe n'est requis : la même adresse e-mail vous reconnecte automatiquement.",
                    "Après inscription, votre compte est en attente de validation par l'administrateur.",
                ], "register"),
                ("3. Accès aux simulateurs", [
                    "Seul un administrateur peut approuver votre compte et vous attribuer les examens autorisés.",
                    "Tant que votre demande n'est pas validée, vous pouvez parcourir le catalogue mais pas démarrer une simulation.",
                    "Si un examen affiche « Access denied », contactez l'administrateur.",
                ], None),
                ("4. Parcourir le catalogue", [
                    "Utilisez Certification tracks pour Microsoft, CompTIA et les programmes personnalisés.",
                    "Ouvrez une famille de certification pour afficher les examens disponibles.",
                    "Start simulation n'est actif que si votre accès est approuvé et que le pool de questions est prêt.",
                ], "catalog"),
                ("5. Rechercher un simulateur", [
                    "Utilisez la barre Search exams… en haut du menu de gauche, disponible sur toutes les pages.",
                    "Saisissez un ou plusieurs mots-clés (code d'examen, titre, éditeur, niveau, rôle, produit…), "
                    "par exemple AZ-900, Azure ou Security, puis validez.",
                    "Plusieurs mots affinent la recherche : tous doivent correspondre.",
                    "La page de résultats liste les simulateurs trouvés ; vous pouvez ouvrir le briefing "
                    "ou la filière associée. Vous pouvez aussi aller sur /catalog/search.",
                ], "search"),
                ("6. Passer une simulation", [
                    "Briefing : lisez les règles (durée, nombre de questions, score), puis Start exam.",
                    "Pendant l'examen : chronomètre, Previous / Next et grille de questions.",
                    "Soumettez avec Submit exam, ou attendez la fin du temps (finalisation automatique).",
                ], "briefing"),
                ("7. Consulter les résultats", [
                    "Results affiche le score global, correct / incorrect / non répondu, et l'analyse par section.",
                    "La revue des questions montre vos réponses, les bonnes réponses et les explications.",
                    "Utilisez Retry pour vous entraîner à nouveau.",
                ], "results"),
                ("8. Profil et export PDF", [
                    "My profile regroupe vos statistiques et l'historique des tentatives.",
                    "Dans Summary by exam, cliquez sur Export PDF pour télécharger un rapport par examen.",
                ], "profile"),
                ("9. Calendrier", [
                    "My calendar affiche vos sessions sur un calendrier mensuel.",
                    "Cliquez sur une session pour ouvrir ses résultats.",
                ], "calendar"),
                ("10. Aide et support", [
                    "Ce mode d'emploi est accessible depuis User guide, dans la langue de votre choix.",
                    "Pour l'accès ou le compte, contactez l'administrateur de la plateforme.",
                ], "help"),
            ],
            "footer": "Examinator — simulation d'entraînement, non un certificat officiel.",
            "legal_title": "Mentions légales et conditions d'usage",
            "legal": (
                "© Aguilera Lab, tous droits réservés. L'usage de cette solution est réservé "
                "aux personnes ayant suivi une formation avec Michel Aguilera. C'est un accès "
                "fourni gracieusement pour préparer et valider les connaissances qui ont été "
                "abordées durant les cours. Ces simulateurs ne donnent en aucun cas une garantie "
                "de résultats aux examens officiels finaux et ne sont pas une alternative "
                "officielle. Veuillez noter que tout usage abusif entraînera automatiquement un "
                "retrait d'accès, sans autre préavis. Pour toutes questions, veuillez vous "
                "adresser au formateur qui vous a suivi durant les cours."
            ),
            "shots": shots,
        },
        "en": {
            "doc_title": "User Guide",
            "subtitle": "User manual for IT certification exam simulators",
            "ui_note_title": "Interface language",
            "ui_note": (
                "Important: the Examinator simulator user interface "
                "(menus, buttons, exam screens, results) is available in English only. "
                "This guide is provided in several languages to help you get started, "
                "but all labels inside the application remain in English."
            ),
            "toc_title": "Contents",
            "sections": [
                ("1. Overview", [
                    "Examinator is an IT certification exam simulation platform "
                    "(Microsoft, CompTIA and custom programmes) for timed practice with detailed feedback.",
                    "The left-hand menu opens Home, the search bar, Certification tracks, Profile, "
                    "Calendar and User guide.",
                ], "home"),
                ("2. Create an account and sign in", [
                    "Open Register from the left-hand menu.",
                    "Enter first name, last name and email, then submit.",
                    "No password is required: the same email signs you back in.",
                    "After registration, your account waits for administrator approval.",
                ], "register"),
                ("3. Access to simulators", [
                    "Only an administrator can approve your account and grant exam simulators.",
                    "While pending, you can browse the catalogue but cannot start a simulation.",
                    "If an exam shows Access denied, contact the administrator.",
                ], None),
                ("4. Browse the catalogue", [
                    "Use Certification tracks for Microsoft, CompTIA and custom programmes.",
                    "Open a certification family to see available exams.",
                    "Start simulation is enabled only when access is approved and the pool is ready.",
                ], "catalog"),
                ("5. Search for a simulator", [
                    "Use the Search exams… bar at the top of the left-hand menu, available on every page.",
                    "Enter one or more keywords (exam code, title, vendor, level, role, product…), "
                    "for example AZ-900, Azure or Security, then submit.",
                    "Multiple words narrow the search: all tokens must match.",
                    "The results page lists matching simulators; open the briefing or the related track. "
                    "You can also go to /catalog/search.",
                ], "search"),
                ("6. Take a simulation", [
                    "Briefing: read the rules, then click Start exam.",
                    "During the exam: countdown timer, Previous / Next and question grid.",
                    "Submit with Submit exam, or wait until time expires.",
                ], "briefing"),
                ("7. Review your results", [
                    "Results shows overall score, counts and section breakdown.",
                    "Question review lists your answers, correct options and explanations.",
                    "Use Retry to practise the same exam again.",
                ], "results"),
                ("8. Profile and PDF export", [
                    "My profile shows statistics and full attempt history.",
                    "Under Summary by exam, click Export PDF for a per-exam report.",
                ], "profile"),
                ("9. Calendar", [
                    "My calendar displays sessions on a monthly grid.",
                    "Click a session to open its results.",
                ], "calendar"),
                ("10. Help and support", [
                    "This guide is always available from User guide in your language.",
                    "For access or account questions, contact the platform administrator.",
                ], "help"),
            ],
            "footer": "Examinator — practice simulation, not an official certificate.",
            "legal_title": "Legal notice and terms of use",
            "legal": (
                "© Aguilera Lab, all rights reserved. Use of this solution is reserved for "
                "people who have attended training with Michel Aguilera. Access is provided "
                "free of charge to prepare for and validate the knowledge covered during the "
                "courses. These simulators do not in any way guarantee results on the official "
                "final exams and are not an official alternative. Please note that any misuse "
                "will automatically result in access being withdrawn, without further notice. "
                "For any questions, please contact the trainer who accompanied you during the "
                "courses."
            ),
            "shots": shots,
        },
        "it": {
            "doc_title": "Manuale utente",
            "subtitle": "Guida ai simulatori di esami di certificazione IT",
            "ui_note_title": "Lingua dell'interfaccia",
            "ui_note": (
                "Importante: l'interfaccia dei simulatori Examinator "
                "(menu, pulsanti, schermate d'esame, risultati) è disponibile solo in inglese. "
                "Questo manuale è in più lingue; le etichette restano in inglese."
            ),
            "toc_title": "Indice",
            "sections": [
                ("1. Presentazione", [
                    "Examinator è una piattaforma di simulazione di esami IT (Microsoft, CompTIA e programmi personalizzati).",
                    "Il menu a sinistra apre Home, la barra di ricerca, Certification tracks, Profile, "
                    "Calendar e User guide.",
                ], "home"),
                ("2. Creare un account e accedere", [
                    "Aprite Register dal menu a sinistra.",
                    "Inserite nome, cognome ed e-mail, poi confermate.",
                    "Nessuna password: la stessa e-mail vi riconnette.",
                    "L'account resta in attesa di approvazione dell'amministratore.",
                ], "register"),
                ("3. Accesso ai simulatori", [
                    "Solo un amministratore può approvare l'account e assegnare gli esami.",
                    "In attesa potete sfogliare il catalogo ma non avviare una simulazione.",
                    "Se compare Access denied, contattate l'amministratore.",
                ], None),
                ("4. Sfogliare il catalogo", [
                    "Usate Certification tracks per Microsoft, CompTIA e programmi personalizzati.",
                    "Aprite una famiglia di certificazione per vedere gli esami.",
                    "Start simulation è attivo solo con accesso approvato e pool pronto.",
                ], "catalog"),
                ("5. Cercare un simulatore", [
                    "Usate la barra Search exams… in alto nel menu a sinistra, disponibile su ogni pagina.",
                    "Inserite una o più parole chiave (codice esame, titolo, vendor, livello, ruolo, prodotto…), "
                    "ad esempio AZ-900, Azure o Security, poi confermate.",
                    "Più parole restringono la ricerca: tutte devono corrispondere.",
                    "La pagina dei risultati elenca i simulatori trovati; aprite il briefing o il percorso. "
                    "Potete anche andare su /catalog/search.",
                ], "search"),
                ("6. Svolgere una simulazione", [
                    "Briefing: leggete le regole, poi Start exam.",
                    "Durante l'esame: timer, Previous / Next e griglia domande.",
                    "Inviare con Submit exam o attendere la fine del tempo.",
                ], "briefing"),
                ("7. Consultare i risultati", [
                    "Results mostra punteggio, conteggi e analisi per sezione.",
                    "La revisione mostra risposte, opzioni corrette e spiegazioni.",
                ], "results"),
                ("8. Profilo ed esportazione PDF", [
                    "My profile raccoglie statistiche e cronologia.",
                    "In Summary by exam, Export PDF scarica il report per esame.",
                ], "profile"),
                ("9. Calendario", [
                    "My calendar mostra le sessioni sulla griglia mensile.",
                    "Cliccate una sessione per i risultati.",
                ], "calendar"),
                ("10. Aiuto e supporto", [
                    "Questo manuale è disponibile da User guide nella lingua scelta.",
                    "Per accessi o account, contattate l'amministratore.",
                ], "help"),
            ],
            "footer": "Examinator — simulazione di pratica, non un certificato ufficiale.",
            "legal_title": "Note legali e condizioni d'uso",
            "legal": (
                "© Aguilera Lab, tutti i diritti riservati. L'uso di questa soluzione è riservato "
                "alle persone che hanno seguito una formazione con Michel Aguilera. Si tratta di "
                "un accesso fornito gratuitamente per preparare e validare le conoscenze trattate "
                "durante i corsi. Questi simulatori non forniscono in alcun caso una garanzia di "
                "risultati agli esami ufficiali finali e non sono un'alternativa ufficiale. "
                "Si prega di notare che qualsiasi uso abusivo comporterà automaticamente la "
                "revoca dell'accesso, senza ulteriore preavviso. Per qualsiasi domanda, rivolgersi "
                "al formatore che vi ha seguito durante i corsi."
            ),
            "shots": shots,
        },
        "es": {
            "doc_title": "Manual de usuario",
            "subtitle": "Guía de los simuladores de exámenes de certificación IT",
            "ui_note_title": "Idioma de la interfaz",
            "ui_note": (
                "Importante: la interfaz de los simuladores Examinator "
                "(menús, botones, pantallas de examen, resultados) solo está disponible en inglés. "
                "Este manual se ofrece en varios idiomas; las etiquetas siguen en inglés."
            ),
            "toc_title": "Contenido",
            "sections": [
                ("1. Presentación", [
                    "Examinator es una plataforma de simulación de exámenes IT (Microsoft, CompTIA y programas personalizados).",
                    "El menú izquierdo abre Home, la barra de búsqueda, Certification tracks, Profile, "
                    "Calendar y User guide.",
                ], "home"),
                ("2. Crear una cuenta e iniciar sesión", [
                    "Abra Register desde el menú izquierdo.",
                    "Introduzca nombre, apellidos y correo, y confirme.",
                    "Sin contraseña: el mismo correo le vuelve a conectar.",
                    "La cuenta queda pendiente de aprobación del administrador.",
                ], "register"),
                ("3. Acceso a los simuladores", [
                    "Solo un administrador puede aprobar la cuenta y asignar exámenes.",
                    "Mientras está pendiente, puede ver el catálogo pero no iniciar una simulación.",
                    "Si aparece Access denied, contacte al administrador.",
                ], None),
                ("4. Explorar el catálogo", [
                    "Use Certification tracks para Microsoft, CompTIA y programas personalizados.",
                    "Abra una familia de certificación para ver los exámenes.",
                    "Start simulation solo está activo con acceso aprobado y banco listo.",
                ], "catalog"),
                ("5. Buscar un simulador", [
                    "Use la barra Search exams… en la parte superior del menú izquierdo, disponible en todas las páginas.",
                    "Introduzca una o varias palabras clave (código de examen, título, editor, nivel, rol, producto…), "
                    "por ejemplo AZ-900, Azure o Security, y confirme.",
                    "Varias palabras afinan la búsqueda: todas deben coincidir.",
                    "La página de resultados lista los simuladores encontrados; abra el briefing o la pista. "
                    "También puede ir a /catalog/search.",
                ], "search"),
                ("6. Realizar una simulación", [
                    "Briefing: lea las reglas y pulse Start exam.",
                    "Durante el examen: temporizador, Previous / Next y cuadrícula.",
                    "Envíe con Submit exam o espere a que termine el tiempo.",
                ], "briefing"),
                ("7. Consultar los resultados", [
                    "Results muestra puntuación, conteos y análisis por sección.",
                    "La revisión muestra respuestas, opciones correctas y explicaciones.",
                ], "results"),
                ("8. Perfil y exportación PDF", [
                    "My profile agrupa estadísticas e historial.",
                    "En Summary by exam, Export PDF descarga el informe por examen.",
                ], "profile"),
                ("9. Calendario", [
                    "My calendar muestra las sesiones en la cuadrícula mensual.",
                    "Pulse una sesión para abrir resultados.",
                ], "calendar"),
                ("10. Ayuda y soporte", [
                    "Este manual está en User guide en el idioma que elija.",
                    "Para accesos o cuenta, contacte al administrador.",
                ], "help"),
            ],
            "footer": "Examinator — simulación de práctica, no un certificado oficial.",
            "legal_title": "Aviso legal y condiciones de uso",
            "legal": (
                "© Aguilera Lab, todos los derechos reservados. El uso de esta solución está "
                "reservado a las personas que han seguido una formación con Michel Aguilera. "
                "Se trata de un acceso facilitado de forma gratuita para preparar y validar los "
                "conocimientos tratados durante los cursos. Estos simuladores no ofrecen en "
                "ningún caso una garantía de resultados en los exámenes oficiales finales y no "
                "son una alternativa oficial. Tenga en cuenta que cualquier uso abusivo "
                "conllevará automáticamente la retirada del acceso, sin otro preaviso. Para "
                "cualquier pregunta, diríjase al formador que le ha acompañado durante los cursos."
            ),
            "shots": shots,
        },
        "de": {
            "doc_title": "Benutzerhandbuch",
            "subtitle": "Anleitung für IT-Zertifizierungs-Prüfungssimulatoren",
            "ui_note_title": "Sprache der Oberfläche",
            "ui_note": (
                "Wichtig: Die Benutzeroberfläche der Examinator-Simulatoren "
                "(Menüs, Schaltflächen, Prüfungsbildschirme, Ergebnisse) ist nur auf Englisch verfügbar. "
                "Dieses Handbuch gibt es in mehreren Sprachen; die Beschriftungen bleiben auf Englisch."
            ),
            "toc_title": "Inhalt",
            "sections": [
                ("1. Übersicht", [
                    "Examinator ist eine Plattform zur Simulation von IT-Zertifizierungsprüfungen "
                    "(Microsoft, CompTIA und individuelle Programme).",
                    "Das linke Menü öffnet Home, die Suchleiste, Certification tracks, Profile, "
                    "Calendar und User guide.",
                ], "home"),
                ("2. Konto erstellen und anmelden", [
                    "Öffnen Sie Register im linken Menü.",
                    "Geben Sie Vorname, Nachname und E-Mail ein und bestätigen Sie.",
                    "Kein Passwort: dieselbe E-Mail meldet Sie erneut an.",
                    "Das Konto wartet auf Freigabe durch den Administrator.",
                ], "register"),
                ("3. Zugriff auf Simulatoren", [
                    "Nur ein Administrator kann das Konto freigeben und Prüfungen zuweisen.",
                    "Solange die Anfrage aussteht, können Sie den Katalog sehen, aber keine Simulation starten.",
                    "Bei Access denied wenden Sie sich an den Administrator.",
                ], None),
                ("4. Katalog durchsuchen", [
                    "Nutzen Sie Certification tracks für Microsoft, CompTIA und individuelle Programme.",
                    "Öffnen Sie eine Zertifizierungsfamilie für verfügbare Prüfungen.",
                    "Start simulation ist nur bei freigegebenem Zugriff und bereitem Pool aktiv.",
                ], "catalog"),
                ("5. Einen Simulator suchen", [
                    "Nutzen Sie die Leiste Search exams… oben im linken Menü — auf jeder Seite verfügbar.",
                    "Geben Sie ein oder mehrere Stichwörter ein (Prüfungscode, Titel, Anbieter, Niveau, Rolle, Produkt…), "
                    "z. B. AZ-900, Azure oder Security, und bestätigen Sie.",
                    "Mehrere Wörter grenzen die Suche ein: alle müssen passen.",
                    "Die Ergebnisseite listet passende Simulatoren; öffnen Sie das Briefing oder den Track. "
                    "Sie können auch /catalog/search aufrufen.",
                ], "search"),
                ("6. Eine Simulation absolvieren", [
                    "Briefing: Regeln lesen, dann Start exam.",
                    "Während der Prüfung: Countdown, Previous / Next und Frageraster.",
                    "Mit Submit exam senden oder Zeitablauf abwarten.",
                ], "briefing"),
                ("7. Ergebnisse ansehen", [
                    "Results zeigt Gesamtpunktzahl, Zählungen und Abschnittsauswertung.",
                    "Die Fragenübersicht zeigt Antworten, richtige Optionen und Erklärungen.",
                ], "results"),
                ("8. Profil und PDF-Export", [
                    "My profile zeigt Statistiken und Versuchshistorie.",
                    "Unter Summary by exam lädt Export PDF den Bericht je Prüfung.",
                ], "profile"),
                ("9. Kalender", [
                    "My calendar zeigt Sitzungen in der Monatsansicht.",
                    "Klicken Sie auf eine Sitzung für die Ergebnisse.",
                ], "calendar"),
                ("10. Hilfe und Support", [
                    "Dieses Handbuch ist unter User guide in Ihrer Sprache verfügbar.",
                    "Bei Zugriffs- oder Kontofragen den Administrator kontaktieren.",
                ], "help"),
            ],
            "footer": "Examinator — Übungssimulation, kein offizielles Zertifikat.",
            "legal_title": "Rechtliche Hinweise und Nutzungsbedingungen",
            "legal": (
                "© Aguilera Lab, alle Rechte vorbehalten. Die Nutzung dieser Lösung ist Personen "
                "vorbehalten, die eine Schulung bei Michel Aguilera absolviert haben. Der Zugang "
                "wird kostenlos bereitgestellt, um die während der Kurse behandelten Kenntnisse "
                "vorzubereiten und zu validieren. Diese Simulatoren bieten in keinem Fall eine "
                "Erfolgsgarantie für die offiziellen Abschlussprüfungen und sind keine offizielle "
                "Alternative. Bitte beachten Sie, dass jeder missbräuchliche Gebrauch automatisch "
                "zum Entzug des Zugangs führt, ohne weitere Vorankündigung. Bei Fragen wenden Sie "
                "sich an den Trainer, der Sie während der Kurse begleitet hat."
            ),
            "shots": shots,
        },
    }
    if lang not in data:
        raise ValueError(f"Unsupported language: {lang}")
    return data[lang]


def _screenshot_block(styles, shot_key: str, lang: str, shots: dict) -> list:
    file_name, captions = shots[shot_key]
    path = SHOT_DIR / file_name
    if not path.exists():
        return [Paragraph(f"[Screenshot missing: {file_name}]", styles["caption"])]
    # Large, clear screenshot using platypus Image (reliable embedding)
    max_w = 16.2 * cm
    max_h = 9.5 * cm
    img = Image(str(path))
    iw, ih = float(img.imageWidth), float(img.imageHeight)
    scale = min(max_w / iw, max_h / ih)
    img.drawWidth = iw * scale
    img.drawHeight = ih * scale
    caption = captions.get(lang, captions["en"])
    # Dark frame via table
    frame = Table([[img]], colWidths=[img.drawWidth + 8])
    frame.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BG),
        ("BOX", (0, 0), (-1, -1), 1.5, ACCENT_CYAN),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    wrap = Table([[frame]], colWidths=[16.5 * cm])
    wrap.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    return [Spacer(1, 3 * mm), wrap, Paragraph(caption, styles["caption"])]


def _legal_block(styles, content: dict) -> list:
    """Build the legal notice flowables (kept together on one page)."""
    legal_para = Paragraph(content["legal"], styles["legal_body"])
    legal_table = Table([[legal_para]], colWidths=[16.5 * cm])
    legal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7fafc")),
        ("BOX", (0, 0), (-1, -1), 1.2, BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [
        Paragraph(content["legal_title"], styles["legal_title"]),
        legal_table,
        Spacer(1, 5 * mm),
        Paragraph(content["footer"], styles["footer"]),
    ]


def build_user_manual_pdf(lang: str = "en") -> bytes:
    lang = lang.strip().lower()
    if lang not in MANUAL_LANGUAGES:
        raise ValueError("Unsupported language")
    content = _content(lang)
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.5 * cm,
        title=f"Examinator — {content['doc_title']}",
        author="Examinator",
    )

    story = []
    # Page 1 is drawn entirely by cover canvas; story needs a blank first page then break
    story.append(Spacer(1, 1))
    story.append(PageBreak())

    # TOC page
    story.append(Paragraph(content["toc_title"], styles["toc_title"]))
    for title, _, _ in content["sections"]:
        story.append(Paragraph(f"•  {title}", styles["toc"]))
    story.append(Spacer(1, 6 * mm))
    note_title = Paragraph(content["ui_note_title"], styles["note_title"])
    note_body = Paragraph(content["ui_note"], styles["note"])
    note_table = Table([[note_title], [note_body]], colWidths=[16.5 * cm])
    note_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
        ("BOX", (0, 0), (-1, -1), 1.5, ACCENT_CYAN),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(note_table)
    story.append(PageBreak())

    for index, (title, paragraphs, shot_key) in enumerate(content["sections"]):
        story.append(Paragraph(title, styles["h1"]))
        if len(paragraphs) == 1 or title.startswith("1."):
            for p in paragraphs:
                story.append(Paragraph(p, styles["body"]))
        else:
            items = [
                ListItem(Paragraph(p, styles["bullet"]), leftIndent=4, bulletColor=ACCENT_PURPLE)
                for p in paragraphs
            ]
            story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=10))
        if shot_key:
            story.extend(_screenshot_block(styles, shot_key, lang, content["shots"]))
        if index < len(content["sections"]) - 1:
            story.append(Spacer(1, 4 * mm))

    # Pin legal notice to the bottom of the last page (no forced PageBreak:
    # that was creating a blank page before the disclaimer).
    story.append(BottomAnchored(_legal_block(styles, content)))

    def first_page(canv, doc):
        _draw_cover_page(canv, content, lang)

    doc.build(story, onFirstPage=first_page, onLaterPages=_header_footer)
    return buffer.getvalue()


def manual_filename(lang: str) -> str:
    return f"examinator_user_guide_{lang.strip().lower()}_v{MANUAL_VERSION}.pdf"


def manual_disk_path(lang: str) -> Path:
    return MANUALS_DIR / manual_filename(lang)


def list_manual_languages() -> list[dict]:
    return [
        {
            "code": code,
            "label": meta["label"],
            "flag": meta["flag"],
            "url": f"/help/manual/{code}.pdf?v={MANUAL_VERSION}",
        }
        for code, meta in MANUAL_LANGUAGES.items()
    ]


def generate_all_manuals() -> dict[str, Path]:
    """Write all language PDFs to disk and remove older versioned files."""
    MANUALS_DIR.mkdir(parents=True, exist_ok=True)
    # Remove previous generated manuals
    for old in MANUALS_DIR.glob("examinator_user_guide_*.pdf"):
        old.unlink(missing_ok=True)
    written = {}
    for code in MANUAL_LANGUAGES:
        pdf = build_user_manual_pdf(code)
        path = manual_disk_path(code)
        path.write_bytes(pdf)
        written[code] = path
    return written
