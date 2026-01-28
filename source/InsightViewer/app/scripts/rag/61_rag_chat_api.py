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
BASE_DIR = "/home/robert/insightViewer/source/InsightViewer/app/scripts/rag"
config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD),
)

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
