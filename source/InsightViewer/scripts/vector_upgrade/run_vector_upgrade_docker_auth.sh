#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/robert/insightViewer"
RUNNER="$ROOT/source/InsightViewer/scripts/vector_upgrade/run_vector_upgrade.sh"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-neo4j}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install docker or set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD manually."
  exit 2
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$NEO4J_CONTAINER"; then
  echo "Container '$NEO4J_CONTAINER' is not running."
  exit 2
fi

AUTH_LINE=$(docker inspect "$NEO4J_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^NEO4J_AUTH=' || true)
if [[ -z "$AUTH_LINE" ]]; then
  echo "NEO4J_AUTH not found in container '$NEO4J_CONTAINER'."
  exit 2
fi

AUTH_PAIR=${AUTH_LINE#NEO4J_AUTH=}
if [[ "$AUTH_PAIR" != */* ]]; then
  echo "Invalid NEO4J_AUTH format in container '$NEO4J_CONTAINER'."
  exit 2
fi

export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_USER="${AUTH_PAIR%%/*}"
export NEO4J_PASSWORD="${AUTH_PAIR#*/}"

exec "$RUNNER" "$@"
