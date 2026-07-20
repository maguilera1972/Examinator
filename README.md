# Examinator — IT Certification Exam Simulator

Web platform for Microsoft and IT certification exam practice
(Microsoft, CompTIA, and custom Examinator simulations).

**Documentation technique complète** :
[`docs/DOCUMENTATION_TECHNIQUE.md`](docs/DOCUMENTATION_TECHNIQUE.md)

---

## Features

- User registration (first name, last name, email — no password)
- Admin approval and per-exam access grants
- Exam catalog (Microsoft, CompTIA, Examinator topics / custom)
- Custom exam creation with category assignment
- 50 random questions per session (configurable), timer, auto-submit
- Section results, review, profile PDF export, calendar
- Multilingual PDF user manuals (FR / EN / IT / ES / DE)
- Excel / JSON question import and pool purge per exam

---

## Prerequisites

| Item | Requirement |
|------|-------------|
| OS | Linux (tested on Proxmox LXC) |
| Python | **3.13** |
| Fonts (PDF manuals) | `fonts-dejavu-core` |
| Optional | nginx reverse proxy |

---

## Fresh install

```bash
# 1. Clone
sudo mkdir -p /opt
sudo git clone https://git.aguilera.ch/Aguilera_Lab/Examinator.git /opt/exam-simulator
cd /opt/exam-simulator

# 2. Python venv + dependencies
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. System fonts (user manuals)
sudo apt-get update
sudo apt-get install -y fonts-dejavu-core

# 4. Runtime data + config
mkdir -p data
cp .env.example .env
# Edit .env — at least ADMIN_EMAIL and SECRET_KEY
nano .env

# 5. Branding assets (logo / favicon) if available
# ./scripts/install_branding.sh

# 6. Seed catalog (Microsoft / CompTIA / topics)
PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/seed_data.py

# 7. (Optional) Generate user manuals
PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/generate_user_manuals.py

# 8. Run (dev)
PYTHONPATH=/opt/exam-simulator ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open: http://localhost:8000  
Register with the e-mail set in `ADMIN_EMAIL` to get administrator access.

---

## Production (systemd)

```bash
sudo /opt/exam-simulator/deploy/install-systemd.sh
systemctl status exam-simulator
journalctl -u exam-simulator -f
```

Optional nginx reverse proxy: `deploy/nginx-exam-simulator.conf`.

After Python code changes:

```bash
systemctl restart exam-simulator
```

---

## Configuration

Copy `.env.example` → `.env`. Main variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite path (default under `/opt/exam-simulator/data/`) |
| `ADMIN_EMAIL` | Sole administrator identity |
| `SECRET_KEY` | Reserved (set a strong value for future use) |
| `QUESTIONS_PER_SESSION` | Default session size |
| `SESSION_COOKIE` | Auth cookie name |

Full details: [`docs/DOCUMENTATION_TECHNIQUE.md`](docs/DOCUMENTATION_TECHNIQUE.md).

---

## Import questions

### Modèle Excel (inclus dans le dépôt)

- Fichier : [`docs/excel/examinator_question_bank_template.xlsx`](docs/excel/examinator_question_bank_template.xlsx)
- Guide d’alimentation : [`docs/excel/ALIMENTATION_QUESTIONS.md`](docs/excel/ALIMENTATION_QUESTIONS.md)

### Excel (admin UI)

Administration → **Importer** → choose target exam → upload `.xlsx`.

### JSON (API)

```bash
curl -X POST "http://localhost:8000/api/admin/import/json?exam_code=AZ-900" \
  -F "file=@questions.json"
```

JSON format:

```json
[
  {
    "section": "Describe cloud concepts",
    "question_type": "single",
    "text": "Question text in English?",
    "explanation": "Why the answer is correct.",
    "external_id": "unique-id-001",
    "options": [
      {"label": "A", "text": "Option A", "is_correct": false},
      {"label": "B", "text": "Option B", "is_correct": true}
    ]
  }
]
```

---

## Sync Microsoft catalog

```bash
curl -X POST http://localhost:8000/api/admin/sync/microsoft
```

(Admin session cookie required for API admin routes; prefer the **Sync Microsoft** tab in the admin UI.)

External scrapers (ExamTopics, etc.) are stubs — import converted files manually.

---

## Quality checks (cron)

```bash
0 3 * * * cd /opt/exam-simulator && PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/quality_check.py
```

Repair pools:

```bash
PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/repair_pools.py
```

---

## Tests

```bash
cd /opt/exam-simulator
PYTHONPATH=/opt/exam-simulator ./venv/bin/python -m pytest tests/ -q
```

(`pytest` must be installed in the venv: `./venv/bin/pip install pytest`)

---

## Repository layout

```
app/          FastAPI application (routes, services, templates, static)
deploy/       systemd unit + nginx sample
docs/         Technical documentation
scripts/      Seed, sync, manuals, quality tools
tests/        pytest suite
requirements.txt
.env.example
```

**Not published** (local only): `venv/`, `.env`, SQLite database under `data/`.
