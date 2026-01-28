import configparser
from pathlib import Path
import requests
from neo4j import GraphDatabase
import os

# BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = BASE_DIR.parent / "config.ini"

config = configparser.ConfigParser()
print("Using config:", CONFIG_PATH)  # optional debug
if not CONFIG_PATH.exists():
    raise RuntimeError(f"Config file not found: {CONFIG_PATH}")

config.read(CONFIG_PATH)



NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OLLAMA_URL = config['OLLAMA']['BASE']
MODEL = config['OLLAMA']['EMB_MODEL']



q = "highest temperature measured in Slovenia"
emb = requests.post(f"{OLLAMA_URL}/api/embeddings", json={"model": MODEL, "prompt": q}).json()["embedding"]
print("Embedding dim:", len(emb))

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
with driver.session() as s:
    rows = s.run("""
        CALL db.index.vector.queryNodes('chunk_embedding_index', 6, $vec)
        YIELD node, score
        RETURN node.id_rc AS id, node.name AS name, score
        ORDER BY score DESC
    """, vec=emb).data()

print(rows)
