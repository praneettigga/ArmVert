#!/usr/bin/env bash
# Rebuild everything from scratch: data -> train -> export -> parity vectors -> tests.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-../.venv/bin/python}
$PY data/generate_synthetic.py --out data/synthetic.csv --per-template 40
$PY data/download_public.py
$PY train.py --epochs 6
$PY export_executorch.py
$PY tests/make_vectors.py
$PY -m unittest discover -s tests
echo "Done. Classifier copied to android/app/src/main/assets/scam_classifier.pte"
