import os
from pathlib import Path
import uuid
import requests
from neo4j import GraphDatabase
import configparser




#BASE_DIR = os.path.dirname(__file__)
#config = configparser.ConfigParser()
#config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

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

PROJECT = "ZGD1"

def rc_id() -> str:
    return str(uuid.uuid4())


def ollama_embed(text: str) -> list[float]:
    r = requests.post(
        f"{OLLAMA_BASE}/api/embeddings",
        json={"model": EMB_MODEL, "prompt": text},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def ensure_vector_index(tx, dim: int):
    # Neo4j DDL: safe to run repeatedly due to IF NOT EXISTS
    tx.run(
        f"""
        CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
        FOR (c:Chunk) ON (c.embedding)
        OPTIONS {{indexConfig: {{
          `vector.dimensions`: {dim},
          `vector.similarity_function`: 'cosine'
        }}}}
        """
    )


def upsert_chunk(tx, chunkId: str, text: str, embedding: list[float], parId: str):
    tx.run(
        """
        MATCH (p:Paragraph {parId:$parId, projectName:$projectName})
        MERGE (c:Chunk {chunkId:$chunkId})
        ON CREATE SET
          c.id_rc = $id_rc,
          c.text = $text,
          c.embedding = $embedding,
          c.projectName = $projectName
        MERGE (c)-[:CHUNK_OF]->(p)
        """,
        parId=parId,
        chunkId=chunkId,
        id_rc=rc_id(),
        text=text,
        embedding=embedding,
        projectName=PROJECT,
    )


def fetch_paragraphs_without_chunk(session):
    return session.run(
        """
        MATCH (p:Paragraph {projectName:$projectName})
        WHERE p.text IS NOT NULL AND trim(p.text) <> ""
          AND NOT (p)<-[:CHUNK_OF]-(:Chunk {projectName:$projectName})
        RETURN p.parId AS parId, p.text AS text
        ORDER BY p.parId
        """,
        projectName=PROJECT,
    )


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        # 1) dimenzija + index
        dim = len(ollama_embed("test"))
        with driver.session() as session:
            session.execute_write(ensure_vector_index, dim)
        print(f"OK: vector index 'chunk_embedding' ensured (dim={dim})")

        # 2) najprej PREBERI vse odst. brez chunk-a
        with driver.session() as session:
            rows = list(fetch_paragraphs_without_chunk(session))

        # 3) nato v ločeni seji PIŠI (ustvarjaj chanke)
        n = 0
        with driver.session() as session:
            for r in rows:
                parId = r["parId"]
                text = (r["text"] or "").strip()
                if not text:
                    continue

                chunkId = parId + "#c1"
                emb = ollama_embed(text)

                session.execute_write(upsert_chunk, chunkId, text, emb, parId)

                n += 1
                if n % 50 == 0:
                    print("Embedded:", n)

        print("DONE: embedded new paragraphs =", n)

    finally:
        driver.close()


if __name__ == "__main__":
    main()
