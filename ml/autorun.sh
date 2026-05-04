#!/bin/bash
# AXIOM ML — daily automation script.
# Captures today's prices + prints backtest health report.
# Designed to run from the valuation_app/ directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

LOG="$SCRIPT_DIR/monitor_autorun.log"
PYTHON="$(which python3)"

echo "" >> "$LOG"
echo "=== AXIOM Monitor $(date) ===" | tee -a "$LOG"

# 1. Capture today's prices + current regime
$PYTHON -m ml.monitor --snapshot 2>&1 | tee -a "$LOG"

# 2. Show backtest quality on historical data (instant — uses saved walk-forward results)
$PYTHON -m ml.monitor --backtest-report 2>&1 | tee -a "$LOG"

# 3. Score any predictions that are now 90/180/365 days old
$PYTHON -m ml.monitor --evaluate 2>&1 | tee -a "$LOG"

echo "Done. Log: $LOG"
