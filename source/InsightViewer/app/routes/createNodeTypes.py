# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

# createNodeTypes.py
import os
import jwt
import neo4j
import requests 
from flask import Blueprint, jsonify, request
from neo4j import GraphDatabase
import configparser
import sys
import uuid
import re  # add near other imports

# JWT configuration
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

# Create a Flask Blueprint with a URL prefix to avoid route conflicts
nodes_bp = Blueprint("createNodeTypes", __name__, url_prefix="/nodes")

# Do NOT read config or create a driver at import-time.
# Provide functions the application can call to initialize the driver.
driver = None

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

def init_driver(d):
    """Attach an already-created neo4j driver instance."""
    global driver
    driver = d

def init_driver_from_config(base_dir=None, config_path=None):
    """Optional helper to create and attach a driver from a config file.
    base_dir: project root to look for config_private.ini / config.ini if config_path not provided.
    """
    global driver
    cfg = configparser.ConfigParser()
    if config_path:
        files_read = cfg.read(config_path)
    else:
        base = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        private_cfg = os.path.join(base, 'config_private.ini')
        default_cfg = os.path.join(base, 'config.ini')
        cfg_path = private_cfg if os.path.exists(private_cfg) else default_cfg
        files_read = cfg.read(cfg_path)

    if "NEO4J" not in cfg:
        raise RuntimeError("NEO4J section missing in config when initializing driver")
    URI = cfg["NEO4J"]["URI"]
    USERNAME = cfg["NEO4J"]["USERNAME"]
    PASSWORD = cfg["NEO4J"]["PASSWORD"]
    driver = GraphDatabase.driver(URI, auth=(USERNAME, PASSWORD))
    return driver

def _ensure_driver():
    if driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver(driver) in app startup.")

# Function to create NodeType nodes
def create_node_types():
    _ensure_driver()
    query = """
    CALL db.labels() YIELD label
    MERGE (nt:NodeType {name: label})
    RETURN nt.name;
    """
    with driver.session() as session:
        result = session.run(query)
        node_types = [record["nt.name"] for record in result]
    
    print("Created NodeType nodes:", node_types)

@nodes_bp.route("/update-node-properties", methods=["POST"])
def update_node_properties():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    _ensure_driver()
    print("update_node_properties")
    data = request.json
    node_id = data.get("node_id")
    properties = data.get("properties")

    if not node_id or not properties:
        return jsonify({"success": False, "error": "Invalid input."}), 400

    print("20 update_node_properties")
    try:
        query = """
        MATCH (t)
        WHERE t.id_rc = $node_id
        SET t += $properties
        RETURN t
        """
        with driver.session() as session:
            print("30 update_node_properties")
            print(query)
            print("node_id " + str(node_id))
            print("properties:" + str(properties))
            session.run(query, node_id=str(node_id), properties=properties)
            print("40 update_node_properties")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500    
    
@nodes_bp.route("/get_node_types", methods=["GET"])
def get_node_types():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    _ensure_driver()

    # Prefer query string, then JSON body (silent)
    data = request.get_json(silent=True) or {}
    projectName = request.args.get("projectName") or data.get("projectName") or None
    createdBy = request.args.get("createdBy") or data.get("createdBy") or None

    # Build query with optional filters
    base = "MATCH (t:NodeType)"
    conditions = []
    params = {}
    if projectName:
        conditions.append("t.projectName = $projectName OR $projectName = 'ALL'")
        params["projectName"] = projectName
    if createdBy:
        conditions.append("t.createdBy = $createdBy")
        params["createdBy"] = createdBy

    query = base
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " RETURN t.name AS name, t.shape AS shape, t.color AS color"

    print("get_node_types query:", query)
    print("get_node_types params:", params)

    with driver.session() as session:
        result = session.run(query, **params) if params else session.run(query)
        node_types = [{"name": record["name"], "shape": record["shape"], "color": record["color"]} for record in result]

    return jsonify(node_types)

#windows curl for testing
# curl -X POST -H "Content-Type: application/json" -d "{\"nodeType\": \"Person\"}" http://localhost:5000/get_node_type_visuals  

#if 

@nodes_bp.route("/get_node_type_visuals", methods=["POST"])
def get_node_type_visuals():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    _ensure_driver()
    try:
        data = request.json
        print("Request data:", data)

        node_type = data.get("nodeType")
        if not node_type:
            return jsonify({"success": False, "error": "Missing 'nodeType' in request"}), 400

        # Query to fetch NodeType properties
        query = """
        MATCH (t:NodeType {name: $nodeType})
        RETURN t
        """        
        
        with driver.session() as session:
            # print query with parameters
            print("Query:", query)
            print("Running query with parameters:", {"nodeType": node_type})
            
            result = session.run(query, nodeType=node_type)
            record = result.single()
            if not record:
                return jsonify({
                    "success": True
                })
                #return jsonify({"success": False, "error": f"NodeType '{node_type}' not found"}), 404

            node_type_properties = dict(record["t"])  # Extract all properties of the NodeType node
            print("NodeType properties before filtering:", node_type_properties)

            # Exclude specific properties
            excluded_keys = {"shape", "color", "size"}
            filtered_properties = {k: v for k, v in node_type_properties.items() if k not in excluded_keys}
            print("Filtered NodeType properties:", filtered_properties)

            # Return the filtered properties, including shape and color separately
            return jsonify({
                "success": True,
                "name": node_type_properties.get("name"),
                "shape": node_type_properties.get("shape"),
                "color": node_type_properties.get("color"),
                "size": node_type_properties.get("size"),
                "properties": filtered_properties  # Include only filtered properties
            })
    except Exception as e:
        print(f"Error in get_node_type_visuals: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@nodes_bp.route("/test_post", methods=["POST"])
def test_post():
    return jsonify({"success": True, "message": "POST request successful"})


@nodes_bp.route("/add_node_type", methods=["POST"])
def add_node_type():
  # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    print("add_node_type start")
    _ensure_driver()
    data = request.json or {}
    print("add_node_type request.json:", data)

    nodeType = data.get("pNodeType", "NodeType")
    name = data.get("name")
    shape = data.get("shape", "ellipse")
    color = data.get("color", "#000000")
    size = data.get("size", 25)
    properties = data.get("properties", {}) or {}

    projectName = data.get("projectName")
    createdBy = data.get("createdBy")

    if not name:
        return jsonify({"success": False, "error": "Node type name is required"}), 400

    id_rc = str(uuid.uuid4())

    query = """
    MERGE (t:<<nodeType>> {name: $name})
    // merge then apply arbitrary properties map
    SET t += $properties
    WITH t, $createdBy AS _createdBy
    SET t.shape = $shape,
        t.color = $color,
        t.size = $size,
        t.projectName = coalesce(t.projectName, $projectName),
        t.id_rc = coalesce(t.id_rc, $id_rc)
    // only set createdBy when provided (avoid overwriting with null)
    FOREACH (_ IN CASE WHEN _createdBy IS NOT NULL THEN [1] ELSE [] END |
      SET t.createdBy = _createdBy
    )
    RETURN t.name AS name,
           t.shape AS shape,
           t.color AS color,
           t.size AS size,
           t.id_rc AS id_rc,
           t.projectName AS projectName,
           t.createdBy AS createdBy
    """
    query = query.replace("<<nodeType>>", nodeType)

    try:
        with driver.session() as session:
            result = session.run(
                query,
                name=name,
                shape=shape,
                color=color,
                size=size,
                properties=properties,
                id_rc=id_rc,
                projectName=projectName,
                createdBy=createdBy
            )
            record = result.single()
            print("add_node_type record:", record)
        print("Query add_node_type:", query)
        print("Parameters add_node_type:", {
            "name": name, "shape": shape, "color": color, "size": size,
            "properties": properties, "id_rc": id_rc,
            "projectName": projectName, "createdBy": createdBy
        })
        if record:
            return jsonify({"success": True, "node_type": {
                "name": record["name"],
                "shape": record["shape"],
                "color": record["color"],
                "size": record["size"],
                "id_rc": record["id_rc"],
                "projectName": record.get("projectName"),
                "createdBy": record.get("createdBy")
            }})
        else:
            return jsonify({"success": False, "error": "No record returned"}), 500
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return jsonify({"success": False, "error": str(e)}), 500

@nodes_bp.route("/test", methods=["GET"])
def test():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       
    return "ok"

@nodes_bp.route("/get_node_type_shape", methods=["POST"])
def get_node_type_shape():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]    
    project = user_data["project"]       

    _ensure_driver()
    """
    Fetch the shape and type (label) of a node based on its type (label).
    """
    data = request.json
    node_typeP = data.get("node_type")
    
    # Validate input
    if not node_typeP:
        return jsonify({"success": False, "error": "Node type is required"}), 400

    # Query to fetch the shape and type for the given node type
    query = """
    MATCH (n {name: $node_type})
    RETURN n.shape AS shape, head(labels(n)) AS nodeType
    """
    try:
        with driver.session() as session:
            result = session.run(query, node_type=node_typeP)
            record = result.single()

            # If a shape is found, return it along with the node type
            if record:
                return jsonify({
                    "success": True,
                    "shape": record["shape"] if record["shape"] else "ellipse",  # Default to "ellipse" if shape is None
                    "nodeType": record["nodeType"] if record["nodeType"] else "Unknown"  # Return the first label as node type
                })

            # If no record is found, return a default shape and "Unknown" as the node type
            return jsonify({
                "success": True,
                "shape": "star",  # Default shape
                "nodeType": "Unknown"  # Default to "Unknown" if no label is found
            })
    except Exception as e:
        # Handle unexpected errors
        print(f"Error in get_node_type_shape: {e}")
        return jsonify({"success": False, "error": "An error occurred while fetching the node type shape"}), 500
    

@nodes_bp.route("/create-custom-graph", methods=["POST"])
def create_custom_graph():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       

    _ensure_driver()
    """
    Create a new manual graph in Neo4j.
    """
    data = request.json
    graph_name = data.get("name")

    if not graph_name:
        return jsonify({"success": False, "error": "Graph name is required"}), 400

    id_rc = str(uuid.uuid4())
    query = """
    MERGE (g:CustomGraph {name: $name})
    set g.id_rc = coalesce(g.id_rc, $id_rc)
    RETURN id(g) AS graph_id
    """
    try:
        with driver.session() as session:
            result = session.run(query, name=graph_name, id_rc=id_rc)
            graph_id = result.single()["graph_id"]
            return jsonify({"success": True, "graph_id": graph_id})
    except Exception as e:
        print(f"Error creating manual graph: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@nodes_bp.route("/connect-custom-graph-position", methods=["POST"])
def connect_custom_graph_position():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]       
    _ensure_driver()

    """
    Connect nodes to the CustomGraph node and create customGraphNodePosition nodes.
    """
    data = request.json
    custom_graph_name = data.get("customGraphName")
    nodes = data.get("nodes")  # List of nodes with position and shape information    
    
    # Debugging logs
    print("Received customGraphName:", custom_graph_name)
    print("Received nodes:", nodes)    

    if not custom_graph_name or not nodes:
        return jsonify({"success": False, "error": "Missing required parameters"}), 400

    id_rc = str(uuid.uuid4())
    query = """
                MATCH (g:CustomGraph {name: $customGraphName})
                UNWIND $nodeDataCgPos AS nodeDataCgPos
                WITH nodeDataCgPos,
                    'cg_' + nodeDataCgPos.properties.name + '.' + $customGraphName AS customName,
                    $id_rc AS idRc
                MERGE (newNodeCg:CustomGraphNode { name: customName })
                ON CREATE SET
                    newNodeCg.id_rc       = idRc,
                    newNodeCg.original_id = nodeDataCgPos.vis_id,
                    newNodeCg.x           = nodeDataCgPos.x,
                    newNodeCg.y           = nodeDataCgPos.y,
                    newNodeCg.shape       = nodeDataCgPos.shape
                ON MATCH SET
                    newNodeCg.x           = nodeDataCgPos.x,
                    newNodeCg.y           = nodeDataCgPos.y,
                    newNodeCg.shape       = nodeDataCgPos.shape
                RETURN nodeDataCgPos, customName, newNodeCg;
            """

    print ("customGraphNodePosition query: " + query)   

    try:
        with driver.session() as session:
            result=session.run(query, customGraphName=custom_graph_name, nodeDataCgPos=nodes, id_rc=id_rc)

            for record in result:
                # print properties name
                node_data = record["nodeDataCgPos"]
                node_data_properties = node_data["properties"]

                #there are nodes in record make a relationship to node $customGraphName
                new_node = record["newNodeCg"]
                print("new_node: " + str(new_node))
                # connect this node to $customGraphName
                queryCg="""
                    match(s:CustomGraph {name:$customGraphName})                     
                    match (t:CustomGraphNode {name:$CgName})                     
                    with distinct s,t
                    merge(s)-[r:isPartOf]-(t) return s,r,t
                """                        
                resultCg=session.run(queryCg, customGraphName=custom_graph_name, CgName=str(new_node["name"]))

        return jsonify({"success": True, "message": "Nodes connected and positions saved successfully"})
    except Exception as e:
        print(f"Error in connect_custom_graph_position: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@nodes_bp.route("/get_nodes_by_type", methods=["POST"])
def get_nodes_by_type():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    _ensure_driver()
    """
    Return nodes that have the specified label (node type).
    Request JSON: { "nodeType": "<LabelName>" }
    Response: { "success": True, "nodes": [ { "id": <neo4j id>, "label": "<name>", "properties": {...}, "labels": [...] }, ... ] }
    """
    try:
        data = request.json or {}
        node_type = data.get("nodeType")
        if not node_type:
            return jsonify({"success": False, "error": "Missing 'nodeType' in request"}), 400

        query = """
        MATCH (n)
        WHERE $nodeType IN labels(n)
        RETURN id(n) AS id, n.name AS name, properties(n) AS properties, labels(n) AS labels
        LIMIT 1000
        """
        with driver.session() as session:
            result = session.run(query, nodeType=node_type)
            nodes_list = []
            for record in result:
                rec_props = record["properties"] if record["properties"] is not None else {}
                nodes_list.append({
                    "id": record["id"],
                    "label": record["name"] if record["name"] is not None else f"{node_type}_{record['id']}",
                    "properties": dict(rec_props),
                    "labels": record["labels"] if record["labels"] is not None else []
                })
        return jsonify({"success": True, "nodes": nodes_list})
    except Exception as e:
        print(f"Error in get_nodes_by_type: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@nodes_bp.route("/remove-node-custom-graph", methods=["POST"])
def remove_node_custom_graph():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   

    _ensure_driver()
    """
    Remove references so a node no longer appears in custom graph.
    Accepts JSON: { "node_id": "<neo4j_internal_id_or_id_rc_or_id_property>" }
    """
    try:
        data = request.json or {}
        node_id = data.get("node_id")
        if not node_id:
            return jsonify({"success": False, "error": "Missing 'node_id' in request"}), 400

        # Determine if node_id looks like an integer (neo4j internal id)
        if re.fullmatch(r"\d+", str(node_id)):
            # Match by internal id
            id_int = int(node_id)
            query = """
            MATCH (n)
            WHERE id(n) = $id_int
            // remove all relationships from/to the node (so it's not attached to CustomGraph)
            OPTIONAL MATCH (n)-[r]-()
            DELETE r
            // remove customGraphNode label if present
            REMOVE n:customGraphNode
            WITH n
            // delete associated position node(s) if present
            OPTIONAL MATCH (p:customGraphNodePosition {id: n.id})
            DETACH DELETE p
            RETURN count(n) AS removed
            """
            params = {"id_int": id_int}
        else:
            # Match by id_rc or id property
            query = """
            MATCH (n)
            WHERE n.id_rc = $node_id OR n.id = $node_id
            OPTIONAL MATCH (n)-[r]-()
            DELETE r
            REMOVE n:customGraphNode
            WITH n
            OPTIONAL MATCH (p:customGraphNodePosition {id: n.id})
            DETACH DELETE p
            RETURN count(n) AS removed
            """
            params = {"node_id": str(node_id)}

        with driver.session() as session:
            result = session.run(query, **params)
            rec = result.single()
            removed = rec["removed"] if rec and "removed" in rec else 0

        return jsonify({"success": True, "removed_count": removed})
    except Exception as e:
        print(f"Error in remove_node_custom_graph: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def get_node_type_properties(node_type):
    _ensure_driver()
    """Return properties for a given node type as a Flask JSON response."""
    if not node_type:
        return jsonify({"success": False, "error": "node_type is required"}), 400

    query = "MATCH (n:NodeType) WHERE n.name=$node_type RETURN n LIMIT 1"
    try:
        with driver.session() as session:
            result = session.run(query, node_type=node_type)
            record = result.single()
    except Exception as e:
        print(f"Error querying node type properties: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    if not record:
        return jsonify({"success": False, "error": f"NodeType '{node_type}' not found"}), 404

    node = record.get("n")
    properties = dict(node) if node is not None else {}

    return jsonify({"success": True, "node_type": node_type, "properties": properties})

# Add a POST endpoint to fetch node type properties by JSON payload
@nodes_bp.route("/get_node_type_property", methods=["POST"])
def get_node_type_property():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   


    _ensure_driver()
    """
    POST endpoint: accepts JSON body with node_type / nodeType / name and returns node type properties.
    Example body: { "nodeType": "Person" }
    """
    try:
        data = request.json or {}
        node_type = data.get("node_type") or data.get("nodeType") or data.get("name")
        if not node_type:
            return jsonify({"success": False, "error": "Missing 'node_type' in request"}), 400
        return get_node_type_properties(node_type)
    except Exception as e:
        print(f"Error in get_node_type_property: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# Example usage of get_node_type_properties

@nodes_bp.route("/node_type_properties/<node_type>", methods=["GET"])
def node_type_properties(node_type):
    return get_node_type_properties(node_type)
    

@nodes_bp.route("/create_name_indexes", methods=["GET","POST"])
def create_name_indexes():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   


    _ensure_driver()
    """
    Create name indexes for a given label (if provided) or for all labels in the DB.
    Accepts node_type via JSON, form data or query string. Uses request.get_json(silent=True)
    to avoid 'Unsupported Media Type' warnings when Content-Type is not application/json.
    Returns a list of labels and node counts for which an index was created (or ensured).
    """
    # Try JSON silently (no warning), then fall back to form/query parameters
    data_json = request.get_json(silent=True) or {}
    node_type = (
        data_json.get("node_type")
        or data_json.get("nodeType")
        or request.values.get("node_type")
        or request.values.get("nodeType")
        or request.args.get("node_type")
        or request.args.get("nodeType")
    )

    try:
        # Determine labels to operate on
        if node_type:
            labels = [node_type]
        else:
            # fetch all labels from the DB
            with driver.session() as session:
                result = session.run("CALL db.labels() YIELD label RETURN label")
                labels = [record["label"] for record in result]

        indexes_info = []
        # Create index for each label and collect node counts
        with driver.session() as session:
            for label in labels:
                if not label:
                    continue
                # Create only a uniqueness constraint on n.name.
                # Try modern REQUIRE form first, fall back to older ASSERT form if necessary.
                try:
                    session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.name IS UNIQUE")
                    print("Created constraint using REQUIRE syntax")
                except Exception as e_req:
                    try:
                        # Older Neo4j versions (3.x) use ASSERT syntax.
                        session.run(f"CREATE CONSTRAINT ON (n:`{label}`) ASSERT n.name IS UNIQUE")
                        print("Created constraint using ASSERT syntax")
                    except Exception as e_assert:
                        # Log and continue; constraint creation failed or already exists in incompatible form.
                        print(f"Failed to create constraint for label '{label}': {e_req} / {e_assert}")
 
                # Get count of nodes with this label
                count_query = f"MATCH (n:`{label}`) RETURN count(n) AS node_count"
                res = session.run(count_query)
                rec = res.single()
                node_count = rec["node_count"] if rec and "node_count" in rec else 0

                indexes_info.append({"label": label, "node_count": node_count})

        return jsonify({"success": True, "indexes": indexes_info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

#need a roudte /getCustomGraps which will return a custom graph based on this cypher query match(s:CustomGraph) order by s.name return s
@nodes_bp.route("/getCustomGraphs", methods=["GET"])
def get_custom_graphs():
    # Validate JWT and extract user data
    user_data, error_response, status_code = validate_jwt()
    if error_response:
        return error_response, status_code

    # Extract user data from JWT
    uid = user_data["uid"]
    project = user_data["project"]   


    _ensure_driver()
    """Fetch custom graphs from Neo4j."""
    query = "MATCH (s:CustomGraph) ORDER BY s.name RETURN s"
    with driver.session() as session:
        result = session.run(query)
        graphs = []
        for record in result:
            graph_node = record["s"]
            graph_props = dict(graph_node) if graph_node is not None else {}
            graphs.append(graph_props)
    return jsonify(graphs)        


# Run script
if __name__ == "__main__":
    create_node_types()
    driver.close()
