import os
import re

import jwt
from flask import Blueprint, jsonify, request


JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

global_search_bp = Blueprint("global_search", __name__, url_prefix="/api/search")

driver = None

READ_ONLY_DISALLOWED = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL|LOAD\s+CSV|USING\s+PERIODIC\s+COMMIT|FOREACH|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT)\b",
    re.IGNORECASE,
)
READ_ONLY_REQUIRED = re.compile(r"\b(MATCH|RETURN|OPTIONAL\s+MATCH|UNWIND|WITH|WHERE)\b", re.IGNORECASE)

TEMPLATE_REGISTRY = {
    "connected_to_node": {
        "id": "connected_to_node",
        "label": "Connected to this node",
        "description": "Show nodes directly connected to the selected source node.",
        "needs_target_node": False,
        "needs_target_type": False,
        "supports_edge_filter": True,
    },
    "related_nodes_of_target_type": {
        "id": "related_nodes_of_target_type",
        "label": "Related nodes of target type",
        "description": "Show source-neighbor nodes filtered by the chosen target node type.",
        "needs_target_node": False,
        "needs_target_type": True,
        "supports_edge_filter": True,
    },
    "direct_connection_between_a_b": {
        "id": "direct_connection_between_a_b",
        "label": "Direct connection between A and B",
        "description": "Check whether two selected nodes are directly connected.",
        "needs_target_node": True,
        "needs_target_type": False,
        "supports_edge_filter": True,
    },
    "shortest_path_between_a_b": {
        "id": "shortest_path_between_a_b",
        "label": "Shortest path between A and B",
        "description": "Show the shortest path between the selected source and target nodes.",
        "needs_target_node": True,
        "needs_target_type": False,
        "supports_edge_filter": True,
    },
}


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


def is_safe_read_query(cypher: str) -> bool:
    if not cypher or READ_ONLY_DISALLOWED.search(cypher):
        return False
    return bool(READ_ONLY_REQUIRED.search(cypher))


def _normalize_project(project_value, user_project):
    project = str(project_value or user_project or "").strip()
    if not project or project.upper() == "ALL":
        return None
    return project


def _normalize_node_selection(value, field_name):
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")

    id_rc = str(value.get("id_rc") or "").strip()
    node_type = str(value.get("node_type") or "").strip()
    name = str(value.get("name") or "").strip()
    return {
        "id_rc": id_rc,
        "node_type": node_type,
        "name": name,
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


def _lookup_nodes_by_type_and_name(session, node_type, name, project):
    cypher = """
    MATCH (n)
    WHERE $node_type IN labels(n)
      AND coalesce(n.name, '') = $name
      AND ($project IS NULL OR n.projectName = $project OR n.projectName IS NULL)
    RETURN n.id_rc AS id_rc, n.name AS name, labels(n) AS labels, n.projectName AS project_name
    LIMIT 10
    """

    rows = session.run(
        cypher,
        node_type=node_type,
        name=name,
        project=project,
    ).data()

    if not rows and project:
        rows = session.run(
            cypher,
            node_type=node_type,
            name=name,
            project=None,
        ).data()

    return rows


def _resolve_node_identity(session, node, field_name, project):
    if node["id_rc"]:
        return node

    if not node["node_type"] or not node["name"]:
        raise ValueError(
            f"{field_name}.id_rc is missing. Choose a suggestion or provide both {field_name}.node_type and {field_name}.name."
        )

    rows = _lookup_nodes_by_type_and_name(session, node["node_type"], node["name"], project)
    rows_with_id = [row for row in rows if row.get("id_rc")]

    if len(rows_with_id) == 1:
        resolved = dict(node)
        resolved["id_rc"] = str(rows_with_id[0]["id_rc"])
        return resolved

    if len(rows_with_id) > 1:
        raise ValueError(
            f"{field_name} node '{node['name']}' of type '{node['node_type']}' is ambiguous. Choose a suggestion from the list to disambiguate it."
        )

    if rows:
        raise ValueError(
            f"Selected {field_name} node '{node['name']}' of type '{node['node_type']}' has no id_rc. Only the selected endpoint nodes need id_rc for guided search."
        )

    raise ValueError(
        f"Could not find {field_name} node '{node['name']}' of type '{node['node_type']}'. Choose a suggestion from the list."
    )


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


def _build_connected_to_node(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")

    edge_filter = "TRUE"
    if edge_types:
        edge_filter = f"(r IS NULL OR type(r) IN {_cypher_list(edge_types)})"

    return f"""
MATCH (s {{id_rc: {_quote_cypher_string(source['id_rc'])}}})
WHERE {_project_filter('s', project)}
OPTIONAL MATCH (s)-[r]-(t)
WHERE {_project_filter('t', project)} AND {edge_filter}
RETURN s, r, t
""".strip()


def _build_related_nodes_of_target_type(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["node_type"]:
        raise ValueError("target.node_type is required for this template")

    edge_filter = "TRUE"
    if edge_types:
        edge_filter = f"type(r) IN {_cypher_list(edge_types)}"

    return f"""
MATCH (s {{id_rc: {_quote_cypher_string(source['id_rc'])}}})
WHERE {_project_filter('s', project)}
MATCH (s)-[r]-(t)
WHERE {_quote_cypher_string(target['node_type'])} IN labels(t)
  AND {_project_filter('t', project)}
  AND {edge_filter}
RETURN s, r, t
""".strip()


def _build_direct_connection_between_a_b(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")

    edge_filter = "TRUE"
    if edge_types:
        edge_filter = f"(r IS NULL OR type(r) IN {_cypher_list(edge_types)})"

    return f"""
MATCH (a {{id_rc: {_quote_cypher_string(source['id_rc'])}}}), (b {{id_rc: {_quote_cypher_string(target['id_rc'])}}})
WHERE {_project_filter('a', project)} AND {_project_filter('b', project)}
OPTIONAL MATCH (a)-[r]-(b)
WHERE {edge_filter}
RETURN a AS s, r, b AS t
""".strip()


def _build_shortest_path_between_a_b(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")

    path_filter = "TRUE"
    if edge_types:
        path_filter = f"ALL(rel IN relationships(p) WHERE type(rel) IN {_cypher_list(edge_types)})"

    return f"""
MATCH (a {{id_rc: {_quote_cypher_string(source['id_rc'])}}}), (b {{id_rc: {_quote_cypher_string(target['id_rc'])}}})
WHERE {_project_filter('a', project)} AND {_project_filter('b', project)}
MATCH p = shortestPath((a)-[*..8]-(b))
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
WITH relationships(p) AS rels
UNWIND rels AS r
RETURN startNode(r) AS s, r, endNode(r) AS t
""".strip()


BUILDERS = {
    "connected_to_node": _build_connected_to_node,
    "related_nodes_of_target_type": _build_related_nodes_of_target_type,
    "direct_connection_between_a_b": _build_direct_connection_between_a_b,
    "shortest_path_between_a_b": _build_shortest_path_between_a_b,
}


@global_search_bp.get("/templates")
def list_templates():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    return jsonify({"success": True, "templates": list(TEMPLATE_REGISTRY.values())})


@global_search_bp.get("/node-names")
def autocomplete_node_names():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()

    node_type = str(request.args.get("node_type") or "").strip()
    query_text = str(request.args.get("q") or "").strip()
    if not node_type:
        return jsonify({"success": False, "error": "node_type is required"}), 400

    try:
        limit = max(1, min(int(request.args.get("limit", 15)), 50))
    except ValueError:
        return jsonify({"success": False, "error": "limit must be an integer"}), 400

    project = _normalize_project(request.args.get("project"), user_data["project"])

    cypher = """
    MATCH (n)
    WHERE $node_type IN labels(n)
      AND n.id_rc IS NOT NULL
      AND coalesce(n.name, '') <> ''
            AND ($query_text = '' OR toLower(coalesce(n.name, '')) CONTAINS toLower($query_text))
            AND ($project IS NULL OR n.projectName = $project OR n.projectName IS NULL)
    RETURN n.id_rc AS id_rc, n.name AS name, labels(n) AS labels
    ORDER BY CASE WHEN toLower(n.name) STARTS WITH toLower($query_text) THEN 0 ELSE 1 END, n.name
    LIMIT $limit
    """

    with driver.session() as session:
                rows = session.run(
            cypher,
            node_type=node_type,
            query_text=query_text,
            project=project,
            limit=limit,
        ).data()

                if not rows and project:
                        rows = session.run(
                                cypher,
                                node_type=node_type,
                                query_text=query_text,
                                project=None,
                                limit=limit,
                        ).data()

    items = [
        {
            "id_rc": row.get("id_rc"),
            "name": row.get("name"),
            "labels": row.get("labels") or [],
        }
        for row in rows
        if row.get("id_rc") and row.get("name")
    ]
    return jsonify({"success": True, "items": items})


@global_search_bp.get("/edge-types")
def list_edge_types():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()
    project = _normalize_project(request.args.get("project"), user_data["project"])

    cypher = """
    MATCH (a)-[r]-(b)
    WHERE $project IS NULL OR a.projectName = $project OR b.projectName = $project
    RETURN DISTINCT type(r) AS edge_type
    ORDER BY edge_type
    LIMIT 200
    """

    with driver.session() as session:
        rows = session.run(cypher, project=project).data()

    edge_types = [row.get("edge_type") for row in rows if row.get("edge_type")]
    return jsonify({"success": True, "edge_types": edge_types})


@global_search_bp.post("/build-cypher")
def build_cypher():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    _ensure_driver()

    payload = request.get_json(silent=True) or {}

    template_id = str(payload.get("template") or "").strip()
    if template_id not in BUILDERS:
        return jsonify({"success": False, "error": "Unsupported template"}), 400

    try:
        source = _normalize_node_selection(payload.get("source") or {}, "source")
        target = _normalize_node_selection(payload.get("target") or {}, "target")
        edge_types = _normalize_edge_types(payload.get("edge_types"))
        project = _normalize_project(payload.get("project"), user_data["project"])
        with driver.session() as session:
            source = _resolve_node_identity(session, source, "source", project)
            target = _resolve_node_identity(session, target, "target", project) if (target.get("id_rc") or target.get("name")) else target
        cypher = BUILDERS[template_id](source, target, edge_types, project)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    if not is_safe_read_query(cypher):
        return jsonify({"success": False, "error": "Generated query failed read-only safety validation"}), 400

    return jsonify(
        {
            "success": True,
            "template": template_id,
            "cypher": cypher,
            "meta": {
                "project": project,
                "edge_types": edge_types,
                "source": source,
                "target": target,
            },
        }
    )
