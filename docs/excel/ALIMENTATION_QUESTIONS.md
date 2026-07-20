# Alimentation des questions Examinator (fichier Excel)

Ce dossier contient le **modèle Excel officiel** pour créer ou mettre à jour les banques de questions des simulateurs.

| Fichier | Rôle |
|---------|------|
| [`examinator_question_bank_template.xlsx`](examinator_question_bank_template.xlsx) | Modèle multi-examens à télécharger et remplir |

Vous pouvez aussi télécharger un modèle **par examen** depuis l’interface d’administration (onglet **Importer**), une fois Examinator installé.

---

## Principe

1. L’examen doit **exister** dans Examinator (catalogue Microsoft / CompTIA / topic, ou examen **custom** créé dans l’admin).
2. Vous remplissez le fichier Excel (une ligne = une question).
3. Vous importez le fichier via **Administration → Importer**, en choisissant éventuellement l’**examen cible**.
4. Les questions alimentent le **pool** de cet examen ; les sessions tirent ensuite un sous-ensemble aléatoire.

Pour remplacer entièrement une banque obsolète : **vider le pool** de l’examen, puis réimporter le fichier à jour.

---

## Structure du classeur

Le modèle contient en général trois feuilles :

### 1. `Instructions`

Rappel des colonnes et conseils d’import (en anglais dans le fichier).

### 2. `Exams` (ou `Exam`)

Liste de référence des codes d’examens connus au moment de la génération du modèle (`exam_code`, titre, vendor, etc.).

Utilisez ces codes dans la colonne `exam_code` de la feuille Questions, **ou** sélectionnez l’examen cible dans l’UI d’import (il écrase alors le code présent dans le fichier).

### 3. `Questions` (obligatoire)

C’est la feuille à remplir. Colonnes :

| Colonne | Obligatoire | Description |
|---------|-------------|-------------|
| `exam_code` | Oui* | Code examen (`AZ-900`, `SIM-DB001`, `CUST-SEC01`…). *Peut être forcé par l’examen cible à l’import. |
| `question_id` | Non | Identifiant stable unique par examen (ex. `AZ900-001`). Utile pour **mettre à jour** une question déjà importée. Si vide → généré automatiquement. |
| `section` | Non | Domaine / section (ex. « Describe cloud concepts »). Créée si absente ; sinon `General`. |
| `question_type` | Non | `single` (une bonne réponse) ou `multiple` (plusieurs). Alias acceptés : `qcu`, `qcm`, etc. Si vide → déduit de `correct_answers`. |
| `question_text` | Oui | Énoncé de la question. |
| `option_a` … `option_f` | Oui (min. 2) | Propositions de réponse. Laissez vides les options inutilisées. |
| `correct_answers` | Oui | Lettre(s) correctes : `A`, `A,B`, `AB`, `1,3`, `A et B`, etc. |
| `explanation` | Non | Explication affichée après la session / en revue. |

**Exemples fournis dans le modèle** (à remplacer ou compléter) :

- une question `single` (type AZ-900) ;
- une question `multiple` (type simulation).

---

## Comment importer

### Via l’interface (recommandé)

1. Connectez-vous en **administrateur** (`ADMIN_EMAIL`).
2. Ouvrez **Administration**.
3. Onglet **Importer**.
4. (Optionnel) choisissez l’**examen cible** dans la liste.
5. Sélectionnez votre fichier `.xlsx`.
6. Cochez « Remplacer les questions existantes… » **uniquement** si vous voulez désactiver l’ancien pool des examens présents dans le fichier avant l’import.
7. Cliquez **Importer depuis Excel**.

### Si le fichier contient un autre `exam_code`

Exemple : le fichier indique `IDK-001` mais vous choisissez la cible `TOP-IN001`.

→ Toutes les questions sont importées dans `TOP-IN001`. Ce n’est **pas une erreur** : un message d’information (Note) le confirme.

### Via l’API (JSON)

Pour un flux JSON plutôt qu’Excel, voir le [README](../README.md) (`/api/admin/import/json`).

---

## Bonnes pratiques

- Gardez des `question_id` **stables** pour mettre à jour les questions sans doublons.
- Une banque doit contenir **au moins** autant de questions uniques que `questions_per_session` (souvent 50) pour qu’une session puisse démarrer.
- Après import, vérifiez l’onglet **Pools** (qualité, doublons, « Session ready »).
- Pour un examen custom neuf : créez d’abord l’examen (onglet **Créer un examen**), puis importez.
- Ne commitez pas de banques de questions propriétaires dans le dépôt public si le contenu est confidentiel : le modèle seul suffit pour l’installation.

---

## Régénérer le modèle depuis le code

Sur une instance déjà installée (avec catalogue synchronisé) :

```bash
cd /opt/exam-simulator
PYTHONPATH=/opt/exam-simulator ./venv/bin/python scripts/generate_excel_templates.py
```

Les fichiers sont écrits sous `data/excel-templates/` (local, non versionné).  
Pour mettre à jour le modèle publié dans ce dépôt :

```bash
PYTHONPATH=/opt/exam-simulator ./venv/bin/python -c "
from pathlib import Path
from app.database import SessionLocal
from app.services.excel_import_service import build_question_bank_workbook
db = SessionLocal()
Path('docs/excel/examinator_question_bank_template.xlsx').write_bytes(build_question_bank_workbook(db))
db.close()
"
```

---

## Dépannage rapide

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| `Exam … not found` | Code inconnu | Créer l’examen ou synchroniser le catalogue |
| Session impossible | Moins de N questions uniques | Enrichir le pool / dédupliquer |
| Questions « manquantes » | Mauvais examen cible | Vérifier la cible à l’import et le `exam_code` |
| Doublons | Mêmes énoncés / fingerprints | Onglet Pools → déduplication |
