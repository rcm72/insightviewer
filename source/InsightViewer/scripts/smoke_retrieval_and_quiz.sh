#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5001}"
TOKEN="${2:-${ACCESS_TOKEN:-}}"
PERF_MODE="${3:-${SMOKE_PERF:-0}}"
PERF_MAX_MS="${PERF_MAX_MS:-12000}"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Error: python3/python not found in PATH"
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 [base_url] <jwt_token>"
  echo "Or set ACCESS_TOKEN in your environment."
  exit 1
fi

if [[ "$PERF_MODE" == "--perf" ]]; then
  PERF_MODE="1"
fi

tmp_json="$(mktemp)"
tmp_txt="$(mktemp)"
trap 'rm -f "$tmp_json" "$tmp_txt"' EXIT

pass_count=0
fail_count=0

report() {
  local ok="$1"
  local name="$2"
  local detail="$3"
  if [[ "$ok" == "1" ]]; then
    pass_count=$((pass_count + 1))
    echo "[PASS] $name - $detail"
  else
    fail_count=$((fail_count + 1))
    echo "[FAIL] $name - $detail"
  fi
}

post_json() {
  local path="$1"
  local payload="$2"
  curl -s -o "$tmp_json" -w "%{http_code}" \
    -H 'Content-Type: application/json' \
    --cookie "access_token=$TOKEN" \
    -X POST "$BASE_URL$path" \
    -d "$payload"
}

post_json_no_cookie() {
  local path="$1"
  local payload="$2"
  curl -s -o "$tmp_json" -w "%{http_code}" \
    -H 'Content-Type: application/json' \
    -X POST "$BASE_URL$path" \
    -d "$payload"
}

post_json_timed() {
  local path="$1"
  local payload="$2"
  local out
  out="$(curl -s -o "$tmp_json" -w "%{http_code} %{time_total}" \
    -H 'Content-Type: application/json' \
    --cookie "access_token=$TOKEN" \
    -X POST "$BASE_URL$path" \
    -d "$payload")"
  echo "$out"
}

json_has_keys() {
  local keys_csv="$1"
  "$PYTHON_BIN" - "$tmp_json" "$keys_csv" <<'PY'
import json
import sys
p = sys.argv[1]
keys = [k for k in sys.argv[2].split(',') if k]
with open(p, 'r', encoding='utf-8') as f:
    data = json.load(f)
ok = all(k in data for k in keys)
print('1' if ok else '0')
PY
}

json_field_eq() {
  local field="$1"
  local expected="$2"
  "$PYTHON_BIN" - "$tmp_json" "$field" "$expected" <<'PY'
import json
import sys
p, field, expected = sys.argv[1], sys.argv[2], sys.argv[3]
with open(p, 'r', encoding='utf-8') as f:
    data = json.load(f)
value = data.get(field)
print('1' if str(value) == expected else '0')
PY
}

json_eval() {
  local expr="$1"
  "$PYTHON_BIN" - "$tmp_json" "$expr" <<'PY'
import json
import sys
p, expr = sys.argv[1], sys.argv[2]
with open(p, 'r', encoding='utf-8') as f:
    data = json.load(f)
print('1' if eval(expr, {'__builtins__': {}}, {'data': data}) else '0')
PY
}

echo "Running smoke tests against $BASE_URL"

# 1) New endpoint happy path
code="$(post_json '/api/retrieval/query-cypher' '{"query":"test","index_name":"iv_global_search_idx"}')"
if [[ "$code" == "200" && "$(json_has_keys 'success,cypher,items,meta')" == "1" ]]; then
  report 1 "retrieval/query-cypher happy path" "HTTP 200 and expected keys"
else
  report 0 "retrieval/query-cypher happy path" "HTTP $code"
fi

# 2) Legacy compatibility endpoint happy path
code="$(post_json '/api/search/neo4j-global-build-cypher' '{"query":"test","index_name":"iv_global_search_idx"}')"
if [[ "$code" == "200" && "$(json_has_keys 'success,cypher,items,meta')" == "1" ]]; then
  report 1 "global-search compatibility happy path" "HTTP 200 and expected keys"
else
  report 0 "global-search compatibility happy path" "HTTP $code"
fi

# 3) Auth check (no cookie)
code="$(post_json_no_cookie '/api/retrieval/query-cypher' '{"query":"test"}')"
if [[ "$code" == "401" ]]; then
  report 1 "auth required" "HTTP 401 without cookie"
else
  report 0 "auth required" "Expected 401, got $code"
fi

# 4) Validation check
code="$(post_json '/api/retrieval/query-cypher' '{"index_name":"iv_global_search_idx"}')"
if [[ "$code" == "400" && "$(json_field_eq 'success' 'False')" == "1" ]]; then
  report 1 "validation for query" "HTTP 400 on missing query"
else
  report 0 "validation for query" "Expected 400, got $code"
fi

# 5) Quiz/UI routes
for path in /index /quiz_ui /quiz; do
  code="$(curl -s -o "$tmp_txt" -w "%{http_code}" --cookie "access_token=$TOKEN" "$BASE_URL$path")"
  if [[ "$code" == "200" ]]; then
    report 1 "page $path" "HTTP 200"
  else
    report 0 "page $path" "Expected 200, got $code"
  fi
done

# 6) Ask-by-depth validation (missing question)
code="$(post_json '/api/ai/graph/ask-by-depth' '{"node_ids":["x"]}')"
if [[ "$code" == "400" ]]; then
  report 1 "ask-by-depth validation" "HTTP 400 on missing question"
else
  report 0 "ask-by-depth validation" "Expected 400, got $code"
fi

# 7) Ask-by-depth happy path using a discovered node id from retrieval
code="$(post_json '/api/retrieval/query-cypher' '{"query":"test","index_name":"iv_global_search_idx"}')"
node_id="$($PYTHON_BIN - "$tmp_json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1], 'r', encoding='utf-8'))
    items = d.get('items') or []
    print((items[0].get('id_rc') if items else '') or '')
except Exception:
    print('')
PY
)"

if [[ -n "$node_id" ]]; then
  payload="{\"question\":\"What is this node?\",\"node_ids\":[\"$node_id\"],\"depth\":1,\"chunk_limit\":20}"
  code="$(post_json '/api/ai/graph/ask-by-depth' "$payload")"
  if [[ "$code" == "200" && "$(json_has_keys 'success,answer,retrieval')" == "1" ]]; then
    report 1 "ask-by-depth happy path" "HTTP 200 with answer and retrieval"
  else
    report 0 "ask-by-depth happy path" "HTTP $code"
  fi
else
  report 0 "ask-by-depth happy path" "No node id discovered from retrieval/query-cypher"
fi

# 8) Direct retrieval endpoint for depth chunks
if [[ -n "$node_id" ]]; then
  chunks_payload="{\"node_ids\":[\"$node_id\"],\"depth\":1,\"chunk_limit\":20}"
  code="$(post_json '/api/retrieval/chunks-by-depth' "$chunks_payload")"
  if [[ "$code" == "200" && "$(json_has_keys 'success,retrieval')" == "1" ]]; then
    report 1 "retrieval chunks-by-depth" "HTTP 200 with retrieval payload"
  else
    report 0 "retrieval chunks-by-depth" "HTTP $code"
  fi
else
  report 0 "retrieval chunks-by-depth" "No node id discovered from retrieval/query-cypher"
fi

# 9) Scoping check: project='ALL' is normalized to null in retrieval metadata
code="$(post_json '/api/retrieval/query' '{"query":"test","index_name":"iv_global_search_idx","project":"ALL"}')"
if [[ "$code" == "200" && "$(json_eval "data.get('meta', {}).get('project') is None")" == "1" ]]; then
  report 1 "project ALL normalization" "meta.project is null"
else
  report 0 "project ALL normalization" "Expected HTTP 200 with meta.project null, got $code"
fi

# 10) Scoping check: generated cypher keeps project filters in query-cypher path
code="$(post_json '/api/retrieval/query-cypher' '{"query":"test","index_name":"iv_global_search_idx"}')"
if [[ "$code" == "200" && "$(json_eval "'projectName' in data.get('cypher', '')")" == "1" ]]; then
  report 1 "cypher project filter" "Generated cypher contains projectName filter"
else
  report 0 "cypher project filter" "Expected HTTP 200 with projectName in cypher, got $code"
fi

# 11) Ask-by-depth no-chunk scenario should return success with guidance
code="$(post_json '/api/ai/graph/ask-by-depth' '{"question":"What can you tell me?","node_ids":["__missing_node__"],"depth":1,"chunk_limit":20}')"
if [[ "$code" == "200" && "$(json_eval "data.get('success') is True and (data.get('retrieval') or {}).get('chunks_count') == 0")" == "1" ]]; then
  report 1 "ask-by-depth no-chunk guidance" "HTTP 200 with chunks_count=0"
else
  report 0 "ask-by-depth no-chunk guidance" "Expected HTTP 200 with chunks_count=0, got $code"
fi

# 12) Optional performance check: retrieval-only depth call
if [[ "$PERF_MODE" == "1" ]]; then
  if [[ -n "$node_id" ]]; then
    perf_payload="{\"node_ids\":[\"$node_id\"],\"depth\":4,\"chunk_limit\":120}"
    perf_out="$(post_json_timed '/api/retrieval/chunks-by-depth' "$perf_payload")"
    perf_code="$(echo "$perf_out" | awk '{print $1}')"
    perf_sec="$(echo "$perf_out" | awk '{print $2}')"
    perf_ms="$(awk -v s="$perf_sec" 'BEGIN { printf "%d", (s * 1000) }')"

    if [[ "$perf_code" == "200" && "$perf_ms" -le "$PERF_MAX_MS" ]]; then
      report 1 "retrieval performance" "HTTP 200 in ${perf_ms}ms (limit ${PERF_MAX_MS}ms)"
    else
      report 0 "retrieval performance" "HTTP $perf_code in ${perf_ms}ms (limit ${PERF_MAX_MS}ms)"
    fi
  else
    report 0 "retrieval performance" "Skipped because no node id was discovered"
  fi
fi

echo
echo "Summary: pass=$pass_count fail=$fail_count"
if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
