# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

# app/routes/people.py
from flask import Blueprint, request, jsonify
from app.models.neo4jConnect import Neo4jConnector

# Create a Flask Blueprint
people_bp = Blueprint("people", __name__)

# Initialize Neo4j connection
neo4j = Neo4jConnector()

@people_bp.route("/add_person", methods=["POST"])
def add_person():
    """Add a new person to Neo4j."""
    data = request.json
    name = data.get("name", "Unnamed Person")

    query = "CREATE (p:Person {name: $name}) RETURN p"
    result = neo4j.query(query, {"name": name})
    created_node = [{"labels": list(record["p"].labels), "properties": dict(record["p"])} for record in result]
    
    return jsonify({"message": "Person added", "person": created_node})
