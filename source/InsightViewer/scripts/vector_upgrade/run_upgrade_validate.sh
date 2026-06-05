#!/usr/bin/env bash
set -uo pipefail

ROOT="/home/robert/insightViewer/source/InsightViewer"
UPGRADE_SCRIPT="$ROOT/scripts/vector_upgrade/run_vector_upgrade_docker_auth.sh"
SMOKE_SCRIPT="$ROOT/scripts/smoke_retrieval_and_quiz.sh"

BASE_URL="http://localhost:5001"
JWT="${ACCESS_TOKEN:-}"
SKIP_SMOKE=0
FORWARD_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  run_upgrade_validate.sh [options] [-- <upgrade_args>]

Options:
  --jwt <token>        JWT token for smoke checks (or set ACCESS_TOKEN env)
  --base-url <url>     App base URL for smoke checks (default: http://localhost:5001)
  --skip-smoke         Skip smoke checks (DB validation only)
  -h, --help           Show this help

Examples:
  run_upgrade_validate.sh --jwt <token>
  run_upgrade_validate.sh --jwt <token> -- --provider ollama --model mxbai-embed-large:latest --batch-size 100
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jwt)
      JWT="${2:-}"
      shift 2
      ;;
    --base-url)
      BASE_URL="${2:-}"
      shift 2
      ;;
    --skip-smoke)
      SKIP_SMOKE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        FORWARD_ARGS+=("$1")
        shift
      done
      ;;
    *)
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

PASS=1

echo "[STEP 1/3] Upgrade (indexes + backfill)"
UPGRADE_OUT="$($UPGRADE_SCRIPT "${FORWARD_ARGS[@]}" 2>&1)"
UPGRADE_RC=$?
echo "$UPGRADE_OUT"
if [[ $UPGRADE_RC -ne 0 ]]; then
  echo "RESULT upgrade=FAIL"
  PASS=0
fi

echo "[STEP 2/3] Coverage (Chunk embedding)"
AUTH_LINE=$(docker inspect neo4j --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^NEO4J_AUTH=' || true)
if [[ -z "$AUTH_LINE" ]]; then
  echo "Could not read NEO4J_AUTH from container neo4j"
  echo "RESULT coverage=FAIL"
  PASS=0
else
  AUTH_PAIR=${AUTH_LINE#NEO4J_AUTH=}
  NEO4J_USER=${AUTH_PAIR%%/*}
  NEO4J_PASSWORD=${AUTH_PAIR#*/}
  COVERAGE_OUT="$(docker exec -i neo4j cypher-shell -a bolt://localhost:7687 -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "MATCH (c:Chunk) RETURN count(c) AS total, count(c.embedding) AS withEmbedding, count(c)-count(c.embedding) AS missing;" 2>&1)"
  COVERAGE_RC=$?
  echo "$COVERAGE_OUT"
  if [[ $COVERAGE_RC -ne 0 ]]; then
    echo "RESULT coverage=FAIL"
    PASS=0
  else
    MISSING=$(echo "$COVERAGE_OUT" | tail -n 1 | awk -F',' '{gsub(/ /, "", $3); print $3}')
    if [[ -z "$MISSING" ]]; then
      echo "RESULT coverage=UNKNOWN"
      PASS=0
    elif [[ "$MISSING" != "0" ]]; then
      echo "RESULT coverage=FAIL missing=$MISSING"
      PASS=0
    else
      echo "RESULT coverage=PASS missing=0"
    fi
  fi
fi

if [[ $SKIP_SMOKE -eq 1 ]]; then
  echo "[STEP 3/3] Smoke skipped"
else
  echo "[STEP 3/3] Smoke (app endpoints)"
  if [[ -z "$JWT" ]]; then
    echo "Missing JWT. Provide --jwt <token> or ACCESS_TOKEN env (or use --skip-smoke)."
    echo "RESULT smoke=FAIL"
    PASS=0
  else
    SMOKE_OUT="$($SMOKE_SCRIPT "$BASE_URL" "$JWT" 2>&1)"
    SMOKE_RC=$?
    echo "$SMOKE_OUT"
    if [[ $SMOKE_RC -ne 0 ]]; then
      echo "RESULT smoke=FAIL"
      PASS=0
    elif echo "$SMOKE_OUT" | grep -q 'Summary: pass=' && echo "$SMOKE_OUT" | grep -q 'fail=0'; then
      echo "RESULT smoke=PASS"
    else
      echo "RESULT smoke=FAIL"
      PASS=0
    fi
  fi
fi

if [[ $PASS -eq 1 ]]; then
  echo "OVERALL: PASS"
  exit 0
fi

echo "OVERALL: FAIL"
exit 1
