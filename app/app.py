from flask import Flask, jsonify
from neo4j import GraphDatabase
import os

app = Flask(__name__)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("Sonja1val.")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@app.route("/")
def index():
	with driver.session() as session:
		result = session.run("RETURN 'Hello from Neo4j' AS msg")
		msg = result.single()["msg"]
	return jsonify({"ok": True, "neo4j": msg})

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5000)
