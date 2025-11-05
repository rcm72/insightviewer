# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

from flask import Blueprint, jsonify
from app.models.neo4jConnect import Neo4jConnector  # Ensure correct path
from urllib.parse import unquote

# Create a Flask Blueprint
nodes_bp = Blueprint("nodes", __name__)

# Initialize Neo4j connection
neo4j = Neo4jConnector()

@nodes_bp.route("/get_nodes", methods=["GET"])
def get_nodes():
    """Fetch first 10 nodes from Neo4j."""
    query = "MATCH (n) RETURN n LIMIT 10"
    result = neo4j.query(query)
    nodes = [{"labels": list(record["n"].labels), "properties": dict(record["n"])} for record in result]
    return jsonify(nodes)

# Return properties for a given node type (supports Unicode / URL-encoded names)
def get_node_type_properties(node_type):
    """Return properties for a given node type."""
    # decode any percent-encoding just in case
    node_type = unquote(node_type)
    # Parameterized Cypher (preferred)
    query = "MATCH (n:NodeType {name: $node_type}) RETURN n"
    try:
        result = neo4j.query(query, {"node_type": node_type})
    except TypeError:
        # Fallback if neo4j.query only accepts a single argument
        safe_name = node_type.replace("'", "\\'")
        fallback = f"MATCH (n:NodeType) WHERE n.name = '{safe_name}' RETURN n"
        result = neo4j.query(fallback)

    nodes = [{"labels": list(record["n"].labels), "properties": dict(record["n"])} for record in result]
    return jsonify(nodes)

@nodes_bp.route("/node_type_properties/<path:node_type>", methods=["GET"])
def node_type_properties(node_type):
    return get_node_type_properties(node_type)








