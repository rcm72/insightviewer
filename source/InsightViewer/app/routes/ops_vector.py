import os
import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from flask import Blueprint, jsonify, request

from ai.registry import ProviderRegistry
from ai.vector_config import VECTOR_DIMENSIONS
from routes.retrieval import validate_jwt
from services.vector_embeddings import inspect_vector_index, run_embedding_backfill

ops_vector_bp = Blueprint("ops_vector", __name__, url_prefix="/api/ops")

driver = None
_job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vector-backfill")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_INDEX_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,128}$")


def init_driver(d):
    global driver
    driver = d


def _ensure_driver():
    if driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver(driver) on startup.")


def _normalize_project(project_value: str | None) -> str | None:
    project = str(project_value or "").strip()
    if not project or project.upper() == "ALL":
        return None
    return project


def _query_embedding_coverage(session, project: str | None) -> dict[str, int]:
    cypher = """
    MATCH (c:Chunk)
    WHERE $project IS NULL OR c.projectName = $project
    RETURN
      count(c) AS total,
      count(c.embedding) AS withEmbedding,
      count(c) - count(c.embedding) AS missing
    """
    row = session.run(cypher, project=project).single()
    if not row:
        return {"total": 0, "withEmbedding": 0, "missing": 0}
    return {
        "total": int(row.get("total") or 0),
        "withEmbedding": int(row.get("withEmbedding") or 0),
        "missing": int(row.get("missing") or 0),
    }


def _query_index_status(session) -> list[dict[str, str]]:
    expected = [
        "chunk_embedding",
        "chunk_embedding_index",
        "chunk_text_fts",
    ]
    cypher = """
    SHOW INDEXES YIELD name, type, state
    WHERE name IN $expected
    RETURN name, type, state
    ORDER BY name
    """
    rows = session.run(cypher, expected=expected).data()
    return [
        {
            "name": str(r.get("name") or ""),
            "type": str(r.get("type") or ""),
            "state": str(r.get("state") or ""),
        }
        for r in rows
    ]


def _probe_ollama(registry: ProviderRegistry) -> dict[str, Any]:
    try:
        provider = registry.get_provider("ollama")
    except Exception as e:
        return {"configured": False, "reachable": False, "error": str(e)}

    base_url = getattr(provider, "_base_url", "")
    if not base_url:
        return {"configured": False, "reachable": False, "error": "OLLAMA base URL missing"}

    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        r = requests.get(url, timeout=6)
        return {
            "configured": True,
            "reachable": bool(r.ok),
            "http_status": int(r.status_code),
            "base_url": base_url,
        }
    except requests.RequestException as e:
        return {
            "configured": True,
            "reachable": False,
            "base_url": base_url,
            "error": str(e),
        }


def _probe_openai(registry: ProviderRegistry) -> dict[str, Any]:
    # Keep this lightweight and safe: verify config and key presence.
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"configured": False, "reachable": False, "error": "OPENAI_API_KEY missing"}

    try:
        provider = registry.get_provider("openai")
    except Exception as e:
        return {"configured": False, "reachable": False, "error": str(e)}

    base_url = getattr(provider, "_base_url", "https://api.openai.com")
    return {
        "configured": True,
        "reachable": True,
        "base_url": base_url,
        "note": "Key present; provider initialized",
    }


def _update_embedding_job(job_id: str, **updates: Any) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(updates)


def _run_embedding_job(job_id: str, project: str, provider: str, model: str, index_name: str) -> None:
    _update_embedding_job(job_id, status="starting")
    try:
        run_embedding_backfill(
            driver=driver,
            project=project,
            provider_id=provider,
            model=model,
            index_name=index_name,
            update_job=lambda **updates: _update_embedding_job(job_id, **updates),
        )
    except Exception as exc:
        logging.getLogger(__name__).exception("Vector embedding job %s failed", job_id)
        _update_embedding_job(
            job_id,
            status="failed",
            error=f"{type(exc).__name__}: {str(exc)[:500]}",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )


def _prune_embedding_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    with _jobs_lock:
        expired = [
            job_id
            for job_id, job in _jobs.items()
            if job.get("completed_at")
            and datetime.fromisoformat(job["completed_at"]) < cutoff
        ]
        for job_id in expired:
            _jobs.pop(job_id, None)


def _read_vector_index(session, index_name: str) -> dict[str, Any]:
    state, dimensions, labels, properties = inspect_vector_index(session, index_name)
    exists = state is not None
    compatible = (
        exists
        and dimensions == VECTOR_DIMENSIONS
        and "Chunk" in labels
        and "embedding" in properties
    )
    return {
        "index_name": index_name,
        "exists": exists,
        "state": state,
        "dimensions": dimensions,
        "expected_dimensions": VECTOR_DIMENSIONS,
        "labels": labels,
        "properties": properties,
        "compatible": compatible,
        "ready": bool(compatible and state == "ONLINE"),
    }


@ops_vector_bp.route("/vector-index-status", methods=["GET"])
def vector_index_status():
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    _ensure_driver()
    index_name = str(request.args.get("index_name") or "chunk_embedding_index").strip()
    if not _INDEX_NAME_PATTERN.fullmatch(index_name):
        return jsonify({"success": False, "error": "Invalid vector index name."}), 400

    try:
        with driver.session() as session:
            details = _read_vector_index(session, index_name)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Failed to inspect vector index: {str(exc)[:500]}"}), 400
    return jsonify({"success": True, **details}), 200


@ops_vector_bp.route("/vector-index-ensure", methods=["POST"])
def ensure_vector_index():
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    _ensure_driver()
    payload = request.get_json(silent=True) or {}
    index_name = str(payload.get("index_name") or "chunk_embedding_index").strip()
    if not _INDEX_NAME_PATTERN.fullmatch(index_name):
        return jsonify({"success": False, "error": "Invalid vector index name."}), 400

    try:
        with driver.session() as session:
            before = _read_vector_index(session, index_name)
            if before["exists"]:
                if not before["compatible"]:
                    return jsonify({
                        "success": False,
                        **before,
                        "error": (
                            f"Index '{index_name}' already exists but does not match Chunk.embedding "
                            f"with {VECTOR_DIMENSIONS} dimensions. It was not changed."
                        ),
                    }), 409
            else:
                create_cypher = f"""
                CREATE VECTOR INDEX {index_name} IF NOT EXISTS
                FOR (c:Chunk)
                ON (c.embedding)
                OPTIONS {{
                  indexConfig: {{
                    `vector.dimensions`: {VECTOR_DIMENSIONS},
                    `vector.similarity_function`: 'cosine'
                  }}
                }}
                """
                session.run(create_cypher).consume()
            after = _read_vector_index(session, index_name)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Failed to create/verify vector index: {str(exc)[:500]}"}), 400

    return jsonify({
        "success": True,
        "created": not before["exists"] and after["exists"],
        **after,
    }), 200


@ops_vector_bp.route("/vector-health", methods=["GET"])
def vector_health():
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    _ensure_driver()

    project = _normalize_project(user_info.get("project"))
    include_global = str(request.args.get("include_global") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    coverage_only = str(request.args.get("coverage_only") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    result: dict[str, Any] = {
        "success": True,
        "project": project,
        "coverage": {},
        "indexes": [],
        "providers": {},
    }

    with driver.session() as session:
        result["coverage"] = {
            "project": _query_embedding_coverage(session, project),
        }
        if include_global and not coverage_only:
            result["coverage"]["global"] = _query_embedding_coverage(session, None)

        if not coverage_only:
            try:
                result["indexes"] = _query_index_status(session)
            except Exception as e:
                result["indexes_error"] = str(e)

    if not coverage_only:
        registry = ProviderRegistry()
        result["providers"] = {
            "ollama": _probe_ollama(registry),
            "openai": _probe_openai(registry),
        }

    return jsonify(result), 200


@ops_vector_bp.route("/vector-embeddings", methods=["POST"])
def start_vector_embeddings():
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    _ensure_driver()
    project = str(user_info.get("project") or "").strip()
    if not project or project.upper() == "ALL":
        return jsonify({"success": False, "error": "A specific project is required."}), 400

    payload = request.get_json(silent=True) or {}
    provider = str(payload.get("provider") or "ollama").strip().lower()
    model = str(payload.get("model") or "mxbai-embed-large:latest").strip()
    index_name = str(payload.get("vector_index_name") or "chunk_embedding_index").strip()
    if provider not in {"ollama", "openai"}:
        return jsonify({"success": False, "error": "Unsupported embedding provider."}), 400
    if not model or len(model) > 200:
        return jsonify({"success": False, "error": "A valid embedding model is required."}), 400
    if provider == "openai" and not model.startswith("text-embedding-3"):
        return jsonify({
            "success": False,
            "error": "The selected OpenAI model must support configurable dimensions (text-embedding-3 models).",
        }), 400
    if not _INDEX_NAME_PATTERN.fullmatch(index_name):
        return jsonify({"success": False, "error": "Invalid vector index name."}), 400

    _prune_embedding_jobs()
    user_id = str(user_info.get("uid") or "")
    with _jobs_lock:
        active = next(
            (
                job
                for job in _jobs.values()
                if job.get("status") in {"queued", "starting", "running"}
            ),
            None,
        )
        if active:
            if active.get("project") != project or active.get("owner") != user_id:
                return jsonify({
                    "success": False,
                    "error": "Another embedding job is already running.",
                }), 409
            return jsonify({
                "success": True,
                "job": {k: v for k, v in active.items() if k != "owner"},
                "already_running": True,
            }), 202

        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "queued",
            "project": project,
            "provider": provider,
            "model": model,
            "vector_index_name": index_name,
            "dimensions": VECTOR_DIMENSIONS,
            "total": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "error_samples": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "owner": user_id,
        }
        _jobs[job_id] = job

    try:
        _job_executor.submit(_run_embedding_job, job_id, project, provider, model, index_name)
    except Exception as exc:
        _update_embedding_job(
            job_id,
            status="failed",
            error=f"Could not start job: {str(exc)[:300]}",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        return jsonify({"success": False, "error": "Could not start the embedding job."}), 503

    with _jobs_lock:
        snapshot = {k: v for k, v in _jobs[job_id].items() if k != "owner"}
    return jsonify({"success": True, "job": snapshot}), 202


@ops_vector_bp.route("/vector-embeddings", methods=["GET"])
def get_active_vector_embeddings():
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    project = str(user_info.get("project") or "").strip()
    user_id = str(user_info.get("uid") or "")
    with _jobs_lock:
        job = next(
            (
                candidate
                for candidate in reversed(list(_jobs.values()))
                if candidate.get("owner") == user_id
                and candidate.get("project") == project
                and candidate.get("status") in {"queued", "starting", "running"}
            ),
            None,
        )
        snapshot = {k: v for k, v in job.items() if k != "owner"} if job else None
    return jsonify({"success": True, "job": snapshot}), 200


@ops_vector_bp.route("/vector-embeddings/<job_id>", methods=["GET"])
def get_vector_embeddings_job(job_id: str):
    user_info, err_resp, status = validate_jwt()
    if err_resp:
        return err_resp, status

    with _jobs_lock:
        job = _jobs.get(job_id)
        if (
            not job
            or job.get("owner") != str(user_info.get("uid") or "")
            or job.get("project") != str(user_info.get("project") or "").strip()
        ):
            return jsonify({"success": False, "error": "Embedding job not found."}), 404
        snapshot = {k: v for k, v in job.items() if k != "owner"}
    return jsonify({"success": True, "job": snapshot}), 200
