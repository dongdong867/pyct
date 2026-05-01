#!/usr/bin/env bash
set -euo pipefail

# Mutation testing baseline runner for src/pyct/engine/.
#
# Reads config from [tool.mutmut] in pyproject.toml. Tees raw output to a
# timestamped log under tools/mutation/results/ and writes a survivor summary
# alongside it.
#
# Usage:
#   tools/mutation/run_baseline.sh                  # full engine run
#   tools/mutation/run_baseline.sh path engine      # only mutate path/engine modules

cd "$(dirname "$0")/../.."

ts=$(date +%Y%m%d_%H%M%S)
out_dir=tools/mutation/results
log="$out_dir/run_${ts}.log"
summary="$out_dir/run_${ts}.summary.txt"

mkdir -p "$out_dir"

echo "Mutation run starting: $ts" | tee "$log"
echo "Config: $(uv run python -c 'import tomllib;print(tomllib.loads(open(\"pyproject.toml\").read())[\"tool\"][\"mutmut\"])')" | tee -a "$log"

# Optional positional args narrow the run to specific module name fragments.
filter_args=()
for arg in "$@"; do
    filter_args+=("src.pyct.engine.${arg}")
done

uv run mutmut run "${filter_args[@]}" 2>&1 | tee -a "$log"

echo "" | tee -a "$summary"
echo "=== Survivor summary ===" | tee -a "$summary"
uv run mutmut results 2>&1 | tee -a "$summary"

echo ""
echo "Log:     $log"
echo "Summary: $summary"
