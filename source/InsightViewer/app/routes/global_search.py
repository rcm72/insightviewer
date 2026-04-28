import os
import re
from typing import Any

import jwt
from flask import Blueprint, jsonify, request

from ai.errors import AIError, ProviderConfigError, ProviderRequestError, ProviderResponseError
from ai.registry import ProviderRegistry
from ai.selection import (
    COOKIE_MODEL,
    COOKIE_PROVIDER,
    default_selection,
    get_selection_from_request,
    selection_to_json,
    validate_selection,
)
from ai.types import ChatRequest, ModelSelection
from graph.context import fetch_graph_context, format_context_for_prompt

## BUILDERS

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
    "apex_app_writes_to_db_object": {
        "id": "apex_app_writes_to_db_object",
        "label": "APEX app write paths to DB object",
        "description": "Show APEX pages, buttons, processes, and dynamic actions that lead to writes into the selected DB object.",
        "needs_target_node": True,
        "needs_target_type": False,
        "supports_edge_filter": False,
    },
    "apex_app_region_writes_to_db_object": {
        "id": "apex_app_region_writes_to_db_object",
        "label": "APEX app write paths to DB object via Region",
        "description": "Show APEX pages,regions that lead to writes into the selected DB object.",
        "needs_target_node": True,
        "needs_target_type": False,
        "supports_edge_filter": False,
    },    
    "apex_source_db_access_to_db_object": {
        "id": "apex_source_db_access_to_db_object",
        "label": "APEX app/page DB access paths to DB object",
        "description": "Show APEX paths from the selected app or page to the selected DB object through regions, buttons, processes, dynamic actions, and procedures.",
        "needs_target_node": True,
        "needs_target_type": False,
        "supports_edge_filter": False,
    },      
    "filtered_paths_between_a_b": {
        "id": "filtered_paths_between_a_b",
        "label": "Paths between A and B by edge types",
        "description": "Build a graph between the selected source and target nodes using only the selected relationship types.",
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


def _provider_models_map(registry: ProviderRegistry) -> dict[str, list[str]]:
    return {provider.id: provider.models for provider in registry.list_providers()}


def _parse_selection(payload: dict[str, Any]) -> ModelSelection:
    req_selection = get_selection_from_request(request)
    provider = payload.get("provider") or req_selection.provider or default_selection().provider
    model = payload.get("model") or req_selection.model or default_selection().model
    provider = str(provider).strip().lower()
    model = str(model).strip()

    if provider not in ("openai", "ollama"):
        raise ValueError("provider must be one of: openai, ollama")
    if not model:
        raise ValueError("model is required")

    return ModelSelection(provider=provider, model=model)  # type: ignore[arg-type]


def _extract_cypher_from_text(text: str) -> str:
    if not text:
        return ""

    stripped = text.strip()
    code_block = re.search(r"```(?:\s*cypher\s*\n)?(.*?)```", stripped, re.IGNORECASE | re.DOTALL)
    if code_block:
        stripped = code_block.group(1).strip()

    match_start = re.search(r"\b(MATCH|OPTIONAL\s+MATCH|UNWIND|WITH|RETURN)\b", stripped, re.IGNORECASE)
    if match_start:
        stripped = stripped[match_start.start() :].strip()

    return stripped.strip("`").strip()


def _fetch_node_type_names(session, project):
    cypher = """
    MATCH (n:NodeType)
    WHERE $project IS NULL OR n.projectName = $project OR n.projectName IS NULL
    RETURN DISTINCT n.name AS name
    ORDER BY name
    LIMIT 200
    """

    rows = session.run(cypher, project=project).data()
    if not rows and project:
        rows = session.run(cypher, project=None).data()

    return [str(row.get("name") or "").strip() for row in rows if str(row.get("name") or "").strip()]


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

def _lookup_node_by_id_rc(session, id_rc, project):
    cypher = """
    MATCH (n {id_rc: $id_rc})
    WHERE $project IS NULL OR n.projectName = $project OR n.projectName IS NULL
    RETURN n.id_rc AS id_rc, n.name AS name, labels(n) AS labels, n.projectName AS project_name
    LIMIT 1
    """
    rows = session.run(cypher, id_rc=id_rc, project=project).data()
    if not rows and project:
        rows = session.run(cypher, id_rc=id_rc, project=None).data()
    return rows[0] if rows else None

def _resolve_node_identity(session, node, field_name, project):
    if node["id_rc"]:
        row = _lookup_node_by_id_rc(session, node["id_rc"], project)
        if not row:
            raise ValueError(
                f"Could not find {field_name} node with id_rc '{node['id_rc']}'."
            )
        resolved = dict(node)
        if not resolved.get("name"):
            resolved["name"] = str(row.get("name") or "")
        if not resolved.get("node_type"):
            labels = row.get("labels") or []
            resolved["node_type"] = str(labels[0]) if labels else ""
        return resolved

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

def _build_apex_app_writes_to_db_object(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")

    source_type = str(source.get("node_type") or "").strip()
    if source_type not in ("APEXApp", "APEXPage"):
        raise ValueError("source.node_type must be APEXApp or APEXPage for this template")

    source_id = _quote_cypher_string(source["id_rc"])
    obj_id = _quote_cypher_string(target["id_rc"])

    path_filter = "TRUE"
    if edge_types:
        path_filter = f"ALL(rel IN relationships(p) WHERE type(rel) IN {_cypher_list(edge_types)})"

    if source_type == "APEXApp":
        start_match = f"MATCH (start:APEXApp {{id_rc: {source_id}}})"
        start_pattern = "(start)-[:HAS_PAGE]->(page:APEXPage)"
    else:
        start_match = f"MATCH (start:APEXPage {{id_rc: {source_id}}})"
        start_pattern = "(start:APEXPage)"

    return f"""
{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_PROCESS]->(procNode:APEXPageProcess)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:TRIGGERS_DA]->(da:APEXDynamicAction)
       -[:HAS_ACTION]->(step:APEXDynamicActionStep)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:TRIGGERS_DA]->(da:APEXDynamicAction)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t
""".strip()

def _build_apex_app_region_db_access_to_db_object(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")

    source_type = str(source.get("node_type") or "").strip()
    if source_type not in ("APEXApp", "APEXPage"):
        raise ValueError("source.node_type must be APEXApp or APEXPage for this template")

    source_id = _quote_cypher_string(source["id_rc"])
    obj_id = _quote_cypher_string(target["id_rc"])

    path_filter = "TRUE"
    if edge_types:
        path_filter = f"ALL(rel IN relationships(p) WHERE type(rel) IN {_cypher_list(edge_types)})"

    if source_type == "APEXApp":
        start_match = f"MATCH (start:APEXApp {{id_rc: {source_id}}})"
        start_pattern = "(start)-[:HAS_PAGE]->(page:APEXPage)"
    else:
        start_match = f"MATCH (start:APEXPage {{id_rc: {source_id}}})"
        start_pattern = "(start:APEXPage)"

    return f"""
{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_REGION]->(region:APEXRegion)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t
""".strip()


def _build_apex_source_db_access_to_db_object(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")

    source_type = str(source.get("node_type") or "").strip()
    if source_type not in ("APEXApp", "APEXPage"):
        raise ValueError("source.node_type must be APEXApp or APEXPage for this template")

    source_id = _quote_cypher_string(source["id_rc"])
    obj_id = _quote_cypher_string(target["id_rc"])

    path_filter = "TRUE"
    if edge_types:
        path_filter = f"ALL(rel IN relationships(p) WHERE type(rel) IN {_cypher_list(edge_types)})"

    if source_type == "APEXApp":
        start_match = f"MATCH (start:APEXApp {{id_rc: {source_id}}})"
        start_pattern = "(start)-[:HAS_PAGE]->(page:APEXPage)"
    else:
        start_match = f"MATCH (start:APEXPage {{id_rc: {source_id}}})"
        start_pattern = "(start:APEXPage)"
    return f"""
{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_PROCESS]->(procNode:APEXPageProcess)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:TRIGGERS_DA]->(da:APEXDynamicAction)
       -[:HAS_ACTION]->(step:APEXDynamicActionStep)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_BUTTON]->(btn:APEXButton)
       -[:TRIGGERS_DA]->(da:APEXDynamicAction)
       -[:CALLS_PROCEDURE]->(pr:OracleProcedure)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t

UNION

{start_match}
MATCH (obj:ORADbObject {{id_rc: {obj_id}}})
MATCH p =
  {start_pattern}
       -[:HAS_REGION]->(region:APEXRegion)
       -[:SELECTS_FROM|INSERTS_INTO|UPDATES|DELETES_FROM|MERGES_INTO]->(obj)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN startNode(r) AS s, r, endNode(r) AS t
""".strip()

def _build_filtered_paths_between_a_b(source, target, edge_types, project):
    if not source["id_rc"]:
        raise ValueError("source.id_rc is required")
    if not target["id_rc"]:
        raise ValueError("target.id_rc is required")
    if not edge_types:
        raise ValueError("At least one edge type must be selected")

    path_filter = f"ALL(rel IN relationships(p) WHERE type(rel) IN {_cypher_list(edge_types)})"

    return f"""
MATCH (a {{id_rc: {_quote_cypher_string(source['id_rc'])}}}),
      (b {{id_rc: {_quote_cypher_string(target['id_rc'])}}})
WHERE {_project_filter('a', project)} AND {_project_filter('b', project)}
MATCH p = (a)-[*..8]-(b)
WHERE ALL(n IN nodes(p) WHERE {_project_filter('n', project)})
  AND {path_filter}
UNWIND relationships(p) AS r
RETURN DISTINCT startNode(r) AS s, r, endNode(r) AS t
""".strip()


BUILDERS = {
    "connected_to_node": _build_connected_to_node,
    "related_nodes_of_target_type": _build_related_nodes_of_target_type,
    "direct_connection_between_a_b": _build_direct_connection_between_a_b,
    "shortest_path_between_a_b": _build_shortest_path_between_a_b,
    "apex_app_writes_to_db_object": _build_apex_app_writes_to_db_object,    
    "apex_app_region_writes_to_db_object": _build_apex_app_region_db_access_to_db_object,
    "apex_source_db_access_to_db_object": _build_apex_source_db_access_to_db_object,
    "filtered_paths_between_a_b": _build_filtered_paths_between_a_b,
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


@global_search_bp.post("/ai-build-cypher")
def build_cypher_with_ai():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    try:
        _ensure_driver()
        payload = request.get_json(silent=True) or {}

        question = str(payload.get("question") or payload.get("natural_language") or "").strip()
        if not question:
            return jsonify({"success": False, "error": "question is required"}), 400

        registry = ProviderRegistry()
        provider_models = _provider_models_map(registry)

        requested_selection = _parse_selection(payload)
        model_explicitly_set = bool(str(payload.get("model") or "").strip())
        if model_explicitly_set:
            selection = requested_selection
        else:
            selection = validate_selection(requested_selection, provider_models)
        provider = registry.get_provider(selection.provider)

        project = _normalize_project(payload.get("project"), user_data["project"])
        edge_types = _normalize_edge_types(payload.get("edge_types"))
        source = _normalize_node_selection(payload.get("source") or {}, "source")
        target = _normalize_node_selection(payload.get("target") or {}, "target")
        sample_limit = max(1, min(int(payload.get("sample_limit") or 12), 20))

        with driver.session() as session:
            ctx = fetch_graph_context(session, project=project, sample_limit=sample_limit)
            node_type_names = _fetch_node_type_names(session, project)

        prompt_parts = [format_context_for_prompt(ctx).strip()]
        if node_type_names:
            shown = ", ".join(node_type_names[:80])
            suffix = " ..." if len(node_type_names) > 80 else ""
            prompt_parts.append(f"Known NodeType names:\n- {shown}{suffix}")

        if source.get("id_rc") or source.get("node_type") or source.get("name"):
            prompt_parts.append(
                "Selected source hint:\n"
                f"- id_rc: {source.get('id_rc') or 'N/A'}\n"
                f"- node_type: {source.get('node_type') or 'N/A'}\n"
                f"- name: {source.get('name') or 'N/A'}"
            )

        if target.get("id_rc") or target.get("node_type") or target.get("name"):
            prompt_parts.append(
                "Selected target hint:\n"
                f"- id_rc: {target.get('id_rc') or 'N/A'}\n"
                f"- node_type: {target.get('node_type') or 'N/A'}\n"
                f"- name: {target.get('name') or 'N/A'}"
            )

        if edge_types:
            prompt_parts.append(f"Preferred relationship types: {', '.join(edge_types)}")

        project_instruction = (
            f"If you match domain nodes, include project filtering such as projectName = {_quote_cypher_string(project)} OR projectName IS NULL where appropriate."
            if project
            else "Project scope is ALL, so do not invent a project filter."
        )

        prompt_parts.append(
            "Output contract:\n"
            "- Return exactly one Cypher query and nothing else.\n"
            "- Do not use markdown fences, explanations, or comments.\n"
            "- The query must be read-only. Never use CREATE, MERGE, DELETE, SET, REMOVE, DROP, CALL, LOAD CSV, or FOREACH.\n"
            "- Use only labels, relationship types, and property names present in the provided context.\n"
            "- Prefer graph-friendly results for InsightViewer. Usually return nodes and relationships, for example RETURN s, r, t.\n"
            "- Do not return path variables directly. If you need a path, UNWIND relationships(p) AS r and RETURN startNode(r) AS s, r, endNode(r) AS t.\n"
            f"- {project_instruction}"
        )
        prompt_parts.append(f"User request:\n{question}")

        system_prompt = str(
            payload.get("system")
            or "You generate safe Neo4j Cypher queries for InsightViewer based only on provided schema context."
        ).strip()
        user_prompt = "\n\n".join(part for part in prompt_parts if part).strip()

        resp = provider.chat(
            ChatRequest(
                system=system_prompt,
                user=user_prompt,
                model=selection.model,
                temperature=0.0,
                max_tokens=int(payload.get("max_tokens") or 900),
            )
        )

        cypher = _extract_cypher_from_text(resp.text)
        if not cypher:
            return jsonify({"success": False, "error": "AI response did not contain a Cypher query"}), 502

        if not is_safe_read_query(cypher):
            return jsonify({"success": False, "error": "AI generated query failed read-only safety validation"}), 400

        out = jsonify(
            {
                "success": True,
                "provider": selection.provider,
                "model": selection.model,
                "selection": selection_to_json(selection),
                "cypher": cypher,
                "graph_context": {
                    "project": ctx.project,
                    "labels": ctx.labels,
                    "relationship_types": ctx.rel_types,
                    "sample_nodes": ctx.sample_nodes,
                    "node_types": node_type_names,
                },
            }
        )
        out.set_cookie(COOKIE_PROVIDER, selection.provider, max_age=60 * 60 * 24 * 30, samesite="Lax")
        out.set_cookie(COOKIE_MODEL, selection.model, max_age=60 * 60 * 24 * 30, samesite="Lax")
        return out

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ProviderConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except ProviderRequestError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except ProviderResponseError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except AIError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Unexpected error: {e}"}), 500



