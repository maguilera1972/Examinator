#!/usr/bin/env bash
# Publish local Examinator changes to the public Gitea repository.
# Token is read from a local secrets file (never committed).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TOKEN_FILE="${EXAMINATOR_GITEA_TOKEN_FILE:-/root/.config/examinator/gitea_token}"
GITEA_HOST="${EXAMINATOR_GITEA_HOST:-172.16.12.12:3000}"
GITEA_OWNER="${EXAMINATOR_GITEA_OWNER:-Aguilera_Lab}"
GITEA_REPO="${EXAMINATOR_GITEA_REPO:-Examinator}"
GITEA_USER="${EXAMINATOR_GITEA_USER:-Michel}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing token file: $TOKEN_FILE" >&2
  echo "Create it with the Gitea personal access token (chmod 600)." >&2
  exit 1
fi

TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"
if [[ -z "$TOKEN" ]]; then
  echo "Token file is empty: $TOKEN_FILE" >&2
  exit 1
fi

if [[ ! -d .git ]]; then
  echo "Not a git repository: $ROOT" >&2
  exit 1
fi

# Default remote without credentials
CLEAN_URL="http://${GITEA_HOST}/${GITEA_OWNER}/${GITEA_REPO}.git"
AUTH_URL="http://${GITEA_USER}:${TOKEN}@${GITEA_HOST}/${GITEA_OWNER}/${GITEA_REPO}.git"

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "$CLEAN_URL"
else
  git remote set-url origin "$CLEAN_URL"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" == "HEAD" ]]; then
  BRANCH="main"
fi

MSG="${1:-}"
if [[ -z "$MSG" ]]; then
  MSG="Update Examinator from deployment host."
fi

# Stage everything except ignored secrets
git add -A

if git diff --cached --quiet; then
  # Still push in case local commits are ahead
  if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    AHEAD="$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
  else
    AHEAD=1
  fi
  if [[ "${AHEAD}" == "0" ]]; then
    echo "Nothing to commit or push."
    exit 0
  fi
  echo "No new staged changes; pushing existing commits..."
else
  git -c user.name="${GIT_AUTHOR_NAME:-Michel Aguilera}" \
      -c user.email="${GIT_AUTHOR_EMAIL:-michel@aguilera.ch}" \
      commit -m "$MSG"
fi

git push "$AUTH_URL" "HEAD:refs/heads/${BRANCH}"
git remote set-url origin "$CLEAN_URL"
echo "Published to ${CLEAN_URL} (branch ${BRANCH})."
