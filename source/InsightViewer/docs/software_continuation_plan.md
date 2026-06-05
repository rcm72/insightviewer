Software Continuation Plan

Purpose
- Park the next software improvements so work can resume quickly later.

Current status (2026-06-05)
- Vector upgrade workflow is automated and documented.
- One-command validator exists and was verified with OVERALL: PASS.
- Retrieval smoke checks passed (13/13).
- Operations vector/embeddings health endpoint is implemented and verified.

Implemented item
1) Operations health endpoint
- Route: /api/ops/vector-health
- Query param: include_global=1 (optional)
- Protection: JWT auth required
- Response includes:
  - vector/fulltext index state
  - Chunk embedding coverage (project and optional global)
  - provider reachability (Ollama/OpenAI basic probe)
- Verified locally with:
  - GET /api/ops/vector-health?include_global=1

Deferred implementation options
1) OpenAI embedding tests
- Add tests for OpenAI embed success path and failure handling:
  - HTTP non-200
  - malformed JSON response shape
  - missing embedding vector
- Target file under tests: tests for app/ai/providers/openai_provider.py.

2) JWT helper for smoke runs
- Add a helper script to acquire/generate a fresh JWT for local smoke checks.
- Goal: remove manual token copy-paste from validation flow.

3) Retrieval resilience review
- Add targeted tests for edge cases:
  - provider timeout
  - empty retrieval result
  - project normalization behavior
  - fulltext/index unavailable handling

Recommended order when resuming
1. OpenAI embedding tests
2. JWT helper for smoke
3. Retrieval resilience tests

Definition of done for each item
- Endpoint/script/tests added
- Local run instructions documented
- Smoke/tests pass
- Commit + push with a scoped message

Resume command checklist
- Open this file.
- Pick one item.
- Implement in a small scoped commit.
