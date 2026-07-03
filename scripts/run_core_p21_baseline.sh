#!/usr/bin/env bash
# Empirical CORE / Pinnacle 21 baseline driver for the Track B archetype benchmark.
#
#   1. build clean + 20 injected CORE-readable corpora      (project venv)
#   2. run real CORE v0.15 on each corpus                    (vendor/core/.venv)
#   3. compare injected-vs-clean per archetype -> 0/20       (project venv)
#
# CORE (cdisc-rules-engine) lives in its own venv because its deps (dask, etc.)
# conflict with the project. Pinnacle 21 Community uses this same CORE engine as
# its backend, so the result is Pinnacle 21's detection ceiling.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
COREPY="vendor/core/.venv/Scripts/python.exe"
[ -f "$COREPY" ] || COREPY="vendor/core/.venv/bin/python"
REPORTS="$ROOT/eval/core_benchmark"
mkdir -p "$REPORTS"

echo "== [0/3] ensure xport (V5 XPORT writer; wheel, no build) is available =="
# xport's sdist build is broken (pkg_resources); the wheel installs cleanly with --no-deps.
uv pip install --no-deps xport >/dev/null 2>&1 || true
# CORE reads XPORT via pandas.read_sas, so the engine venv needs it too.
( cd "$ROOT/vendor/core" && .venv/Scripts/python.exe -m pip install --no-deps xport >/dev/null 2>&1 ) || true

echo "== [1/3] build corpora =="
PYTHONIOENCODING=ascii:replace uv run python -m scripts.run_core_p21_baseline build

run_core () {  # $1 = corpus dir name, $2 = report stem
  echo "   CORE validate: $1"
  # CORE resolves its rules cache relative to vendor/core, so run from there.
  ( cd "$ROOT/vendor/core" && .venv/Scripts/python.exe core.py validate \
      -s sdtmig -v 3-4 -d "$ROOT/bench/core_lean/$1" -ft xpt \
      -of JSON -rr -l critical -o "$REPORTS/$2" >/dev/null 2>&1 ) \
    || echo "     (CORE returned non-zero for $1)"
}

echo "== [2/3] run CORE on clean + 20 injected =="
run_core clean lean_clean
for aid in A01 A02 A03 A04 A05 A06 A07 A08 A09 A10 A11 A12 A13 A14 A15 A16 A17 A18 A19 A20; do
  run_core "$aid" "lean_$aid"
done

echo "== [3/3] compare =="
PYTHONIOENCODING=ascii:replace uv run python -m scripts.run_core_p21_baseline compare
