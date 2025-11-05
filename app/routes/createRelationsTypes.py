# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

# createRelationsTypes.py
from neo4j import GraphDatabase
import configparser
from flask import Blueprint, jsonify, request
import uuid
import re

# Create a Flask Blueprint
relations_bp = Blueprint("createRelationsTypes", __name__)

# Load credentials from config.ini
config = configparser.ConfigParser()
config.read("/home/pi/Documents/rcmrlec/insightViewer/config.ini")

URI = config["NEO4J"]["URI"]
USERNAME = config["NEO4J"]["USERNAME"]
PASSWORD = config["NEO4J"]["PASSWORD"]

# Connect to Neo4j
driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))

# NOTE: APOC triggers are NOT supported on AuraDB.
# Instead of installing APOC triggers we provide backfill endpoints
# that set id_rc for existing nodes/relationships using randomUUID().

@relations_bp.route("/install-idrc-triggers", methods=["POST"])
def install_idrc_triggers_route():
    """
    Informational endpoint: APOC triggers cannot be installed on AuraDB.
    Use the backfill endpoints below to populate missing id_rc values,
    and ensure your create endpoints set id_rc on new objects.
    """
    return jsonify({
        "success": False,
        "error": "APOC triggers are not supported on AuraDB. Use /relations/backfill-idrc-nodes and /relations/backfill-idrc-rels instead."
    }), 400

@relations_bp.route("/backfill-idrc-nodes", methods=["POST"])
def backfill_idrc_nodes():
    """
    One-time backfill: set id_rc = randomUUID() for nodes that lack it.
    Be careful running this on very large databases; consider batching if needed.
    """
    try:
        query = """
        MATCH (n)
        WHERE n.id_rc IS NULL
        SET n.id_rc = randomUUID()
        RETURN count(n) AS updated
        """
        with driver.session() as session:
            result = session.run(query)
            updated = result.single()["updated"]
        return jsonify({"success": True, "updated": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@relations_bp.route("/backfill-idrc-rels", methods=["POST"])
def backfill_idrc_rels():
    """
    One-time backfill: set id_rc = randomUUID() for relationships that lack it.
    """
    try:
        query = """
        MATCH ()-[r]->()
        WHERE r.id_rc IS NULL
        SET r.id_rc = randomUUID()
        RETURN count(r) AS updated
        """
        with driver.session() as session:
            result = session.run(query)
            updated = result.single()["updated"]
        return jsonify({"success": True, "updated": updated}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def create_nodetype_relationships():
    query = """
    MATCH (a)-[r]->(b)
    WHERE NOT a:NodeType AND NOT b:NodeType
    WITH DISTINCT head(labels(a)) AS sourceType, type(r) AS relType, head(labels(b)) AS targetType
    MERGE (nt1:NodeType {name: sourceType})
    MERGE (nt2:NodeType {name: targetType})
    WITH nt1, nt2, relType
    CALL apoc.create.relationship(nt1, relType, {}, nt2) YIELD rel
    RETURN COUNT(rel) AS created_rels;
    """

    with driver.session() as session:
        result = session.run(query)
        count = result.single()["created_rels"]

    print(f"Created {count} relationships between NodeType nodes. "  )

@relations_bp.route("/addedge", methods=["POST"])
def add_edge():
    data = request.json
    edge_name = data.get("name")
    edge_type = data.get("type")
    from_node = data.get("from")
    to_node = data.get("to")

    print("10 addedge")

    if not edge_name or not edge_type or not from_node or not to_node:
        return jsonify({"success": False, "error": "Missing edge data"}), 400

    # validate edge_type to avoid injection - allow letters, numbers and underscore only
    if not re.fullmatch(r"[A-Za-z0-9_]+", edge_type):
        return jsonify({"success": False, "error": "Invalid edge type"}), 400

    new_rel_id = str(uuid.uuid4())

    
    print("20 addedge "+new_rel_id)

    # match by id_rc (string) and create relationship with id_rc property
    query = f"""
    MATCH (a), (b)
    WHERE a.id_rc = $from_node AND b.id_rc = $to_node
    CREATE (a)-[r:{edge_type} {{name: $edge_name, id_rc: $id_rc}}]->(b)
    RETURN r.id_rc AS edge_id
    """

    with driver.session() as session:
        result = session.run(query, from_node=str(from_node), to_node=str(to_node), edge_name=edge_name, id_rc=new_rel_id)
        rec = result.single()
        if not rec:
            return jsonify({"success": False, "error": "Failed to create relationship (nodes not found or other error)"}), 500
        edge_id = rec["edge_id"]

    return jsonify({"success": True, "edge_id": str(edge_id)})

@relations_bp.route("/get_edge_types", methods=["GET"])
def get_edge_types():
    # Get source and target node id_rc from the request
    source_param = request.args.get('source')
    target_param = request.args.get('target')

    if source_param is None or target_param is None:
        return jsonify({
            "success": False,
            "error": "Missing 'source' or 'target' parameter",
            "details": {
                "source": source_param,
                "target": target_param
            }
        }), 400

    # treat as id_rc strings (no int conversion)
    source_idrc = str(source_param)
    target_idrc = str(target_param)

    print(f"Source Node id_rc: {source_idrc}")
    print(f"Target Node id_rc: {target_idrc}")

    # Query NodeType graph based on the labels of the provided nodes
    query = """
        MATCH (n)
        WHERE n.id_rc IN $ids
        WITH labels(n) AS node_types
        UNWIND node_types AS node_type
        MATCH (m:NodeType)
        WHERE m.name = node_type
        WITH collect(m) AS nodes
        UNWIND nodes AS m1
        UNWIND nodes AS m2
        MATCH (m1)-[r]->(m2)
        RETURN distinct type(r) AS edgeType
        ORDER BY edgeType
    """

    edge_types = []
    ids = [source_idrc, target_idrc]
    with driver.session() as session:
        result = session.run(query, ids=ids)
        edge_types = [record["edgeType"] for record in result]

    print(f"Edge Types: {edge_types}")
    return jsonify({"success": True, "edge_types": edge_types})

# Run script
if __name__ == "__main__":
    create_nodetype_relationships()
    driver.close()
