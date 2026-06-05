import os
import re
from typing import Any

import jwt
from flask import Blueprint, current_app, jsonify, request
from neo4j.exceptions import ClientError, CypherSyntaxError

from ai.registry import ProviderRegistry
from ai.types import EmbedRequest

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

retrieval_bp = Blueprint("retrieval", __name__, url_prefix="/api/retrieval")

driver = None

READ_ONLY_DISALLOWED = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL|LOAD\s+CSV|USING\s+PERIODIC\s+COMMIT|FOREACH|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT)\b",
    re.IGNORECASE,
)
READ_ONLY_REQUIRED = re.compile(r"\b(MATCH|RETURN|OPTIONAL\s+MATCH|UNWIND|WITH|WHERE)\b", re.IGNORECASE)


def init_driver(d):
    global driver
    driver = d


def _ensure_driver():
    if driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver(driver) on startup.")


def validate_jwt():
    token = request.cookies.get("access_token")
    if not token:
        return None, jsonify({"error": "Unauthorized: No token provided"}), 401

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("sub")
        project = payload.get("project")
        if not uid or not project:
            return None, jsonify({"error": "Unauthorized: Invalid token"}), 401
        return {"uid": uid, "project": project}, None, None
    except jwt.PyJWTError as e:
        print(f"JWT Error: {e}")
        return None, jsonify({"error": "Unauthorized: Invalid token"}), 401


def _normalize_project(project_value, user_project):
    project = str(project_value or user_project or "").strip()
    if not project or project.upper() == "ALL":
        return None
    return project


def _telemetry_payload(*, entry_point: str, strategy_used: str, anchor_node_id: str | None) -> dict[str, Any]:
    return {
        "entry_point": entry_point,
        "strategy_used": strategy_used,
        "anchor_node_id": anchor_node_id or None,
    }


def _log_telemetry(payload: dict[str, Any]) -> None:
    # Best-effort logging for operational visibility; never break request flow.
    try:
        current_app.logger.info("retrieval_telemetry=%s", payload)
    except Exception:
        pass


def normalize_node_ids(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("node_ids")
    if not isinstance(raw, list):
        raise ValueError("node_ids must be a list of id_rc strings")
    out: list[str] = []
    for x in raw:
        s = str(x or "").strip()
        if s:
            out.append(s)
    unique: list[str] = []
    seen: set[str] = set()
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    if not unique:
        raise ValueError("node_ids must not be empty")
    if len(unique) > 50:
        raise ValueError("node_ids supports at most 50 entries")
    return unique


def retrieve_chunks_by_depth(session, payload: dict[str, Any]) -> dict[str, Any]:
    node_ids = normalize_node_ids(payload)
    depth = int(payload.get("depth") or 2)
    depth = max(0, min(depth, 100))
    chunk_limit = int(payload.get("chunk_limit") or 80)
    chunk_limit = max(1, min(chunk_limit, 300))
    project = (str(payload.get("project") or "").strip() or None)

    visited_query = f"""
        UNWIND $node_ids AS nid
        MATCH (s {{id_rc: nid}})
        WHERE $project IS NULL OR s.projectName = $project
        WITH collect(DISTINCT s) AS starts
        UNWIND starts AS s
        MATCH p = (s)-[*0..{depth}]-(v)
        WHERE ALL(n IN nodes(p) WHERE $project IS NULL OR n.projectName = $project OR n:Chunk)
        WITH collect(DISTINCT v) AS all_nodes
        UNWIND all_nodes AS n
        WITH DISTINCT n
        RETURN n.id_rc AS id_rc, labels(n) AS labels, n.name AS name
        LIMIT 2000
    """
    rows = session.run(
        visited_query,
        node_ids=node_ids,
        project=project,
    ).data()

    visited_nodes = [
        {
            "id_rc": r.get("id_rc"),
            "labels": r.get("labels") or [],
            "name": r.get("name"),
        }
        for r in rows
        if r.get("id_rc")
    ]

    chunks_query = f"""
        UNWIND $node_ids AS nid
        MATCH (s  {{id_rc: nid}})
        WHERE $project IS NULL OR s.projectName = $project

        MATCH p = (s)-[*0..{depth}]-(n)
        WHERE ALL(x IN nodes(p) WHERE $project IS NULL OR x.projectName = $project OR x:Chunk)

        WITH n, min(length(p)) AS dist
        WITH DISTINCT n, dist

        OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c:Chunk)
        WHERE c IS NOT NULL

        WITH c, min(dist) AS min_dist
        RETURN
        c.id_rc AS id_rc,
        labels(c) AS labels,
        coalesce(c.text, c.content, c.body, c.chunkText, c.value, '') AS text,
        min_dist
        ORDER BY min_dist ASC, id_rc ASC
        LIMIT $chunk_limit
    """

    chunk_rows = session.run(
        chunks_query,
        node_ids=node_ids,
        project=project,
        chunk_limit=chunk_limit,
    ).data()

    chunks = [
        {
            "id_rc": r.get("id_rc"),
            "labels": r.get("labels") or ["Chunk"],
            "text": str(r.get("text") or "").strip(),
        }
        for r in chunk_rows
        if str(r.get("text") or "").strip()
    ]

    return {
        "project": project,
        "input_node_ids": node_ids,
        "depth": depth,
        "chunk_limit": chunk_limit,
        "visited_nodes": visited_nodes,
        "chunks": chunks,
        "telemetry": _telemetry_payload(
            entry_point=str(payload.get("entry_point") or "unknown"),
            strategy_used="depth_chunks",
            anchor_node_id=(node_ids[0] if node_ids else None),
        ),
    }


def build_chunks_by_depth_response(session, payload: dict[str, Any]) -> dict[str, Any]:
    retrieval = retrieve_chunks_by_depth(session, payload)
    visited_nodes = retrieval["visited_nodes"]
    chunks = retrieval["chunks"]

    return {
        "status_code": 200,
        "body": {
            "success": True,
            "retrieval": {
                "project": retrieval["project"],
                "input_node_ids": retrieval["input_node_ids"],
                "depth": retrieval["depth"],
                "chunk_limit": retrieval["chunk_limit"],
                "visited_nodes_count": len(visited_nodes),
                "chunks_count": len(chunks),
                "visited_nodes": visited_nodes[:200],
                "chunks": chunks,
                "telemetry": retrieval["telemetry"],
            },
        },
    }


def build_fulltext_error_response(payload: dict[str, Any], error: Exception | str) -> tuple[dict[str, Any], int]:
    message = str(error)
    if (
        "db.index.fulltext.queryNodes" in message
        or "Unknown procedure" in message
        or "There is no such fulltext schema index" in message
    ):
        index_name = str(payload.get("index_name") or "iv_global_search_idx").strip()
        return (
            {
                "success": False,
                "error": (
                    f"Neo4j fulltext index '{index_name}' is not available. "
                    "Create it first, for example: "
                    f"CREATE FULLTEXT INDEX {index_name} IF NOT EXISTS FOR (n:YourLabel) ON EACH [n.name, n.id_rc]"
                ),
            },
            400,
        )
    return ({"success": False, "error": f"Neo4j fulltext query failed: {message}"}, 400)


def _normalize_fulltext_request(payload, user_project):
    query_text = str(payload.get("query") or "").strip()
    if not query_text:
        raise ValueError("query is required")

    index_name = str(payload.get("index_name") or "iv_global_search_idx").strip()
    if not index_name:
        raise ValueError("index_name is required")

    node_type = str(payload.get("node_type") or "").strip()
    project = _normalize_project(payload.get("project"), user_project)

    try:
        limit = max(1, min(int(payload.get("limit") or 24), 80))
    except ValueError:
        raise ValueError("limit must be an integer")

    try:
        scope_hops = max(1, min(int(payload.get("scope_hops") or 1), 2))
    except ValueError:
        raise ValueError("scope_hops must be an integer")

    scope_node_id_rc = str(payload.get("scope_node_id_rc") or "").strip()

    return {
        "query": query_text,
        "index_name": index_name,
        "node_type": node_type,
        "project": project,
        "limit": limit,
        "scope_hops": scope_hops,
        "scope_node_id_rc": scope_node_id_rc,
    }


def _normalize_retrieval_mode(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("retrieval_mode") or "auto").strip().lower()
    if mode not in {"auto", "vector", "fulltext"}:
        raise ValueError("retrieval_mode must be one of: auto, vector, fulltext")

    vector_index_name = str(payload.get("vector_index_name") or "chunk_embedding_index").strip()
    if not vector_index_name:
        raise ValueError("vector_index_name is required")

    provider = str(payload.get("provider") or "ollama").strip().lower()
    if provider not in {"ollama", "openai"}:
        raise ValueError("provider must be one of: ollama, openai")

    model_default = "mxbai-embed-large:latest" if provider == "ollama" else "text-embedding-3-large"
    model = str(payload.get("embedding_model") or payload.get("model") or model_default).strip()
    if not model:
        raise ValueError("embedding_model is required")

    try:
        vector_k = max(1, min(int(payload.get("vector_k") or 40), 200))
    except ValueError:
        raise ValueError("vector_k must be an integer")

    return {
        "mode": mode,
        "vector_index_name": vector_index_name,
        "provider": provider,
        "embedding_model": model,
        "vector_k": vector_k,
    }


def _normalize_edge_types(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("edge_types must be a list")

    out = []
    seen = set()
    for item in value:
        edge_type = str(item or "").strip()
        if not edge_type or edge_type in seen:
            continue
        seen.add(edge_type)
        out.append(edge_type)
    return out


def _quote_cypher_string(value):
    escaped = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _cypher_list(values):
    return "[" + ", ".join(_quote_cypher_string(v) for v in values) + "]"


def _project_filter(alias, project):
    if not project:
        return "TRUE"
    quoted = _quote_cypher_string(project)
    return f"({alias}.projectName = {quoted} OR {alias}.projectName IS NULL)"


def _build_fulltext_graph_cypher(hit_ids, project, edge_types):
    if not hit_ids:
        return ""

    edge_filter = "TRUE"
    if edge_types:
        edge_filter = f"(r IS NULL OR type(r) IN {_cypher_list(edge_types)})"

    return f"""
MATCH (h)
WHERE h.id_rc IN {_cypher_list(hit_ids)}
  AND {_project_filter('h', project)}
OPTIONAL MATCH (h)-[r]-(n)
WHERE {_project_filter('n', project)}
  AND {edge_filter}
RETURN DISTINCT h AS s, r, n AS t
""".strip()


def _build_scoped_fulltext_graph_cypher(hit_ids, scope_node_id_rc, scope_hops, project, edge_types):
    if not hit_ids:
        return ""

    edge_filter = "TRUE"
    if edge_types:
        edge_filter = f"(r IS NULL OR type(r) IN {_cypher_list(edge_types)})"

    scope_hops = max(1, min(int(scope_hops or 1), 2))

    return f"""
MATCH (scope {{id_rc: {_quote_cypher_string(scope_node_id_rc)}}})
WHERE {_project_filter('scope', project)}
MATCH p = (scope)-[*..{scope_hops}]-(h)
WHERE h.id_rc IN {_cypher_list(hit_ids)}
  AND ALL(n1 IN nodes(p) WHERE {_project_filter('n1', project)})
WITH DISTINCT h
OPTIONAL MATCH (h)-[r]-(n)
WHERE {_project_filter('n', project)}
  AND {edge_filter}
RETURN DISTINCT h AS s, r, n AS t
""".strip()


def is_safe_read_query(cypher: str) -> bool:
    if not cypher or READ_ONLY_DISALLOWED.search(cypher):
        return False
    return bool(READ_ONLY_REQUIRED.search(cypher))


def _fulltext_hits(session, *, index_name, query_text, node_type, project, limit):
    cypher = """
    CALL db.index.fulltext.queryNodes($index_name, $query_text) YIELD node, score
    WHERE node.id_rc IS NOT NULL
      AND coalesce(node.name, '') <> ''
      AND ($node_type = '' OR $node_type IN labels(node))
      AND ($project IS NULL OR node.projectName = $project OR node.projectName IS NULL)
    RETURN node.id_rc AS id_rc, node.name AS name, labels(node) AS labels, score
    ORDER BY score DESC, node.name
    LIMIT $limit
    """

    rows = session.run(
        cypher,
        index_name=index_name,
        query_text=query_text,
        node_type=node_type,
        project=project,
        limit=limit,
    ).data()

    if not rows and project:
        rows = session.run(
            cypher,
            index_name=index_name,
            query_text=query_text,
            node_type=node_type,
            project=None,
            limit=limit,
        ).data()

    return rows


def _vector_hits(
        session,
        *,
        vector_index_name: str,
        query_text: str,
        provider: str,
        embedding_model: str,
        node_type: str,
        project: str | None,
        vector_k: int,
        limit: int,
):
        registry = ProviderRegistry()
        embed_provider = registry.get_provider(provider)
        qvec = embed_provider.embed(EmbedRequest(text=query_text, model=embedding_model)).embedding

        cypher = """
        CALL db.index.vector.queryNodes($vector_index_name, $vector_k, $qvec) YIELD node, score
        WHERE ($project IS NULL OR node.projectName = $project OR node.projectName IS NULL)
        OPTIONAL MATCH (owner)-[:HAS_CHUNK]->(node)
        WHERE owner.id_rc IS NOT NULL
            AND ($node_type = '' OR $node_type IN labels(owner))
            AND ($project IS NULL OR owner.projectName = $project OR owner.projectName IS NULL)
        WITH coalesce(owner, node) AS hit, max(score) AS score
        WHERE hit.id_rc IS NOT NULL
        RETURN
            hit.id_rc AS id_rc,
            coalesce(
                hit.name,
                hit.title,
                hit.heading,
                hit.number,
                toString(hit.order),
                substring(coalesce(hit.text, hit.content, hit.body, hit.chunkText, hit.value, ''), 0, 120)
            ) AS name,
            labels(hit) AS labels,
            score
        ORDER BY score DESC, name
        LIMIT $limit
        """

        rows = session.run(
                cypher,
                vector_index_name=vector_index_name,
                vector_k=vector_k,
                qvec=qvec,
                node_type=node_type,
                project=project,
                limit=limit,
        ).data()

        if not rows and project:
                rows = session.run(
                        cypher,
                        vector_index_name=vector_index_name,
                        vector_k=vector_k,
                        qvec=qvec,
                        node_type=node_type,
                        project=None,
                        limit=limit,
                ).data()

        return rows


def retrieve_nodes_for_query(session, payload, user_project):
    normalized = _normalize_fulltext_request(payload, user_project)
    retrieval_mode = _normalize_retrieval_mode(payload)

    rows = []
    strategy_used = "fulltext_query"
    vector_error = None

    if retrieval_mode["mode"] in {"auto", "vector"}:
        try:
            rows = _vector_hits(
                session,
                vector_index_name=retrieval_mode["vector_index_name"],
                query_text=normalized["query"],
                provider=retrieval_mode["provider"],
                embedding_model=retrieval_mode["embedding_model"],
                node_type=normalized["node_type"],
                project=normalized["project"],
                vector_k=retrieval_mode["vector_k"],
                limit=normalized["limit"],
            )
            strategy_used = "vector_query"
        except Exception as e:
            vector_error = str(e)
            rows = []

    if not rows and retrieval_mode["mode"] in {"auto", "fulltext"}:
        rows = _fulltext_hits(
            session,
            index_name=normalized["index_name"],
            query_text=normalized["query"],
            node_type=normalized["node_type"],
            project=normalized["project"],
            limit=normalized["limit"],
        )
        strategy_used = "fulltext_query"

    if retrieval_mode["mode"] == "vector" and vector_error and not rows:
        raise ValueError(f"Vector retrieval failed: {vector_error}")

    items = [
        {
            "id_rc": row.get("id_rc"),
            "name": row.get("name"),
            "labels": row.get("labels") or [],
            "score": row.get("score"),
        }
        for row in rows
        if row.get("id_rc") and row.get("name")
    ]

    hit_ids = [str(item["id_rc"]) for item in items]

    return {
        "items": items,
        "hit_ids": hit_ids,
        "meta": {
            "query": normalized["query"],
            "index_name": normalized["index_name"],
            "vector_index_name": retrieval_mode["vector_index_name"],
            "retrieval_mode": retrieval_mode["mode"],
            "node_type": normalized["node_type"],
            "scope_node_id_rc": normalized["scope_node_id_rc"],
            "scope_hops": normalized["scope_hops"],
            "project": normalized["project"],
            "hit_count": len(hit_ids),
            "vector_error": vector_error,
        },
        "telemetry": _telemetry_payload(
            entry_point=str(payload.get("entry_point") or "unknown"),
            strategy_used=strategy_used,
            anchor_node_id=(normalized["scope_node_id_rc"] or None),
        ),
    }


def build_query_cypher_response(session, payload, user_project):
    edge_types = _normalize_edge_types(payload.get("edge_types"))
    retrieval = retrieve_nodes_for_query(session, payload, user_project)

    hits = retrieval["items"]
    hit_ids = retrieval["hit_ids"]
    meta = retrieval["meta"]
    scope_node_id_rc = meta["scope_node_id_rc"]
    scope_hops = meta["scope_hops"]
    project = meta["project"]

    if not hit_ids:
        return {
            "status_code": 404,
            "body": {
                "success": False,
                "error": "No matching nodes found for the requested query.",
                "items": [],
            },
        }

    if scope_node_id_rc:
        cypher = _build_scoped_fulltext_graph_cypher(hit_ids, scope_node_id_rc, scope_hops, project, edge_types)
    else:
        cypher = _build_fulltext_graph_cypher(hit_ids, project, edge_types)

    if not is_safe_read_query(cypher):
        return {
            "status_code": 400,
            "body": {
                "success": False,
                "error": "Generated query failed read-only safety validation",
            },
        }

    return {
        "status_code": 200,
        "body": {
            "success": True,
            "cypher": cypher,
            "items": hits,
            "meta": {
                **meta,
                "edge_types": edge_types,
            },
            "telemetry": {
                **retrieval["telemetry"],
                "strategy_used": "fulltext_to_cypher",
            },
        },
    }


@retrieval_bp.post("/query")
def retrieval_query():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()
    payload = request.get_json(silent=True) or {}
    payload.setdefault("entry_point", "retrieval-query")

    try:
        with driver.session() as session:
            result = retrieve_nodes_for_query(session, payload, user_data["project"])
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (CypherSyntaxError, ClientError) as e:
        body, status = build_fulltext_error_response(payload, e)
        return jsonify(body), status

    if isinstance(result.get("telemetry"), dict):
        _log_telemetry(result["telemetry"])

    return jsonify({"success": True, **result})


@retrieval_bp.post("/chunks-by-depth")
def retrieval_chunks_by_depth():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()
    payload = request.get_json(silent=True) or {}
    payload.setdefault("entry_point", "retrieval-chunks-by-depth")
    if "project" not in payload or not str(payload.get("project") or "").strip():
        payload["project"] = user_data["project"]

    try:
        with driver.session() as session:
            result = build_chunks_by_depth_response(session, payload)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (CypherSyntaxError, ClientError) as e:
        return jsonify({"success": False, "error": f"Neo4j depth retrieval failed: {e}"}), 400

    telemetry = ((result.get("body") or {}).get("retrieval") or {}).get("telemetry")
    if isinstance(telemetry, dict):
        _log_telemetry(telemetry)

    return jsonify(result["body"]), result["status_code"]


@retrieval_bp.post("/query-cypher")
def retrieval_query_cypher():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()
    payload = request.get_json(silent=True) or {}
    payload.setdefault("entry_point", "retrieval-query-cypher")

    try:
        with driver.session() as session:
            result = build_query_cypher_response(session, payload, user_data["project"])
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except (CypherSyntaxError, ClientError) as e:
        body, status = build_fulltext_error_response(payload, e)
        return jsonify(body), status

    telemetry = (result.get("body") or {}).get("telemetry")
    if isinstance(telemetry, dict):
        _log_telemetry(telemetry)

    return jsonify(result["body"]), result["status_code"]
