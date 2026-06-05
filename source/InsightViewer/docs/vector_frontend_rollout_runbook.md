Vector Search Rollout Runbook

Purpose
- Follow a clear 3-phase path:
  1) finish development Neo4j,
  2) bring vector search to frontend,
  3) finalize upgrade script for other databases.

Scope
- This runbook is execution-oriented: what to run, what to verify, and when a phase is done.

Current rollout status (2026-06-05)
- Phase 1: COMPLETED
- Phase 2: COMPLETED
- Phase 3: NOT STARTED

--------------------------------------------------------------------------------
Phase 1: Finish Development Neo4j
--------------------------------------------------------------------------------

Goal
- Make current development Neo4j fully vector-ready and stable.

Step 1. Run upgrade + validation
- Command:
  /home/robert/insightViewer/source/InsightViewer/scripts/vector_upgrade/run_upgrade_validate.sh \
    --jwt <jwt_token> \
    -- --provider ollama --model mxbai-embed-large:latest --batch-size 100

Expected
- OVERALL: PASS

Step 2. Check vector health endpoint
- Command:
  curl -sS -X GET "http://localhost:5001/api/ops/vector-health?include_global=1" \
    -H "Cookie: access_token=<jwt_token>"

Expected
- success=true
- indexes include chunk_embedding_index and chunk_text_fts in ONLINE state
- coverage.project.missing=0
- providers.ollama.reachable=true

Step 3. Keep baseline evidence
- Save output of:
  - run_upgrade_validate.sh
  - /api/ops/vector-health
- Keep at least one successful snapshot for comparison later.

Phase 1 exit criteria
- OVERALL: PASS
- Retrieval smoke summary: pass=13 fail=0
- coverage missing=0 for project
- required indexes ONLINE

--------------------------------------------------------------------------------
Phase 2: Bring Vector Search To Frontend
--------------------------------------------------------------------------------

Goal
- Expose vector/hybrid retrieval in product flow and keep existing behavior stable.

Backend tasks
1) Finalize retrieval strategy in API
- Preferred: vector-first with explicit fallback to fulltext when needed.
- Keep compatibility for existing entry points.

2) Add/extend tests
- Provider tests (OpenAI/Ollama embedding behavior and error paths)
- Retrieval contract/edge-case tests:
  - empty retrieval
  - provider timeout
  - index unavailable fallback
  - project normalization

3) Add telemetry for decision visibility
- Track whether response used:
  - vector primary
  - fulltext fallback
  - no retrieval

Frontend tasks
1) Wire UI mode toggle/selection
- Add/confirm vector search mode in frontend controls.

2) Display retrieval strategy feedback
- Surface metadata indicating vector/fallback path (for debugging and trust).

3) Preserve current UX paths
- Guided/global flows should still function if vector path is unavailable.

Validation commands
- Existing smoke:
  cd /home/robert/insightViewer/source/InsightViewer
  ./scripts/smoke_retrieval_and_quiz.sh http://localhost:5001 <jwt_token>

- Optional combined validator:
  ./scripts/vector_upgrade/run_upgrade_validate.sh --jwt <jwt_token> -- --provider ollama --model mxbai-embed-large:latest --batch-size 100

Phase 2 exit criteria
- Frontend can run vector search successfully
- Existing search flows remain green
- Smoke: pass=13 fail=0
- No blocking regressions in retrieval endpoints

Phase 2 completion evidence (2026-06-05)
- Backend retrieval strategy implemented: vector-first with explicit fallback to fulltext.
- Frontend controls added for retrieval mode and embedding/vector options.
- Frontend strategy feedback added (including fallback reason when used).
- Retrieval tests expanded for:
  - vector fallback behavior
  - vector-only error behavior
  - provider timeout fallback
  - fulltext index-missing error mapping
- Validation results:
  - unittest retrieval contracts: 7 tests, OK
  - smoke: pass=13 fail=0

Phase 2 completion commits
- eec755b - Implement vector-first retrieval with fulltext fallback
- 21e8e52 - Add frontend controls for vector retrieval strategy
- 9b52892 - Add retrieval tests for vector fallback and errors
- 24371fa - Add explicit fallback telemetry for vector retrieval
- efffdbc - Expand retrieval tests for timeout and index errors

Important
- Phase 3 is intentionally not started yet.

--------------------------------------------------------------------------------
Phase 3: Final Upgrade Script For Other Databases
--------------------------------------------------------------------------------

Goal
- Provide one robust migration/validation script for fresh or remote test DBs.

Requirements for final script
1) Prechecks
- DB connectivity/auth
- provider reachability
- required script/tool availability

2) Actions
- create indexes/constraints
- backfill embeddings
- run coverage and smoke validation

3) Output
- clear PASS/FAIL summary
- actionable error messages

4) Portability
- configurable container name and URI
- works with current docker auth path and manual env path

Suggested command pattern
- /home/robert/insightViewer/source/InsightViewer/scripts/vector_upgrade/run_upgrade_validate.sh \
    --jwt <jwt_token> \
    -- --provider ollama --model mxbai-embed-large:latest --batch-size 100

Phase 3 exit criteria
- Script succeeds on a fresh test database
- Endpoint health and smoke checks are green
- Documentation is sufficient for repeat execution without manual debugging

--------------------------------------------------------------------------------
Operational Notes
--------------------------------------------------------------------------------

Security
- Rotate JWT tokens that were shared in chat/logs.

Rollback posture
- Keep vector fallback in retrieval path during rollout so search remains functional.

Reference docs/scripts
- /home/robert/insightViewer/source/InsightViewer/scripts/vector_upgrade/USAGE.txt
- /home/robert/insightViewer/source/InsightViewer/docs/vector_upgrade_checklist.txt
- /home/robert/insightViewer/source/InsightViewer/scripts/vector_upgrade/run_upgrade_validate.sh
- /home/robert/insightViewer/source/InsightViewer/app/routes/ops_vector.py
