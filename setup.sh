#!/usr/bin/env bash
# One-shot setup + launch for GitPulse on Linux/macOS.
# Usage: ./setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  echo "Error: no python3 or python interpreter found on PATH." >&2
  echo "Install Python 3.10+ first (e.g. 'sudo apt install python3 python3-venv')." >&2
  exit 1
fi

echo "Using interpreter: $($PYTHON_BIN --version)"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Launching GitPulse..."
exec python start.py
