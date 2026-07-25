#!/usr/bin/env bash
# Install / refresh the exam-simulator systemd unit for the current tree.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/exam-simulator}"
SERVICE_NAME=exam-simulator
UNIT_SRC="${INSTALL_DIR}/deploy/exam-simulator.service"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Missing unit template: $UNIT_SRC" >&2
  exit 1
fi

TMP="$(mktemp)"
sed -e "s|/opt/exam-simulator|${INSTALL_DIR}|g" "$UNIT_SRC" > "$TMP"
cp "$TMP" "$UNIT_DST"
rm -f "$TMP"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager status "$SERVICE_NAME"
