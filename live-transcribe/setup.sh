#!/usr/bin/env bash
# One-time: build the venv. Run this once, then activate + start yourself.
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt

echo
echo "done. now:"
echo "  source .venv/bin/activate"
echo "  python -m uvicorn server:app --host 0.0.0.0 --port 8000"
