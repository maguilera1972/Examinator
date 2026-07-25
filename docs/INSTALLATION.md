# Installation d’Examinator

Ce guide décrit comment reproduire une instance à partir du dépôt public.

**Dépôt :** https://git.aguilera.ch/Aguilera_Lab/Examinator

---

## Méthode recommandée — script bash

Le script [`scripts/install_examinator.sh`](../scripts/install_examinator.sh) automatise l’installation.

### À partir d’un clone local

```bash
git clone https://git.aguilera.ch/Aguilera_Lab/Examinator.git
cd Examinator
sudo ./scripts/install_examinator.sh --admin-email admin@example.com
```

Par défaut, les fichiers sont synchronisés vers `/opt/exam-simulator`, puis :

- paquets système (Python, venv, polices DejaVu, git, rsync…)
- environnement virtuel + dépendances Python
- répertoire `data/` et fichier `.env`
- seed du catalogue
- génération des manuels PDF (si possible)
- service systemd `exam-simulator` (enable + start)

### Cloner directement dans le répertoire cible

```bash
sudo ./scripts/install_examinator.sh \
  --clone \
  --dir /opt/exam-simulator \
  --admin-email admin@example.com
```

### Options utiles

| Option | Effet |
|--------|--------|
| `--dir PATH` | Répertoire d’installation (défaut `/opt/exam-simulator`) |
| `--repo-url URL` | URL Git (défaut `https://git.aguilera.ch/Aguilera_Lab/Examinator.git`) |
| `--clone` | Clone / met à jour le dépôt dans `--dir` |
| `--admin-email EMAIL` | Valeur `ADMIN_EMAIL` dans `.env` |
| `--skip-seed` | Ne pas exécuter `seed_data.py` |
| `--skip-systemd` | Ne pas installer le service |
| `--skip-manuals` | Ne pas régénérer les PDF |
| `--skip-branding` | Ne pas exécuter `install_branding.sh` |
| `--non-interactive` | Pas de prompt (utile en CI / automation) |
| `--help` | Aide |

### Vérification

```bash
systemctl status exam-simulator
curl -I http://localhost:8000/
```

Inscrivez-vous avec l’e-mail `ADMIN_EMAIL` pour obtenir les droits d’administration.

---

## Méthode manuelle

Voir la section « Manual install » du [README](../README.md).

Service seul :

```bash
sudo INSTALL_DIR=/opt/exam-simulator /opt/exam-simulator/deploy/install-systemd.sh
```

---

## Après installation

1. Contrôler `/opt/exam-simulator/.env`
2. Importer des questions : modèle Excel dans [`docs/excel/`](excel/)
3. Reverse proxy optionnel : `deploy/nginx-exam-simulator.conf`
4. Documentation technique : [`DOCUMENTATION_TECHNIQUE.md`](DOCUMENTATION_TECHNIQUE.md)

---

## Mise à jour depuis Git

```bash
cd /opt/exam-simulator
sudo git pull --ff-only
sudo ./venv/bin/pip install -r requirements.txt
sudo systemctl restart exam-simulator
```

Ou relancer l’installeur depuis un checkout à jour (il préserve `.env` et la base existants) :

```bash
cd /chemin/vers/checkout-Examinator
sudo ./scripts/install_examinator.sh --dir /opt/exam-simulator --non-interactive --skip-seed
```
