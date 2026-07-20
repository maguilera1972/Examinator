#!/bin/bash
# Install logo.png and favicon.png into app/static/img/
set -euo pipefail
DEST="/opt/exam-simulator/app/static/img"
SRC="${1:-/opt/exam-simulator/branding}"

resolve() {
  local name="$1"
  if [[ -f "$SRC/$name" ]]; then echo "$SRC/$name"; return; fi
  # Cursor attachment UUID filenames
  case "$name" in
    logo.png) [[ -f "$SRC/logo-b46de37f-8f16-4d35-b93a-37ea2350b622.png" ]] && echo "$SRC/logo-b46de37f-8f16-4d35-b93a-37ea2350b622.png" && return ;;
    favicon.png) [[ -f "$SRC/favicon-7aaef37f-4d81-4ecc-985c-498ef9407fb5.png" ]] && echo "$SRC/favicon-7aaef37f-4d81-4ecc-985c-498ef9407fb5.png" && return ;;
  esac
  return 1
}

for name in logo.png favicon.png; do
  if src=$(resolve "$name"); then
    cp "$src" "$DEST/$name"
    echo "Installed $DEST/$name from $src"
  else
    echo "WARN: $name not found in $SRC" >&2
  fi
done

[[ -f "$DEST/logo.png" && -f "$DEST/favicon.png" ]] || exit 1
echo "Branding OK"
