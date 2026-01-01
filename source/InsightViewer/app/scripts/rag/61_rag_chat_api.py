from pathlib import Path
from neo4j import GraphDatabase
import importlib.util
import configparser
import os

# Absolute path to rag_chat_api.py (the FastAPI app)
RAG_CHAT_API_PATH = "/home/robert/insightViewer/source/InsightViewer/app/scripts/rag/rag_chat_api.py"

# Dynamically import rag_chat_api as a module
spec = importlib.util.spec_from_file_location("rag_chat_api_mod", RAG_CHAT_API_PATH)
rag_chat_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag_chat_api)

# Load config.ini
# BASE_DIR = "/home/robert/insightViewer/source/InsightViewer/app/scripts/rag"
# config = configparser.ConfigParser()
# config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

# driver = GraphDatabase.driver(
#     config["NEO4J"]["URI"],
#     auth=(config["NEO4J"]["USERNAME"], config["NEO4J"]["PASSWORD"]),
# )

# BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

q = "Kaj določa 10.a člen ZGD-1?"
qvec = rag_chat_api.ollama_embed(q)

with driver.session() as s:
    rows = s.run(
        rag_chat_api.RETRIEVAL_CYPHER,
        qvec=qvec,
        topK=512,
        projectName=rag_chat_api.PROJECT,
    )
    for r in rows:
        print(r["clen"], r["odst"], r["score"])
