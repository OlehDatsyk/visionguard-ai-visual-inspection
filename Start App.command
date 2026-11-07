#!/bin/bash
# macOS launcher. If it will not open, run this once in Terminal: chmod +x "Start App.command"
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo
  echo "[VisionGuard] Python was not found."
  echo "Install Python 3.12 from https://www.python.org/downloads/ and try again."
  echo
  read -r -p "Press Return to close." _
  exit 1
fi

"$PY" scripts/start.py "$@"
CODE=$?
if [ "$CODE" -ne 0 ] && [ "$1" != "--check" ]; then
  echo
  echo "[VisionGuard] Stopped with an error. See INSTRUCTION.md, section Troubleshooting."
  read -r -p "Press Return to close." _
fi
exit "$CODE"
