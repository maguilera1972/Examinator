#!/usr/bin/env bash
set -euo pipefail
SERVICE_NAME=exam-simulator
UNIT_SRC=/opt/exam-simulator/deploy/exam-simulator.service
UNIT_DST=/etc/systemd/system/${SERVICE_NAME}.service
cp "$UNIT_SRC" "$UNIT_DST"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager status "$SERVICE_NAME"
