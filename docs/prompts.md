# Prompts

## 1. Understand my stack
You are my local assistant for a Dockerized Flask + Neo4j project. Read the open files and infer the architecture: entrypoints, container topology, how Flask connects to Neo4j, and where config is loaded.

**Output:**
- (1) High-level diagram in text.
- (2) List of key files.
- (3) Top 5 risks/bugs you see.
- (4) Quick wins.

---

## 2. Docker-compose sanity + improvements (safe mode)
Review my `docker-compose.yml` (and any `.env` references). Goals: reproducible dev setup, explicit ports, stable networking, and secure defaults.

**Output:**
- A prioritized list of improvements with exact diffs.
- Explain any breaking changes.
- Constraints:
  - Don’t add new services unless necessary.
  - Keep Neo4j data persistent.
  - Keep local dev simple.

---

## 3. Flask config hardening (12-factor + containers)
Refactor Flask configuration to be 12-factor friendly. Requirements: read from environment variables, support `.env` locally, no secrets in git, clear defaults for dev, strict validation for prod.

**Output:**
- Code changes (exact snippets).
- A sample `.env.example`.

---

## 4. Neo4j connection best practices (driver + sessions)
Audit my Neo4j access layer. Requirements: use the official Neo4j Python driver correctly (driver singleton, sessions per request/unit-of-work, transactions), clean shutdown, and good error handling.

**Output:**
- A recommended module layout.
- Code patches.
- Pitfalls to avoid in Flask (threading / gunicorn).

---

## 5. Make queries safe
Review the code building Cypher queries. Find any string concatenation or unsafe patterns and rewrite them to use parameters.

**Output:**
- Exact code edits.
- A short explanation of what was dangerous.

---

## 6. Add a robust healthcheck (Flask + Neo4j + Docker)
Add a `/health` endpoint that checks:
- Flask is alive.
- Neo4j connectivity is OK (simple `RETURN 1`).
- Returns a JSON payload with status + latency.
- Add Docker healthchecks for the Flask service and Neo4j service.

**Output:**
- Exact code changes.
- `docker-compose.yml` changes.

---

## 7. Neo4j indexes/constraints recommendation
Based on the node labels + relationship types used in this repo, recommend Neo4j constraints and indexes.

**Output:**
- Cypher statements to apply + justification.
- Constraints:
  - Avoid over-indexing.
  - Focus on properties used in `MATCH/WHERE` and unique IDs.

---

## 8. Add structured logging across containers
Implement structured logging (JSON logs) in Flask and ensure logs are container-friendly (stdout/stderr). Include request-id correlation (generate if missing), log Neo4j query timings, and avoid logging secrets.

**Output:**
- Code changes.
- Recommended Docker settings.

---

## 9. Performance pass (Neo4j query tuning)
Identify the top slow-query risks in this codebase. For each query:
- Explain what might be expensive.
- Recommend indexes/constraints.
- Rewrite the Cypher to be more efficient where possible.

**Output:**
- Before/after query and reasoning.
- Constraints: don’t change behavior.

---

## 10. Add tests with containers (pytest + testcontainers OR docker-compose)
Pick one depending on your preference:
A) Docker-compose based integration tests (simple)
Create integration tests for Flask endpoints that require Neo4j, using `docker-compose` as the test dependency.
- Provide: pytest setup, fixtures, and one example test that inserts test data and asserts a response.
- Constraints: Tests must be repeatable and clean up after themselves.

B) Testcontainers (more isolated)
Create integration tests using Testcontainers for Neo4j (Python).
- Provide fixtures that start Neo4j, run migrations/constraints, and tear down cleanly.
- Add one example endpoint test.
