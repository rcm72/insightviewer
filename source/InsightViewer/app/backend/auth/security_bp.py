import configparser
from flask import Blueprint, request, jsonify, make_response
from jose import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import os, time, secrets
from neo4j import GraphDatabase  # Import the Neo4j driver

# Initialize Blueprint
security_bp = Blueprint("security", __name__)
# Password hasher
ph = PasswordHasher()

# Initialize configparser
cfg = configparser.ConfigParser()

# Define the path to config.ini
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../config.ini'))

# Debugging: Print the path being used
print(f"Loading configuration from: {config_path}")

# Load the config.ini file
cfg.read(config_path)

# Debugging: Print loaded sections
print("Loaded sections:", cfg.sections())

# Ensure the NEO4J section exists
if "NEO4J" not in cfg:
    raise RuntimeError("Missing 'NEO4J' section in the configuration file")

# Access the NEO4J configuration
NEO4J_URI = cfg["NEO4J"]["URI"]
NEO4J_USER = cfg["NEO4J"]["USERNAME"]
NEO4J_PASSWORD = cfg["NEO4J"]["PASSWORD"]

# Initialize Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
ph = PasswordHasher()

# JWT configuration
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
EXPIRE_SECONDS = 3600

COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.environ.get("COOKIE_SAMESITE", "Lax")

# Helper functions
def verify_password(password: str, password_hash: str) -> bool:    
    try:
        print("verifying password...")
        print(f"Password hash from database: {password_hash}")
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False

def issue_token(user_uid: str, email: str, project: str, role: str = "user") -> str:
    now = int(time.time())
    payload = {"sub": user_uid, "email": email, "project": project, "role": role,
               "iat": now, "exp": now + EXPIRE_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

# Routes
@security_bp.post("/api/login/step1")
def login_step1():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    

    if not email or not password:
        return jsonify({"error": "Missing email/password"}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Wrong email or password"}), 401

    projects = get_projects_for_user_email(email)
    return jsonify({"projects": projects})


""" original from app.py, moved to security_bp.py and extended with password verification and token issuance
@app.post("/api/login")
def api_login():
    data = request.get_json() or {}
    email = data.get("email")
    project = data.get("project")
    return jsonify({"ok": True}) 
"""


@security_bp.post("/api/login")
def api_login():
    print("api login called")
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    project = (data.get("project") or "").strip()

    if not email or not password or not project:
        return jsonify({"error": "Missing email/password/project"}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Wrong email or password"}), 401

    # Authorization: user must be a MEMBER_OF the project
    with driver.session() as session:
        ok = session.run("""
            MATCH (u:User {email:$email})-[:MEMBER_OF]->(p:Project {name:$project})
            RETURN count(p) AS c
        """, email=email, project=project).single()["c"] > 0

    if not ok:
        return jsonify({"error": "No access to project"}), 403

    token = issue_token(user_uid=user["id_rc"], email=email, project=project, role=user.get("role", "user"))
    csrf = secrets.token_urlsafe(32)

    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("access_token", token, httponly=True, secure=COOKIE_SECURE,
                    samesite=COOKIE_SAMESITE, path="/")
    resp.set_cookie("csrf_token", csrf, httponly=False, secure=COOKIE_SECURE,
                    samesite=COOKIE_SAMESITE, path="/")
    # print response cookies for debugging
    print(f"Set-Cookie headers: {resp.headers.getlist('Set-Cookie')}")
    return resp

# Helper functions for database queries
def get_user_by_email(email: str):
    with driver.session() as session:
        rec = session.run(
            """
            MATCH (u:User {email:$email})
            RETURN u.id_rc AS id_rc, u.email AS email, u.password_hash AS password_hash, u.role AS role
            LIMIT 1
            """,
            email=email
        ).single()
        # print record for debugging
        print(f"Database record for email '{email}': {rec.data() if rec else 'None'}")
        return rec.data() if rec else None

def get_projects_for_user_email(email: str):
    with driver.session() as session:
        result = session.run("""
            MATCH (u:User {email:$email})-[:MEMBER_OF]->(p:Project)
            RETURN p.name AS name ORDER BY name
        """, email=email)
        return [{"id": r["name"], "name": r["name"]} for r in result]
