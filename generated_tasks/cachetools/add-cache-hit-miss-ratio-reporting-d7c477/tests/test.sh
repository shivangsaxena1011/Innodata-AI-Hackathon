#!/bin/bash
# CodeForge verifier. Hidden tests live only here; the agent never sees them.
set -uo pipefail
mkdir -p /logs/verifier
echo '{"reward": 0.0}' > /logs/verifier/reward.json
cd /app || { echo "missing /app"; exit 0; }

# Remove agent-created pytest/interpreter hooks that could fake results.
KEEP=()
while IFS= read -r f; do
  keep=0; for k in "${KEEP[@]:-}"; do [ "$f" = "$k" ] && keep=1; done
  [ "$keep" = 0 ] && echo "removing unexpected $f" && rm -f "$f"
done < <(find . -name conftest.py -not -path './.git/*' 2>/dev/null)
find . \( -name sitecustomize.py -o -name usercustomize.py \) -delete 2>/dev/null || true

# Restore pristine original tests and test configuration, then add the hidden tests.
cp -r /tests/regression/. /app/
cp -r /tests/feature/. /app/

timeout 900 bash -c 'python -m pytest -p no:cacheprovider -q -o addopts='"'"''"'"' --continue-on-collection-errors --junitxml=/logs/verifier/feature.xml tests/test_codeforge_add_cache_hit_miss_ratio_reporting_d7c477.py' > /logs/verifier/feature.log 2>&1
timeout 1800 bash -c 'python -m pytest -p no:cacheprovider -q -o addopts='"'"''"'"' --continue-on-collection-errors --junitxml=/logs/verifier/regression.xml tests' > /logs/verifier/regression.log 2>&1

python3 /tests/grade.py /tests/expected.json /logs/verifier/feature.xml \
  /logs/verifier/regression.xml /logs/verifier/reward.json || true
exit 0
