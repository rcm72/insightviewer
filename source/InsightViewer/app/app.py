# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert �mrlec

# app.py
# pkill -f code-server 
# ps aux | grep code-server 

# pkill -f git || true 

# CREATE CONSTRAINT cg_name IF NOT EXISTS
# FOR (n:CustomGraph) REQUIRE n.name IS UNIQUE; 

# CREATE CONSTRAINT cgn_name IF NOT EXISTS
# FOR (n:CustomGraphNode) REQUIRE n.name IS UNIQUE;
# curl -X POST "http://192.168.1.6:5000/openai-cypher" -H "Content-Type: application/json" -d "{\"query\":\" poi��i najkraj�o pot med nodom tipa table in nodom tipa package \",\"task\":\"explain\",\"execute\":false}"   
# git remote set-url origin https://github.com/rcm72/insightviewer.git
# test¸
# git commit -m "message"
# git push
# source venv/bin/activate
# python -m insightViewer

import os
import sys
import json 
import configparser
from datetime import datetime, date 
from flask import Flask, abort, render_template, request, jsonify, render_template_string, url_for, send_from_directory, send_file, redirect
import jwt  # Import the jwt module  
from flask.json.provider import DefaultJSONProvider
from neo4j import GraphDatabase
import uuid  # For generating unique IDs
from neo4j.graph import Node, Relationship  # Import for type checking
import requests 
import re 
from html import unescape
from neo4j.time import Date as Neo4jDate
from dotenv import load_dotenv
import sys
import os

# JWT configuration
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

load_dotenv()

# Ensure the app directory is in Python's path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'routes')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend\auth')))

from backend.auth.security_bp import security_bp

SYSTEM_BUNDLE = (
    "You are a senior front-end engineer.  "
    "Generate JavaScript, CSS, or an HTML fragment"
    "and return ONLY that code (no prose, no Markdown, no code fences)."
)

SYSTEM_SPLIT = (
    "You are a senior front-end engineer. "
    "Return ONLY compact JSON with three string fields: "
    "{\"html\":\"...\",\"css\":\"...\",\"js\":\"...\"}. "
    "Do not add Markdown, comments, or explanations. "
    "html must NOT include <style> or <script>. Put all CSS in css and all JS in js."
)



def _strip_fences(text: str) -> str:
    if not text: 
        return text
    text = text.strip()
    text = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*", "", text, flags=re.S)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.S)
    return text.strip()

def _extract_full_html(text: str) -> str:
    if not text: 
        return ""
    # prefer full document
    m = re.search(r"(?is)(<!DOCTYPE\s+html[^>]*>.*?</html>)", text)
    if m: return m.group(1).strip()
    m = re.search(r"(?is)(<html[^>]*>.*?</html>)", text)
    if m: return m.group(1).strip()
    # fallback: treat as fragment and wrap
    frag = text.strip()
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>AI</title></head><body>{frag}</body></html>"


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

app = Flask(__name__)
app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)

app.config['TEMPLATES_AUTO_RELOAD'] = True # for development; auto-reload templates on change
app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "static", "images"))
app.config.setdefault("MAX_CONTENT_LENGTH", 512 * 1024 * 1024)

# Register uploader blueprint
from routes.uploader import uploader_bp
app.register_blueprint(uploader_bp, url_prefix="/uploader")



# Register the security blueprint
app.register_blueprint(security_bp)

config = configparser.ConfigParser()

base_dir = os.getenv('BASE_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# prefer private config when present
private_cfg = os.path.join(base_dir, 'config_private.ini')
default_cfg = os.path.join(base_dir, 'config.ini')
config_path = private_cfg if os.path.exists(private_cfg) else default_cfg
files_read = config.read(config_path)
print("Config files read:", files_read)
print("Using config:", config_path)
print("Loaded sections:", config.sections())
if "NEO4J" in config:
    print("NEO4J URI from config:", config.get("NEO4J", "URI", fallback=None))

# --- NEW: Ollama embedding config & helpers ---
OLLAMA_URL = config.get("OLLAMA", "BASE", fallback=None)
OLLAMA_EMB_MODEL = config.get("OLLAMA", "EMB_MODEL", fallback=None)

def _ollama_post_embedding(text: str, timeout: int = 30):
    """
    Try common Ollama embedding endpoints and return a vector list on success.
    Handles several response shapes returned by different Ollama clients.
    """
    if not OLLAMA_URL or not OLLAMA_EMB_MODEL:
        raise RuntimeError("OLLAMA.BASE or OLLAMA.EMB.MODEL not configured in config.ini")

    url_base = OLLAMA_URL.rstrip('/')
    endpoints = [
        "/api/embeddings",  # some clients
        "/api/embed",       # other clients
        "/api/embeds",
    ]
    payload_variants = [
        {"model": OLLAMA_EMB_MODEL, "prompt": text},
        {"model": OLLAMA_EMB_MODEL, "input": text},
        {"model": OLLAMA_EMB_MODEL, "text": text},
    ]
    last_err = None
    for ep in endpoints:
        for payload in payload_variants:
            try:
                r = requests.post(f"{url_base}{ep}", json=payload, timeout=timeout)
                if not r.ok:
                    last_err = f"{r.status_code} {r.text}"
                    continue
                j = r.json()
                # common shapes:
                if isinstance(j, dict):
                    if "embedding" in j and isinstance(j["embedding"], list):
                        return j["embedding"]
                    if "embeddings" in j:
                        emb = j["embeddings"]
                        if isinstance(emb, list) and emb:
                            first = emb[0]
                            if isinstance(first, dict) and "embedding" in first:
                                return first["embedding"]
                            if isinstance(first, list):
                                return first
                    if "data" in j and isinstance(j["data"], list):
                        d0 = j["data"][0]
                        if isinstance(d0, dict) and "embedding" in d0:
                            return d0["embedding"]
                # fallback: if top-level json is list and first element is list
                if isinstance(j, list) and j and isinstance(j[0], list):
                    return j[0]
            except Exception as e:
                last_err = str(e)
                continue
    raise RuntimeError(f"Failed to obtain embedding from Ollama. Last error: {last_err}")

# --- Neo4j Setup ---
NEO4J_URI = config["NEO4J"]["URI"]
print("DEBUG: final NEO4J URI to be used:", repr(NEO4J_URI))
NEO4J_USERNAME = config["NEO4J"]["USERNAME"]
NEO4J_PASSWORD = config["NEO4J"]["PASSWORD"]
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment variables")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# --- initialize route modules that need the driver BEFORE registering blueprints ---
# import module object, call its init_driver(driver), then import their blueprints
import routes.createNodeTypes as createNodeTypes
createNodeTypes.init_driver(driver)

# if other route modules expose init_driver, do the same:
# import routes.createRelationsTypes as createRelationsTypes
# createRelationsTypes.init_driver(driver)

# Now import blueprints and register them
from routes.createNodeTypes import nodes_bp, get_node_types, get_node_type_visuals, add_node_type, update_node_properties, test_post, create_name_indexes, get_custom_graphs
from routes.createRelationsTypes import relations_bp, get_edge_types
from routes.templates_api import bp as templates_api_bp

# Register Blueprints
app.register_blueprint(relations_bp, url_prefix="/relations")
app.register_blueprint(nodes_bp, url_prefix="/nodes")
app.register_blueprint(templates_api_bp, url_prefix="/api")

@app.route("/")
def root():
    # vedno pokaži login (frontend sam poskrbi za redirect naprej)
    return render_template("login.html")

from flask import redirect

@app.route("/home")
def main_app():
    try:
        # Extract JWT from the 'access_token' cookie
        token = request.cookies.get('access_token')
        if not token:
            return redirect("/login")

        # Decode and verify the JWT
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("sub")  # 'sub' is the user ID
        project = payload.get("project")

        if not uid or not project:
            return redirect("/login")

        # Render the home page with user-specific data
        return render_template("index.html", user_id=uid, project=project)

    except jwt.JWTError as e:
        print(f"JWT Error: {e}")
        return redirect("/login")

@app.route("/about")
def about_app():
  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]    

    return render_template("about.html")

@app.route("/quiz_rag")
def quiz_rag():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("quiz_rag.html")

# --- NEW: quiz page route ---
@app.route("/ask_vector")
def ask_vector_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("ask_vector.html")

# --- NEW: quiz_ui page route ---
@app.route("/quiz_ui")
def quiz_ui_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("quiz_ui.html")

# --- NEW: quiz_prep_ui page route ---
@app.route("/quiz_prep_ui")
def quiz_prep_ui_page():
  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]    

    return render_template("quiz_prep_ui.html")

# --- NEW: quiz results viewer route ---
@app.route("/quiz_results")
def quiz_results_page():
  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("quiz_results.html")

# --- NEW: vector search API used by quiz front-end ---
@app.post("/api/quiz/search")
def api_quiz_search():
  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    """
    POST JSON: { "question": "...", "top_k": 6 }
    Returns top matching Chunk nodes (id, text, score).
    """
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"success": False, "error": "Missing 'question'"}), 400
    try:
        emb = _ollama_post_embedding(question)
    except Exception as e:
        app.logger.exception("Failed to get embedding")
        return jsonify({"success": False, "error": str(e)}), 500

    top_k = int(data.get("top_k", 6))
    try:
        with driver.session() as session:
            # use the vector index; pass dimension = len(emb)
            rows = session.run("""
                CALL db.index.vector.queryNodes('chunk_embedding_index', $dim, $vec)
                YIELD node, score
                RETURN node.id_rc AS id, node.text AS text, score
                ORDER BY score DESC
                LIMIT $k
            """, dim=len(emb), vec=emb, k=top_k).data()
        return jsonify({"success": True, "rows": rows})
    except Exception as e:
        app.logger.exception("Neo4j vector query failed")
        return jsonify({"success": False, "error": str(e)}), 500

def render_page(page):
    if request.path.startswith('/api/') or request.path.startswith('/static/'):
        abort(404)
    return render_template(page)

def convert_dates(obj):
    """
    Recursively convert datetime/date/neo4j.time.Date to ISO strings
    in nested dict/list structures.
    """
    if isinstance(obj, (datetime, date, Neo4jDate)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: convert_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_dates(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(convert_dates(v) for v in obj)
    return obj


@app.route("/login")
def login_page():
    return render_template("login.html")

#@app.route("/", endpoint="root_login")
def index_page():
    return render_template("login.html")

@app.route("/index", endpoint="root_index")
def index_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("index.html")

@app.route("/quiz")
def quiz_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return render_template("quiz_rag_egipt.html")

@app.get("/api/projects")
def get_projects():     
    """
    Fetch list of projects from Neo4j (Project nodes).
    Returns JSON array of {id, name} objects.
    """
    try:
        with driver.session() as session:
            result = session.run("MATCH (s:Project) RETURN s.name AS name ORDER BY s.name")
            projects = [{"id": record["name"], "name": record["name"]} for record in result]
        return jsonify(projects)
    except Exception as e:
        app.logger.exception("Failed to fetch projects from Neo4j")
        return jsonify({"error": str(e)}), 500



@app.route("/run-cypher", methods=["POST"])
def run_cypher():
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]

    try:
        data = request.json or {}
        query = data.get("query")
        project = data.get("project")  # <-- NEW: current project from frontend
        print("run-cpyher query: ", query)
        print("run-cpyher project: ", project)

        nodes = {}
        edges = []

        print(f"[{datetime.now()}] Start.")

        with driver.session() as session:
            result = session.run(query)
            for record in result:
                for value in record.values():
                    # Debugging
                    print("Debugging value:", value)
                    print("Labels 1:", getattr(value, "labels", None))

                    # ---- NODES ----
                    if hasattr(value, "id") and hasattr(value, "labels"):
                        properties = dict(value)

                        # FILTER BY PROJECT for nodes
                        if project and properties.get("projectName") != project:
                            # Node is from another project -> skip
                            continue

                        node_id = properties.get("id_rc", str(value.id))
                        if node_id not in nodes:
                            properties = convert_dates(properties)

                            full_name = properties.get("name", f"Node {node_id}")
                            short_name = full_name.split(".")[-1]
                            nodeType = next(iter(value.labels), "Unknown")

                            nodes[node_id] = {
                                "id": node_id,
                                "label": short_name,
                                "nodeType": nodeType,
                                "labels": list(value.labels),
                                "properties": properties
                            }

                    # ---- RELATIONSHIPS ----
                    if hasattr(value, "start_node") and hasattr(value, "end_node"):
                        print("run_cypher relationship edges:", value)

                        rel_props = dict(value)
                        start_props = dict(value.start_node)
                        end_props   = dict(value.end_node)

                        # FILTER BY PROJECT for relationships
                        if project:
                            start_proj = start_props.get("projectName")
                            end_proj   = end_props.get("projectName")

                            # if neither end is in this project, skip the relationship
                            if start_proj != project and end_proj != project:
                                continue

                        start_id = start_props.get("id_rc", str(value.start_node.id))
                        end_id   = end_props.get("id_rc", str(value.end_node.id))
                        rel_id   = rel_props.get("id_rc", str(value.id))

                        edge = {
                            "id": rel_id,
                            "from": start_id,
                            "to": end_id,
                            "type": value.type,
                            "label": value.type
                        }

                        print("DEBUG: Edge deduplication check:", rel_id)
                        edge = convert_dates(edge)

                        if edge not in edges:
                            edges.append(edge)

        # Convert all dates/datetimes to strings on the FULL payload
        payload = {
            "success": True,
            "nodes": list(nodes.values()),
            "edges": edges,
        }
        payload = convert_dates(payload)

        print("DEBUG payload repr in run_cypher:")
        print(repr(payload))   # <--- NEW: raw repr, no JSON encoding

        print(f"[{datetime.now()}] Stop.")
        print(f"[{datetime.now()}] Nodes: {len(payload['nodes'])}, Edges: {len(payload['edges'])}")
        try:
            print(json.dumps(payload, indent=4))
        except TypeError as e:
            print("DEBUG json.dumps failed in run_cypher:", e)

        return jsonify(payload)
    except Exception as e:
        print(f"Error in run_cypher: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# --- API Endpoint to Add a Node ---
@app.route("/add-node", methods=["POST"])
def add_node():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]    

    try:
        data = request.json
        print("Request data:", data)  # Debugging log        
        node_name = data.get("name")
        node_label = data.get("label")
        nodeImageField = data.get("nodeImageField")
        isManualGraph = data.get("isManualGraph"); # Flag to indicate if the graph is manual


        if not node_name or not node_label:
            return jsonify({"success": False, "error": "Missing 'name' or 'label' in request"}), 400

        # Query to fetch properties of the corresponding NodeType
        node_type_query = """
        MATCH (t:NodeType {name: $label})
        RETURN t
        """

        with driver.session() as session:
            # Fetch NodeType properties
            result = session.run(node_type_query, label=node_label)
            record = result.single()
            if not record:
                return jsonify({"success": False, "error": f"NodeType '{node_label}' not found"}), 404

            node_type_properties = dict(record["t"])  # Extract NodeType properties
            print("NodeType properties before filtering:", node_type_properties)  # Debugging log

            excluded_keys = {"size", "id_rc", "id", "name"}  # avoid clobbering generated id_rc and node name
            filtered_properties = {k: v for k, v in node_type_properties.items() if k not in excluded_keys}
            print("Filtered NodeType properties:", filtered_properties)  # Debugging log

            # Generate a stable id_rc for the new node
            new_id_rc = str(uuid.uuid4())

            # Add the new node with combined properties including id_rc
            create_node_query = f"""
            CREATE (n:{node_label} {{name: $name, id_rc: $id_rc, image: $image}})
            SET n += $properties
            RETURN n.id_rc AS node_id, labels(n) AS labels
            """
            combined_properties = filtered_properties  # Start with filtered NodeType properties
            combined_properties["name"] = node_name  # Explicitly set the node's name

            result = session.run(create_node_query, name=node_name, properties=combined_properties, id_rc=new_id_rc, image=nodeImageField)
            record = result.single()
            if record:
                node_id = record["node_id"]
                node_labels = record["labels"]
                print("Node created with id_rc:", node_id, "and labels:", node_labels)  # Debugging log
                return jsonify({"success": True, "node_id": node_id, "labels": node_labels})
            else:
                return jsonify({"success": False, "error": "Failed to create node"}), 500
    except Exception as e:
        print(f"Error in add_node: {e}")  # Debugging log
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/update-node", methods=["POST"])
def update_node():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    data = request.json
    node_id = data.get("id")
    new_name = data.get("name")

    if not node_id or not new_name:
        return jsonify({"success": False, "error": "Missing node ID or name"}), 400

    query = """
    MATCH (n)
    WHERE n.id_rc = $node_id
    SET n.name = $new_name
    RETURN n.name AS updated_name
    """

    with driver.session() as session:
        result = session.run(query, node_id=node_id, new_name=new_name)
        rec = result.single()
        updated_name = rec["updated_name"] if rec else None

    return jsonify({"success": True, "updated_name": updated_name})

@app.route("/get_node_types", methods=["GET"])
def get_node_types_route():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return get_node_types()  # Call the function directly

@app.route("/get_edge_types", methods=["GET"])
def get_edge_types_route():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    return get_edge_types()  # Call the function directly

@app.route("/expand-node", methods=["POST"])
def expand_node():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        

    print("Executing expand_node start...")

    try:
        data = request.get_json() or {}
        node_id = data.get("node_id")
        print(f"expand_node called with node_id: {node_id}")

        if not node_id:
            return jsonify({"success": False, "error": "Missing node ID"}), 400

        query = """
        MATCH (n)-[r]-(m)
        WHERE (n.id_rc = $node_id OR m.id_rc = $node_id)
          AND NOT 'CustomGraph' IN labels(n)
          AND NOT 'CustomGraph' IN labels(m)
          AND NOT 'customGraphNode' IN labels(n)
          AND NOT 'customGraphNode' IN labels(m)
          AND NOT 'customGraphNodePosition' IN labels(n)
          AND NOT 'customGraphNodePosition' IN labels(m)
        RETURN n, r, m
        """
        query1 = """
        MATCH (n)-[r]-(m)
        WHERE n.id_rc = $node_id OR m.id_rc = $node_id
        RETURN n, r, m
        """        

        nodes_dict = {}
        edges_dict = {}  # use dict keyed by edge_id to deduplicate

        print("Executing expand_node query...")
        print("expand_node query:", query)
        print("node_id parameter:", node_id)    
        with driver.session() as session:
            result = session.run(query, node_id=node_id)
            records = list(result)
            print(f"expand_node query returned {len(records)} records")

            for record in records:
                n_node = record.get("n")
                m_node = record.get("m")
                r_rel  = record.get("r")

                print("expand_node raw record:", record)
                print("  n:", n_node)
                print("  m:", m_node)
                print("  r:", r_rel, "type:", type(r_rel))

                # --- nodes ---
                for node in (n_node, m_node):
                    if not node:
                        continue
                    node_id_rc = node.get("id_rc")
                    if not node_id_rc or node_id_rc in nodes_dict:
                        continue

                    nodes_dict[node_id_rc] = {
                        "id": node_id_rc,
                        "id_rc": node_id_rc,
                        "label": node.get("name") or (list(node.labels)[0] if node.labels else "Unknown"),
                        "labels": list(node.labels),
                        "properties": dict(node),
                        "color": node.get("color", "#97C2FC"),
                        "shape": node.get("shape", "ellipse"),
                    }

                # --- edges ---
                print("********************")
                print("expand_node processing relationship r:", r_rel)
                if isinstance(r_rel, Relationship) and n_node and m_node:
                    from_id = n_node.get("id_rc")
                    to_id   = m_node.get("id_rc")
                    if not from_id or not to_id:
                        print("  skip edge, missing from_id/to_id:", from_id, to_id)
                        continue

                    rel_props  = dict(r_rel)
                    rel_id = rel_props.get("id_rc") or str(r_rel.id)

                    # Deduplicate by relationship id_rc / id
                    #if edge_id_rc in edges_dict:
                        # already added this relationship once; skip the reverse duplicate
                        #continue

                    edge = {
                        "id": rel_id,
                        "id_rc": rel_id,
                        "from": from_id,
                        "to": to_id,
                        "label": r_rel.type or rel_props.get("name", ""),
                    }
                    edges_dict[rel_id] = edge
                    print("  added edge:", edge)
                else:
                    print("  Warning: missing relationship or nodes in record")

        print("expand_node sample nodes:", list(nodes_dict.values())[:3])
        print("expand_node sample edges:", list(edges_dict.values())[:5])
        print(f"expand_node returning {len(nodes_dict)} nodes, {len(edges_dict)} edges")

        payload = {
            "success": True,
            "nodes": list(nodes_dict.values()),
            "edges": list(edges_dict.values()),
        }
        payload = convert_dates(payload)
        print("DEBUG: expand_node response payload:", payload)
        return jsonify(payload)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/delete-selected", methods=["POST"])
def delete_selected():
    """
    Deletes the selected nodes and edges from the Neo4j database.
    """

    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]        
    

    print("delete-selected called") 

    data = request.json
    selected_nodes = data.get("nodes", [])
    selected_edges = data.get("edges", [])

    # Normalize to strings (we use id_rc strings)
    selected_nodes = [str(x) for x in selected_nodes]
    selected_edges = [str(x) for x in selected_edges]

    print(f"Selected nodes to delete: {selected_nodes}")
    print(f"Selected edges to delete: {selected_edges}")

    try:
        with driver.session() as session:
            # Delete edges
            if selected_edges:
                query = """
                MATCH ()-[r]->()
                WHERE r.id_rc IN $edge_ids
                DELETE r
                """
                print(f"Executing query: {query} with edge_ids: {selected_edges}")
                session.run(query, edge_ids=selected_edges)

            # Delete nodes
            if selected_nodes:
                query = """
                MATCH (n)
                WHERE n.id_rc IN $node_ids
                DETACH DELETE n
                """
                print(f"Executing query: {query} with node_ids: {selected_nodes}")
                session.run(query, node_ids=selected_nodes)

        return jsonify({"success": True})
    except Exception as e:
        print(f"Error deleting selected nodes and edges: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route('/editor', methods=['GET', 'POST'])
def editor():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       

    if request.method == 'POST':
        content = request.form.get('content')
        print("Submitted Content:", content)
        # Save the content to a database or process it as needed
        return jsonify({"success": True, "content": content})
    return render_template('editor.html')


        
@app.route('/edit/<node_id>', methods=['GET', 'POST'])
def edit_node(node_id):
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       

    try:
        with driver.session() as session:
            query = """
            MATCH (n)
            WHERE n.id_rc = $node_id
            RETURN n.name_unique AS name_unique
            """
            result = session.run(query, node_id=node_id)
            record = result.single()

            if record and record["name_unique"]:
                name_unique = record["name_unique"]
                print(f"Node {node_id} already has name_unique: {name_unique}")
            else:
                name_unique = f"node_{node_id}_{uuid.uuid4().hex[:8]}"
                print(f"Generating name_unique for node {node_id}: {name_unique}")
                update_query = """
                MATCH (n)
                WHERE n.id_rc = $node_id
                SET n.name_unique = $name_unique
                RETURN n.name_unique AS name_unique
                """
                session.run(update_query, node_id=node_id, name_unique=name_unique)
                print(f"Updated node {node_id} with name_unique: {name_unique}")

        file_path = os.path.join(app.root_path, 'static', 'editor_files', f"{name_unique}.html")

        # ---------- POST: save content ----------
        if request.method == 'POST':
            # CKEditor data = fragment we want inside <body>
            content = request.form.get('content') or ""
            mathjax_script = """
            <script src="https://cdn.jsdelivr.net/npm/mathjax@2/MathJax.js?config=TeX-AMS_HTML"></script>
            """
            try:
                fragment = content  # just use it as-is

                full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name_unique}</title>
{mathjax_script}
<style>
/* minimal styling — adjust as needed */
body{{
    font-family:system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height:1.6;
    margin:1rem;
    max-width:100%;
    color:#111;
}}

/* Table defaults: collapse and readable padding */
table {{
    border-collapse: collapse;
    width: 100%;
}}


/* Apply a default solid border only when the cell does not declare a border-style inline.
   This avoids overriding user-chosen styles such as 'dotted' or 'dashed'. */
th:not([style*="dotted"]):not([style*="dashed"]):not([style*="double"]):not([style*="solid"]):not([style*="ridge"]):not([style*="groove"]):not([style*="inset"]):not([style*="outset"]),
td:not([style*="dotted"]):not([style*="dashed"]):not([style*="double"]):not([style*="solid"]):not([style*="ridge"]):not([style*="groove"]):not([style*="inset"]):not([style*="outset"]) {{
    border: 2px solid #000;
    padding: 6px;
    word-wrap: break-word;
    overflow-wrap: anywhere;
}}

/* If you prefer not to rely on inline styles, have CKEditor set 'border-style' or use classes so CSS can detect them. */

</style>
</head>
<body>
{fragment}
</body>
</html>"""

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(full_html)

                return jsonify({"success": True, "message": f"Content saved for {name_unique}"})
            except Exception as save_err:
                app.logger.exception("Failed saving editor content")
                return jsonify({"success": False, "error": str(save_err)}), 500

        # ---------- GET: load content for editing ----------
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                full_html = f.read()

            # Extract only what's inside <body>...</body> for the editor
            import re
            m = re.search(r'<body[^>]*>(.*)</body>', full_html,
                          flags=re.IGNORECASE | re.DOTALL)
            if m:
                content = m.group(1).strip()
            else:
                # fallback: if no <body>, just use whole file
                content = full_html
        else:
            content = "<p>Start editing...</p>"

        # CKEditor now gets only the fragment (no nested <html>, <head>, etc)
        return render_template('ckeditor_template.html',
                               content=content,
                               ckeditor_config={"extraPlugins": "mathjax"})
    except Exception as e:
        print(f"Error in edit_node: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/edit_v4/<node_id>', methods=['GET', 'POST'])
def edit_node_v4(node_id):
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    try:
        with driver.session() as session:
            # Fetch the node's name and unique identifier
            query = """
            MATCH (n)
            WHERE n.id_rc = $node_id
            RETURN n.name AS node_name, n.name_unique AS name_unique
            """
            result = session.run(query, node_id=node_id)
            record = result.single()

            if record:
                node_name = record["node_name"] or f"Node {node_id}"
                name_unique = record["name_unique"]
            else:
                return jsonify({"success": False, "error": "Node not found"}), 404

            if not name_unique:
                # Generate a unique value if `name_unique` doesn't exist
                name_unique = f"node_{node_id}_{uuid.uuid4().hex[:8]}"
                update_query = """
                MATCH (n)
                WHERE n.id_rc = $node_id
                SET n.name_unique = $name_unique
                RETURN n.name_unique AS name_unique
                """
                session.run(update_query, node_id=node_id, name_unique=name_unique)

        # Construct the file path using name_unique
        file_path = os.path.join(app.root_path, 'static', 'editor_files', f"{name_unique}.html")

        # Handle POST request to save content
        if request.method == 'POST':
            content = request.form.get('content')
            mathjax_script = """
            <script src="https://cdn.jsdelivr.net/npm/mathjax@2/MathJax.js?config=TeX-AMS_HTML"></script>
            """
            # Embed MathJax script in the saved content (cleaned stray characters)
            content_with_mathjax = f"{mathjax_script}\n{content}"
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_with_mathjax)
            return jsonify({"success": True, "message": f"Content saved for {name_unique}"})

        # Handle GET request to load content
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "<p>Start editing...</p>"  # Default content if the file doesn't exist

        # Example graph data (replace with actual data from Neo4j)
        graph_data = {
            "nodes": [{"id": 1, "label": "Node 1"}, {"id": 2, "label": "Node 2"}],
            "edges": [{"from": 1, "to": 2}]
        }

        return render_template(
            'ckeditor_v4.html',
            content=content,
            node_name=node_name,
            ckeditor_config={"extraPlugins": "mathjax"},
            graph_data=json.dumps(graph_data)  # Pass graph data as JSON
        )
    except Exception as e:
        print(f"Error in edit_node_v4: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# New endpoints to list and view images placed in app/static/images
@app.route('/list-images', methods=['GET'])
def list_images():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    """
    Return a JSON list of image filenames found in static/images and their absolute URLs.
    """
    images_dir = os.path.join(app.static_folder, 'images')
    if not os.path.isdir(images_dir):
        return jsonify({"images": [], "urls": []})
    files = [
        f for f in os.listdir(images_dir)
        if os.path.isfile(os.path.join(images_dir, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'))
    ]
    urls = [url_for('static', filename=f'images/{f}', _external=True) for f in files]
    return jsonify({"images": files, "urls": urls})

@app.route('/show-image/<path:filename>', methods=['GET'])
def show_image(filename):    
    """
    Simple viewer for an image in static/images.
    Validates that the filename exists in the images directory to avoid path traversal.
    """
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    images_dir = os.path.join(app.static_folder, 'images')
    safe_path = os.path.join(images_dir, os.path.basename(filename))
    if not os.path.isfile(safe_path):
        abort(404)
    img_url = url_for('static', filename=f'images/{os.path.basename(filename)}')
    html = f'''
    <!doctype html>
    <html>
      <head><meta charset="utf-8"><title>{os.path.basename(filename)}</title></head>
      <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h3>{os.path.basename(filename)}</h3>
        <img src="{img_url}" alt="{os.path.basename(filename)}" style="max-width:100%;height:auto;border:1px solid #ccc;padding:8px;">
        <p><a href="{img_url}" download>Download</a> • <a href="/list-images">List images (JSON)</a></p>
      </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/show-html/<node_id>', methods=['GET'])
def show_html(node_id):
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    try:
        # Fetch the unique name for the node
        with driver.session() as session:
            query = """
            MATCH (n)
            WHERE n.id_rc = $node_id
            RETURN n.name_unique AS name_unique
            """
            result = session.run(query, node_id=node_id)
            record = result.single()

            if not record or not record["name_unique"]:
                return "HTML file not found for the given node.", 404

            name_unique = record["name_unique"]

        # Construct the file path
        file_path = os.path.join(app.root_path, 'static', 'editor_files', f"{name_unique}.html")

        # Check if the file exists
        if not os.path.exists(file_path):
            return "HTML file not found.", 404

        # Serve the file
        return send_file(file_path)
    except Exception as e:
        print(f"Error in show_html: {e}")
        return "An error occurred while opening the HTML file.", 500

def convert_neo4j_id(obj):
    """
    Recursively convert Neo4j IDs (large integers) to strings and prefer id_rc if present.
    """
    if isinstance(obj, list):
        return [convert_neo4j_id(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_neo4j_id(value) for key, value in obj.items()}
    elif isinstance(obj, (Node, Relationship)):
        obj_dict = dict(obj)
        # prefer id_rc property if present, otherwise use internal id as string
        obj_dict["id"] = obj_dict.get("id_rc", str(obj.id))
        return obj_dict
    elif isinstance(obj, int) and obj > 9007199254740991:  # Check for large integers
        return str(obj)
    else:
        return obj

@app.route('/loadCustomGraph/<customLoadGraphName>', methods=['GET'])
def load_custom_graph(customLoadGraphName):
    """
    Load a custom graph based on the provided name, with project filtering.
    """
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]

    queryNodes = """
        MATCH (s:CustomGraph)-[r]-(t)
        WHERE s.name = $customLoadGraphName
        WITH t
        MATCH (origNode)
        WHERE t.original_id = origNode.id_rc
        MATCH (ntype:NodeType) WHERE ntype.name IN labels(origNode)
        RETURN origNode, t.x AS x, t.y AS y, ntype.size AS size, t
    """

    queryNodeType = """
        MATCH (s:NodeType)
        WHERE s.name = $NodeTypeName
        RETURN s
    """

    print("loadCustomGraph query:", queryNodes)

    try:
        with driver.session() as session:
            result = session.run(queryNodes, customLoadGraphName=customLoadGraphName)

            nodes = {}
            edges = []

            for record in result:
                origNode = record["origNode"]
                tNode = record["t"]

                # FILTER BY PROJECT for nodes
                origNodeProp = dict(origNode)
                print("origNodeProp: "+ origNodeProp.get("projectName") +" : project: "+ project)
                if project and origNodeProp.get("projectName") != project:
                    print(f"Skipping node: {origNodeProp.get('name')} (projectName: {origNodeProp.get('projectName')})")
                    continue

                origNode_name = origNodeProp.get("name", str(origNode.id))
                origNode_id = origNodeProp.get("id_rc", str(origNode.id))
                origNodeLabels = list(origNode.labels)

                resultNodeType = session.run(queryNodeType, NodeTypeName=origNodeLabels[0])
                recordNodeType = resultNodeType.single()
                print("recordNodeType:", recordNodeType)

                # Assuming `recordNodeType` is the Record object you provided
                node_data = recordNodeType["s"]  # Access the Node object from the Record
                node_properties = dict(node_data)  # Convert the Node object to a dictionary
                shape_value = node_properties.get("shape")  # Extract the value for the key 'shape'

                x = record["x"]
                y = record["y"]
                size = record["size"]
                full_name = origNode_name  # Extract name property
                short_name = full_name.split(".")[-1]  # Get last part after the last dot
                nodes[origNode_id] = {
                    "id": origNode_id,
                    "label": short_name,
                    "name": full_name,
                    "shape": shape_value,
                    "color": node_properties.get("color", "#97C2FC"),
                    "image": origNodeProp.get("image", ""),
                    "x": x,
                    "y": y,
                    "size": size,
                    "labels": origNodeLabels,  # Include all labels
                    "properties": convert_neo4j_id(origNode)  # Convert properties
                }
                print("Node added:", nodes[origNode_id])

                # Find relationships for this node
                rel_query = """
                    MATCH (n)-[r]->(m)
                    WHERE (n.id_rc = $node_id OR m.id_rc = $node_id)
                      AND NOT 'CustomGraph' IN labels(m)
                      AND NOT 'customGraphNode' IN labels(m)
                      AND NOT 'customGraphNodePosition' IN labels(m)
                      AND NOT 'CustomGraph' IN labels(n)
                      AND NOT 'customGraphNode' IN labels(n)
                      AND NOT 'customGraphNodePosition' IN labels(n)
                    RETURN n, r, m
                """
                rel_result = session.run(rel_query, node_id=origNode_id)
                for rel_record in rel_result:
                    n_node = rel_record["n"]
                    m_node = rel_record["m"]
                    relationship = rel_record["r"]

                    # FILTER BY PROJECT for relationships
                    n_props = dict(n_node)
                    m_props = dict(m_node)
                    if project:
                        n_proj = n_props.get("projectName")
                        m_proj = m_props.get("projectName")
                        if n_proj != project and m_proj != project:
                            print(f"Skipping relationship: {relationship} (projects: {n_proj}, {m_proj})")
                            continue

                    # Process relationship
                    rel_props = dict(relationship)
                    rel_id = rel_props.get("id_rc") or f"{relationship.start_node.id}-{relationship.end_node.id}-{relationship.type}"
                    start_props = dict(relationship.start_node)
                    end_props = dict(relationship.end_node)
                    edge = {
                        "id": rel_id,  # Unique edge ID (prefer id_rc)
                        "from": start_props.get("id_rc", str(relationship.start_node.id)),
                        "to": end_props.get("id_rc", str(relationship.end_node.id)),
                        "type": relationship.type,
                        "label": relationship.type  # Set the label to the relationship type
                    }

                    if edge not in edges:
                        edges.append(edge)

            print("Load graph completed")
            print("list(nodes.values()):", list(nodes.values()))
            return jsonify({"success": True, "nodes": list(nodes.values()), "edges": edges})

    except Exception as e:
        app.logger.exception("Error in loadCustomGraph")  # Logs file:line + stack
        return jsonify({"success": False, "error": str(e)}), 500

# helper: validate read-only Cypher
READ_ONLY_DISALLOWED = re.compile(
    r'\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL|LOAD\s+CSV|USING\s+PERIODIC\s+COMMIT|FOREACH|CREATE\s+CONSTRAINT|DROP\s+CONSTRAINT)\b',
    re.IGNORECASE
)
READ_ONLY_REQUIRED = re.compile(r'\b(MATCH|RETURN|OPTIONAL\s+MATCH|UNWIND|WITH|WHERE)\b', re.IGNORECASE)

def is_safe_read_query(cypher: str) -> bool:
    """
    Return True if query looks like a safe read-only Cypher query.
    - rejects queries containing DDL/DML keywords (CREATE, MERGE, DELETE, SET, CALL, LOAD CSV, etc.)
    - requires at least one read keyword (MATCH/RETURN/WHERE/UNWIND/etc.)
    This is a heuristic, not bulletproof.
    """
    if not cypher or READ_ONLY_DISALLOWED.search(cypher):
        return False
    return bool(READ_ONLY_REQUIRED.search(cypher))

@app.route("/openai-cypher", methods=["POST"])
def openai_cypher():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    """
    POST JSON:
      - For analysis/validation/rewrite of an existing Cypher:
        { "query": "<cypher>", "task": "explain|validate|rewrite" (optional),
          "execute": true|false (optional, default false) }

      - To generate Cypher from natural language:
        { "natural_language": "<describe what you want in plain English>",
          "task": "generate" (optional) ,
          "execute": true|false (optional, default false) }

    Behavior:
      - If 'execute' is true: validate query with is_safe_read_query() and run it against Neo4j, returning serialized rows.
      - If 'natural_language' is provided: the endpoint asks OpenAI to produce a Cypher query and returns the suggested query in 'suggested_cypher'.
      - Otherwise: forwards the provided Cypher to OpenAI for explanation/validation/rewrite and returns assistant text / suggested Cypher.
    """
    api_key = OPENAI_API_KEY
    if not api_key:
        return jsonify({"success": False, "error": "OPENAI_API_KEY not set"}), 500

    data = request.json or {}
    # accept either an explicit cypher 'query' or a natural language 'natural_language'
    cypher = data.get("query", "") or None
    natural_language = data.get("natural_language") or data.get("nl") or None
    task = data.get("task", "explain")
    execute = bool(data.get("execute", False))

    if not cypher and not natural_language:
        return jsonify({"success": False, "error": "Missing 'query' or 'natural_language'"}), 400

    # If client requested execution and supplied natural_language, we will first generate Cypher then validate before executing.
    # Build the prompt for OpenAI depending on input
    if natural_language and not cypher:
        # Request generation from natural language. Force strict output: only fenced cypher block or NO_CHANGE.
        prompt = (
            "You are a Neo4j Cypher generator. Given a user's plain-language request, produce a single safe, "
            "read-only Cypher query (use MATCH/RETURN/OPTIONAL MATCH/WITH/WHERE/UNWIND as needed). "
            "Do NOT include any commentary. Reply ONLY with a fenced code block labeled 'cypher' containing the query. "
            "If you cannot produce a safe read-only query, reply exactly: NO_CHANGE\n\n"
            f"User request:\n{natural_language}\n\n"
            "If the user asked for data that requires write/DDL operations or external calls, respond NO_CHANGE."
        )
    else:
        # We have an explicit Cypher to analyze/rewrite/explain
        prompt = (
            f"You are a Neo4j Cypher assistant. Task: {task}.\n"
            "Do not include any unrelated commentary. If you suggest a replacement Cypher, return it "
            "inside a fenced code block labeled 'cypher'. If you cannot suggest a safe read-only Cypher, reply NO_CHANGE.\n\n"
            f"Cypher:\n{cypher if cypher else ''}\n"
        )

    # If the client requests execution, validate first
    if execute:
        if not is_safe_read_query(cypher):
            return jsonify({"success": False, "error": "Query rejected by safety policy (only read queries allowed)."}), 400
        try:
            rows = []
            with driver.session() as session:
                result = session.run(cypher)
                for record in result:
                    row = {}
                    for k, v in record.items():
                        # reuse existing conversion helpers to serialize Nodes/Relationships/dates/ints
                        row[k] = convert_dates(convert_neo4j_id(v))
                    rows.append(row)
            return jsonify({"success": True, "executed": True, "rows": rows})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # Otherwise send to OpenAI for analysis (no DB execution)
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 2000
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30)

        # Handle billing / quota / rate-limit explicitly for clearer client messages
        if resp.status_code == 402:
            # Payment required / insufficient funds
            body = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {"text": resp.text}
            return jsonify({"success": False, "error": "Payment required: insufficient funds or billing issue", "detail": body}), 402

        if resp.status_code == 429:
            body = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else {"text": resp.text}
            retry_after = resp.headers.get("Retry-After")
            return jsonify({"success": False, "error": "Rate limited or quota exhausted", "retry_after": retry_after, "detail": body}), 429

        resp.raise_for_status()
        body = resp.json()
        content = (body.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
        content = _strip_fences(content)
        # Debug: print raw OpenAI content (trimmed)
        try:
            print("OpenAI raw content (trimmed 10000 chars):\n", content[:10000])
        except Exception:
            print("OpenAI raw content: <unprintable>")

        import re

        def extract_code_block(text: str) -> str | None:
            # 1) fenced code block, optionally labeled "cypher"
            m = re.search(r"```(?:\s*cypher\s*\n)?(.*?)```", text, re.S | re.I)
            if m:
                return m.group(1).strip()
            # 2) fallback: find a Cypher-looking line starting with MATCH
            m2 = re.search(r"(?i)(MATCH\s+[\s\S]*?)(?:$|\n{2,})", text)
            if m2:
                return m2.group(1).strip()
            return None

        # ensure assistant_text is defined (use the extracted/stripped content)
        assistant_text = content
        suggested_cypher = extract_code_block(assistant_text)
        print("suggested_cypher:", suggested_cypher)
        # return assistant text plus parsed cypher (no DB execution here)
        return jsonify({
            "success": True,
            "executed": False,
            "response": assistant_text,
            "suggested_cypher": suggested_cypher,
            "raw": body
        })
    except requests.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 500

def _extract_code_block(text: str) -> str | None:
    import re
    # try fenced code blocks first (allow js/javascript label)
    m = re.search(r"```(?:\s*(?:javascript|js)\s*\n)?(.*?)```", text, re.S | re.I)
    if m:
        return m.group(1).strip()
    # fallback: a cypher-like / code-looking block
    m2 = re.search(r"(?:(?:var|const|let)\s+[\w]+|function\s+[\w]+\s*\(|\{[\s\S]*\})", text)
    if m2:
        return m2.group(0).strip()
    return None



from html import unescape

def ensure_name_unique(session, node_id: str) -> str:
    """Ensure n.name_unique is set and return it."""
    q = """
    MATCH (n) WHERE n.id_rc = $node_id
    RETURN n.name_unique AS name_unique
    """
    rec = session.run(q, node_id=node_id).single()
    if rec and rec["name_unique"]:
        return rec["name_unique"]
    name_unique = f"node_{node_id}_{uuid.uuid4().hex[:8]}"
    session.run("""
        MATCH (n) WHERE n.id_rc = $node_id
        SET n.name_unique = $name_unique
    """, node_id=node_id, name_unique=name_unique)
    return name_unique

def editor_file_path(name_unique: str) -> str:
    return os.path.join(app.root_path, 'static', 'editor_files', f"{name_unique}.html")

@app.get("/get-html/<node_id>")
def get_html(node_id):
        # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       
    try:
        with driver.session() as s:
            name_unique = ensure_name_unique(s, node_id)
        path = editor_file_path(name_unique)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "<!-- New document -->\n"
        return jsonify({"success": True, "name_unique": name_unique, "content": content})
    except Exception as e:
        app.logger.exception("get_html failed")
        return jsonify({"success": False, "error": str(e)}), 500

@app.post("/save-html/<node_id>")
def save_html(node_id):
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    try:
        with driver.session() as s:
            name_unique = ensure_name_unique(s, node_id)
        path = editor_file_path(name_unique)

        content = request.form.get("content") or ""
        # If CKEditor escaped HTML elsewhere, make sure we store real HTML
        if "&lt;html" in content or "&lt;!DOCTYPE" in content:
            content = unescape(content)

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({"success": True, "message": f"Saved {name_unique}.html"})
    except Exception as e:
        app.logger.exception("save_html failed")
        return jsonify({"success": False, "error": str(e)}), 500

# Windows curl examples for calling the /openai-generate endpoint:
# 1) cmd.exe (use curl.exe shipped with Windows 10+):
#    curl.exe -X POST "http://localhost:5000/openai-generate" -H "Content-Type: application/json" -d "{\"prompt\":\"Hello, list 3 nodes\",\"model\":\"gpt-4o-mini\",\"temperature\":0.2,\"max_tokens\":200}"
#
# 2) PowerShell (call curl.exe to avoid the Invoke-WebRequest alias):
#    curl.exe -X POST "http://localhost:5000/openai-generate" -H "Content-Type: application/json" --data-raw '{"prompt":"Hello, list 3 nodes","model":"gpt-4o-mini"}'
#
# Notes:
# - Replace http://localhost:5000 with your server host/port or use the full URL.
# - Adjust the JSON fields (prompt, model, temperature, max_tokens) as needed.
# - If using PowerShell native commands, you can also use:
#     Invoke-RestMethod -Method Post -Uri 'http://localhost:5000/openai-generate' -ContentType 'application/json' -Body '{"prompt":"...","model":"gpt-4o-mini"}'

@app.route("/openai-generate", methods=["POST"])
def openai_generate():    
    """
    Generate code with OpenAI.

    Request JSON:
      {
        "prompt": "...",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 2500,
        "mode": "bundle" | "split"   # default: "bundle"
      }

    Response JSON (bundle):
      { success, html, code, raw }

    Response JSON (split):
      { success, html, css, js, code, raw }
    """
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    if not OPENAI_API_KEY:
        return jsonify({"success": False, "error": "OPENAI_API_KEY not set"}), 500

    data = request.json or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"success": False, "error": "Missing 'prompt'"}), 400

    model = data.get("model", "gpt-4o-mini")
    mode = (data.get("mode") or "bundle").lower()
    try:
        temperature = float(data.get("temperature", 0.2))
    except Exception:
        temperature = 0.2
    try:
        max_tokens = int(data.get("max_tokens", 2500))
    except Exception:
        max_tokens = 2500

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    if mode == "split":
        # Ask for structured JSON with separate html/css/js
        messages = [
            {"role": "system", "content": SYSTEM_SPLIT},
            {"role": "user", "content": f"Create code for: {prompt}\nReturn ONLY the JSON with keys html, css, js."}
        ]
    else:
        # Self-contained HTML doc with inline <style>/<script>
        messages = [
            {"role": "system", "content": SYSTEM_BUNDLE},
            {"role": "user", "content": f" {prompt}"}
        ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        r = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=45)

        if r.status_code in (402, 429):
            body = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {"text": r.text}
            return jsonify({"success": False, "error": "OpenAI error", "detail": body}), r.status_code

        r.raise_for_status()
        body = r.json()
        content = (body.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
        content = _strip_fences(content)
        # Debug: print raw OpenAI content (trimmed)
        try:
            print("OpenAI raw content (trimmed 10000 chars):\n", content[:10000])
        except Exception:
            print("OpenAI raw content: <unprintable>")

        if mode == "split":
            # Try to parse strict JSON first
            html = css = js = ""
            parsed = None
            try:
                parsed = json.loads(content)
            except Exception:
                # fallback: try to extract JSON block if the model wrapped it in prose
                m = re.search(r"\{(?:.|\n)*\}", content)
                if m:
                    try:
                        parsed = json.loads(m.group(0))
                    except Exception:
                        parsed = None
            if isinstance(parsed, dict):
                html = (parsed.get("html") or "").strip()
                css  = (parsed.get("css")  or "").strip()
                js   = (parsed.get("js")   or "").strip()
            else:
                # last resort: try to scrape language fences
                html_match = re.search(r"```html\s+(.*?)```", content, re.S | re.I)
                css_match  = re.search(r"```css\s+(.*?)```", content, re.S | re.I)
                js_match   = re.search(r"```(js|javascript)\s+(.*?)```", content, re.S | re.I)
                if html_match: html = html_match.group(1).strip()
                if css_match:  css  = css_match.group(1).strip()
                if js_match:   js   = (js_match.group(2) if js_match.lastindex == 2 else js_match.group(1)).strip()

            # Make sure html does not carry <style>/<script>; if it does, strip them
            if "<style" in html.lower():
                html = re.sub(r"(?is)<style[^>]*>.*?</style>", "", html)
            if "<script" in html.lower():
                html = re.sub(r"(?is)<script[^>]*>.*?</script>", "", html)

            # Provide a handy bundled doc too (for preview)

            bundled = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AI</title>
<style>
{css}
</style>
</head>
<body>
{html}
<script>
{js}
</script>
</body>
</html>""".strip()
            # Debug: print bundled preview (trimmed)
            try:
                print("Bundled preview HTML (trimmed 10000 chars):\n", bundled[:10000])
            except Exception:
                print("Bundled preview HTML: <unprintable>")

            return jsonify({
                "success": True,
                "html": html,
                "css": css,
                "js": js,
                "code": bundled,   # keep legacy 'code' as a ready-to-render doc
                "raw": body
            })

        # mode == "bundle"
        full_html = _extract_full_html(content)
        # Debug: print full extracted HTML (trimmed)
        try:
            print("Full extracted HTML (trimmed 10000 chars):\n", full_html[:10000])
        except Exception:
            print("Full extracted HTML: <unprintable>")
        return jsonify({
            "success": True,
            "html": content,   # complete document
            "code": content,   # legacy field
            "raw": body
        })

    
    

    except requests.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/assessment")
def assessment_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    return render_template("assessment.html")

@app.route('/ollama_ui', methods=['GET'])
def ollama_ui_page():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]           
    return render_template('ollama_ui.html')    

@app.route('/api/ollama/ask', methods=['POST'])
def ask_ollama():
        # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       
    data = request.json
    question = data.get('question', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        # Forward the question to Ollama API
        OLLAMA_API_BASE = config.get("OLLAMA", "BASE", fallback=None)
        if not OLLAMA_API_BASE:
            return jsonify({'error': 'OLLAMA_API_BASE is not configured'}), 500
        response = requests.post(f"{OLLAMA_API_BASE}/ask", json={'question': question})
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/proxy/ollama/ask', methods=['POST'])
def proxy_ollama_ask():
        # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       
    data = request.json
    question = data.get('question', '')

    if not question:
        return jsonify({'error': 'No question provided'}), 400

    try:
        OLLAMA_API_BASE = config.get("OLLAMA", "BASE", fallback=None)
        MODEL = config.get("OLLAMA", "MODEL", fallback="Default model not set")
        
        # Log the model being used
        app.logger.info(f"Using Ollama model: {MODEL}")

        # Forward the request to the correct endpoint
        response = requests.post(f"{OLLAMA_API_BASE}/ask", json={'question': question})
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        app.logger.exception("Error while forwarding request to Ollama API")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ollama/model', methods=['GET'])
def get_ollama_model():
    model = config.get("OLLAMA", "MODEL", fallback="Default model not set")
    return jsonify({'model': model})

@app.route('/favicon.ico')
def favicon():
    return '', 204  # Empty response, no error

from flask import render_template_string


@app.route('/ask-question', methods=['POST'])
def ask_question():
    """
    API endpoint to forward user questions along with context to OpenAI API.
    Expects JSON: { "question": "...", "context": "..." }
    """
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       

    data = request.json or {}
    question = data.get("question", "").strip()
    context = data.get("context", "").strip()

    if not question or not context:
        return jsonify({"success": False, "error": "Missing 'question' or 'context'"}), 400

    api_key = OPENAI_API_KEY
    if not api_key:
        app.logger.error("OPENAI_API_KEY is not set in environment variables")
        return jsonify({"success": False, "error": "OPENAI_API_KEY not set"}), 500

    prompt = f"Context:\n{context}\n\nQuestion:\n{question}"
    payload = {
        "model": "gpt-4.1-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 500
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        answer = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return jsonify({"success": True, "answer": answer})
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            app.logger.error("Unauthorized: Check your OpenAI API key")
            return jsonify({"success": False, "error": "Unauthorized: Invalid API key"}), 401
        app.logger.exception("HTTP error occurred while calling OpenAI API")
        return jsonify({"success": False, "error": str(e)}), 500
    except requests.RequestException as e:
        app.logger.exception("Request error occurred while calling OpenAI API")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/summary-popup', methods=['GET'])
def summary_popup():
    """
    Render a popup template for asking questions about a summary.
    Use the context provided in the query string.
    """
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       

    context = request.args.get('context')
    if not context:
        app.logger.error("Missing or invalid 'context' parameter in request")
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Error</title>
        </head>
        <body>
            <h3>Error: Missing context</h3>
            <p>Please provide valid context in the URL.</p>
        </body>
        </html>
        '''), 400

    app.logger.info(f"Received context: {context}")
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ask Question</title>
        <script>
            async function sendQuestion() {
                const question = document.getElementById('question').value;
                const context = document.getElementById('context').value;
                const response = await fetch('/ask-question', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question, context })
                });
                const result = await response.json();
                if (result.success) {
                    document.getElementById('answer').innerText = result.answer;
                } else {
                    document.getElementById('answer').innerText = "Error: " + result.error;
                }
            }
        </script>
    </head>
    <body>
        <h3>Ask a Question</h3>
        <textarea id="context" style="display:none;">{{ context }}</textarea>
        <label for="question">Your Question:</label><br>
        <textarea id="question" rows="4" cols="50"></textarea><br>
        <button onclick="sendQuestion()">Submit</button>
        <h4>Answer:</h4>
        <div id="answer" style="white-space: pre-wrap; border: 1px solid #ccc; padding: 10px;"></div>
    </body>
    </html>
    ''', context=context)

def validate_jwt():
    token = request.cookies.get('access_token')
    if not token:
        return None, jsonify({"error": "Unauthorized: No token provided"}), 401

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        uid = payload.get("sub")
        project = payload.get("project")
        if not uid or not project:
            return None, jsonify({"error": "Unauthorized: Invalid token"}), 401
        return {"uid": uid, "project": project}, None, None
    except jwt.PyJWTError as e:  # Updated exception
        print(f"JWT Error: {e}")
        return None, jsonify({"error": "Unauthorized: Invalid token"}), 401

if __name__ == '__main__':
    app.run(host='::', port=5000, debug=True)


#   sudo lsof -i :5001
#   sudo kill -9 <PID>
