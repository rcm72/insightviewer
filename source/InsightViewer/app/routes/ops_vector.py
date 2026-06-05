import os
from typing import Any

import requests
from flask import Blueprint, jsonify, request

from ai.registry import ProviderRegistry
from routes.retrieval import validate_jwt

ops_vector_bp = Blueprint("ops_vector", __name__, url_prefix="/api/ops")

driver = None


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
        if include_global:
            result["coverage"]["global"] = _query_embedding_coverage(session, None)

        try:
            result["indexes"] = _query_index_status(session)
        except Exception as e:
            result["indexes_error"] = str(e)

    registry = ProviderRegistry()
    result["providers"] = {
        "ollama": _probe_ollama(registry),
        "openai": _probe_openai(registry),
    }

    return jsonify(result), 200
