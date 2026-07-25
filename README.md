# Examinator — IT Certification Exam Simulator

Web platform for Microsoft and IT certification exam practice
(Microsoft, CompTIA, and custom Examinator simulations).

**Documentation technique complète** :
[`docs/DOCUMENTATION_TECHNIQUE.md`](docs/DOCUMENTATION_TECHNIQUE.md)

**Installation automatisée** :
[`scripts/install_examinator.sh`](scripts/install_examinator.sh) — voir aussi [`docs/INSTALLATION.md`](docs/INSTALLATION.md)

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
| Python | **3.13** (3.11+ may work; installer prefers 3.13) |
| Privileges | root / sudo for full install |
| Optional | nginx reverse proxy |

---

## Fresh install (recommended)

```bash
git clone https://git.aguilera.ch/Aguilera_Lab/Examinator.git
cd Examinator
sudo ./scripts/install_examinator.sh --admin-email you@example.com
```

The installer will:

1. Sync or use the checkout under `/opt/exam-simulator` (default)
2. Install system packages (Python venv, DejaVu fonts, …)
3. Create `venv/` and install `requirements.txt`
4. Create `data/` + `.env` (random `SECRET_KEY`)
5. Seed the catalog
6. Generate PDF manuals (when possible)
7. Install and start `exam-simulator.service`

Clone directly into the target directory:

```bash
sudo ./scripts/install_examinator.sh --clone --dir /opt/exam-simulator --admin-email you@example.com
```

Useful flags: `--skip-seed`, `--skip-systemd`, `--skip-manuals`, `--non-interactive`, `--help`.

Open: http://localhost:8000  
Register with the e-mail set in `ADMIN_EMAIL` to get administrator access.

Full guide: [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

---

## Manual install (alternative)

```bash
sudo mkdir -p /opt
sudo git clone https://git.aguilera.ch/Aguilera_Lab/Examinator.git /opt/exam-simulator
cd /opt/exam-simulator

python3 -m venv venv
./venv/bin/pip install -r requirements.txt
sudo apt-get install -y fonts-dejavu-core

mkdir -p data
cp .env.example .env
# Edit .env — at least ADMIN_EMAIL and SECRET_KEY

PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/seed_data.py
sudo ./deploy/install-systemd.sh
```

Dev run without systemd:

```bash
PYTHONPATH=/opt/exam-simulator ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Production (systemd)

```bash
sudo INSTALL_DIR=/opt/exam-simulator /opt/exam-simulator/deploy/install-systemd.sh
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

Copy `.env.example` → `.env` (or let the installer create it). Main variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite path (default under `/opt/exam-simulator/data/`) |
| `ADMIN_EMAIL` | Sole administrator identity |
| `SECRET_KEY` | Set a strong random value |
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

Prefer the **Sync Microsoft** tab in the admin UI (administrator session required).

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
docs/         Technical documentation + Excel template
scripts/      Installer, seed, sync, manuals, quality tools
tests/        pytest suite
requirements.txt
.env.example
```

**Not published** (local only): `venv/`, `.env`, SQLite database under `data/`.
