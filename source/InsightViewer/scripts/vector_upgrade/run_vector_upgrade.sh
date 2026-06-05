#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/robert/insightViewer"
VENV_PY="$ROOT/.venv/bin/python"
CYPHER_FILE="$ROOT/source/InsightViewer/scripts/vector_upgrade/01_create_vector_indexes.cypher"
BACKFILL_PY="$ROOT/source/InsightViewer/scripts/vector_upgrade/02_backfill_chunk_embeddings.py"

if [[ -z "${NEO4J_URI:-}" || -z "${NEO4J_USER:-}" || -z "${NEO4J_PASSWORD:-}" ]]; then
  echo "Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD first."
  exit 2
fi

echo "[1/2] Creating constraints/indexes..."
if command -v cypher-shell >/dev/null 2>&1; then
  cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$CYPHER_FILE"
elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -qx 'neo4j'; then
  # Fallback for hosts without cypher-shell: run cypher-shell inside Neo4j container.
  docker exec -i neo4j cypher-shell -a "bolt://localhost:7687" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" < "$CYPHER_FILE"
else
  echo "cypher-shell not found and no running 'neo4j' container detected."
  echo "Install Neo4j shell tools or run $CYPHER_FILE manually in Neo4j Browser."
  exit 2
fi

echo "[2/2] Backfilling embeddings..."
"$VENV_PY" "$BACKFILL_PY" "$@"

echo "Vector upgrade complete."
