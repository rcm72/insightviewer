# Če to vrne rezultate → vse je pravilno nastavljeno.

import configparser
import os
from pathlib import Path
from neo4j import GraphDatabase
import requests

# BASE_DIR = os.path.dirname(__file__)
# config = configparser.ConfigParser()
# config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

# BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = BASE_DIR / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

HTML_PATH = (
    Path(__file__)
    .resolve()
    .parent              # .../app/scripts/rag
    / "zakon"
    / "data"
    / "ZAKO4291_NPB22.html"
)


NEO4J_URI = config['NEO4J']['URI']
NEO4J_USER = config['NEO4J']['USERNAME']
NEO4J_PASSWORD = config['NEO4J']['PASSWORD']

OLLAMA_BASE = config['OLLAMA']['BASE']
EMB_MODEL = config['OLLAMA']['EMB_MODEL']
MODEL = config['OLLAMA']['MODEL']




def embed(text):
    r = requests.post(
        f"{OLLAMA_BASE}/api/embeddings",
        json={"model": EMB_MODEL, "prompt": text},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["embedding"]

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

qvec = embed("Kaj določa 10.a člen ZGD-1?")

with driver.session() as s:
    r = s.run("""
    CALL db.index.vector.queryNodes('chunk_embedding', 5, $qvec)
    YIELD node, score
    RETURN substring(node.text,0,120) AS text, score
    """, qvec=qvec)

    for row in r:
        print(row)
