import configparser
import os
import uuid
import requests
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from neo4j import GraphDatabase
import re


# ===== CONFIG =====
PROJECT = "ZGD1"

""" NEO4J_URI = os.getenv("NEO4J_URI", "bolt://192.168.1.38:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://192.168.1.38:11434")

EMB_MODEL = os.getenv("EMB_MODEL", "mxbai-embed-large:latest")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:14b") """

BASE_DIR = os.path.dirname(__file__)
HTML_PATH = os.path.join(
    BASE_DIR,
    "",
    "",
    "zakon",
    "data",
    "ZAKO4291_NPB22.html",
)

config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")

OLLAMA_BASE = config['OLLAMA']['BASE']
EMB_MODEL = config['OLLAMA']['EMB_MODEL']
MODEL = config['OLLAMA']['MODEL']
TOP_K = int(config['OLLAMA'].get('TOP_K', '8'))




# ===== FastAPI models =====
class ChatRequest(BaseModel):
    question: str
    top_k: Optional[int] = None


class Citation(BaseModel):
    clen: str
    odst: int
    paragraph_id_rc: str
    chunk_id_rc: str
    score: float
    preview: str


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]


# ===== Helpers =====
def rc_id() -> str:
    return str(uuid.uuid4())


def ollama_embed(text: str) -> List[float]:
    r = requests.post(
        f"{OLLAMA_BASE}/api/embeddings",
        json={"model": EMB_MODEL, "prompt": text},
        timeout=180,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama embeddings error: {r.text}")
    return r.json()["embedding"]


def ollama_generate(prompt: str) -> str:
    """
    /api/generate vrne stream; nastavimo stream=False da dobimo en JSON.
    """
    r = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192
            },
        },
        timeout=300,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama generate error: {r.text}")
    return (r.json().get("response") or "").strip()


RETRIEVAL_CYPHER = """
CALL db.index.vector.queryNodes('chunk_embedding', $topK, $qvec)
YIELD node, score
WHERE node.projectName = $projectName
MATCH (node)-[:CHUNK_OF]->(p:Paragraph {projectName:$projectName})<-[:HAS_PARAGRAPH]-(a:Article {projectName:$projectName})
RETURN
  a.num AS clen,
  p.order AS odst,
  p.id_rc AS paragraph_id_rc,
  node.id_rc AS chunk_id_rc,
  node.text AS chunk_text,
  score
ORDER BY score DESC
"""


def build_prompt(question: str, contexts: List[Dict[str, Any]]) -> str:
    """
    Prompt v slovenščini, nagnjen k temu, da odgovori na vprašanje,
    če obstaja vsaj nekaj relevantnega konteksta.
    """
    lines = []
    lines.append("Si zelo natančen pravni asistent za ZGD-1 (Slovenija).")
    lines.append(
        "Odgovarjaj IZKLJUČNO na podlagi spodaj podanega konteksta. "
        "Če obstaja vsaj delno ustrezen kontekst, poskusi iz njega povzeti odgovor."
    )
    lines.append(
        "Samo če v kontekstu res ni ničesar uporabnega za vprašanje, "
        "napiši, da kontekst ne zadošča."
    )
    lines.append(
        "Na koncu odgovora vedno navedi sklic(e) v obliki [člen, odstavek, paragraph_id_rc], "
        "če so v kontekstu prisotni relevantni odstavki."
    )
    lines.append("")
    lines.append("KONTEKST (od najbolj do najmanj relevantnega):")
    for i, c in enumerate(contexts, start=1):
        lines.append(
            f"{i}) Člen {c['clen']} odst. {c['odst']} "
            f"(paragraph_id_rc={c['paragraph_id_rc']})\n{c['chunk_text']}\n"
        )
    lines.append("")
    lines.append(f"VPRAŠANJE: {question}")
    lines.append("ODGOVOR (v slovenščini):")
    return "\n".join(lines)


# ===== App =====
app = FastAPI(title="ZGD1 RAG Chat API")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


@app.on_event("shutdown")
def shutdown_event():
    driver.close()


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    question = req.question.strip()
    top_k = req.top_k or TOP_K

    # ---- 1) Simbolični fallback: direktno iskanje "X člen" ----
    m = re.search(r"(\d+\.\w?)\s*člen", question, flags=re.IGNORECASE)
    if m:
        wanted = m.group(1)  # npr. "10.a" ali "10."
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Article {projectName:$projectName, num:$num})
                MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph {projectName:$projectName})
                MATCH (p)-[:CHUNK_OF]->(c)
                RETURN
                  a.num  AS clen,
                  p.order AS odst,
                  p.id_rc AS paragraph_id_rc,
                  c.id_rc AS chunk_id_rc,
                  c.text AS chunk_text,
                  1.0    AS score
                ORDER BY p.order
                """,
                projectName=PROJECT,
                num=wanted,
            )
            rows = list(rows)

        if rows:
            contexts: List[Dict[str, Any]] = []
            citations: List[Dict[str, Any]] = []

            for r in rows[:top_k]:
                ctx = {
                    "clen":            r["clen"],
                    "odst":            r["odst"],
                    "paragraph_id_rc": r["paragraph_id_rc"],
                    "chunk_id_rc":     r["chunk_id_rc"],
                    "chunk_text":      r["chunk_text"],
                    "score":           float(r["score"]),
                }
                contexts.append(ctx)
                citations.append({
                    "clen":           ctx["clen"],
                    "odst":           ctx["odst"],
                    "paragraph_id_rc": ctx["paragraph_id_rc"],
                    "chunk_id_rc":    ctx["chunk_id_rc"],
                    "score":          ctx["score"],
                    "preview":        ctx["chunk_text"][:200],
                })

            prompt = build_prompt(question, contexts)
            answer = ollama_generate(prompt)

            return ChatResponse(answer=answer, citations=citations)

    # ---- 2) Obstoječi vektorski RAG za ostala vprašanja ----
    with driver.session() as session:
        qvec = ollama_embed(question)
        result = session.run(
            RETRIEVAL_CYPHER,
            qvec=qvec,
            topK=top_k,
            projectName=PROJECT,
        )
        rows = list(result)

    if not rows:
        return ChatResponse(
            answer="Kontekst ne zadošča. V bazi ni najdenih ustreznih odstavkov.",
            citations=[],
        )

    contexts: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    for r in rows:
        ctx = {
            "clen":            r["clen"],
            "odst":            r["odst"],
            "paragraph_id_rc": r["paragraph_id_rc"],
            "chunk_id_rc":     r["chunk_id_rc"],
            "chunk_text":      r["chunk_text"],
            "score":           float(r["score"]),
        }
        contexts.append(ctx)
        citations.append({
            "clen":           ctx["clen"],
            "odst":           ctx["odst"],
            "paragraph_id_rc": ctx["paragraph_id_rc"],
            "chunk_id_rc":    ctx["chunk_id_rc"],
            "score":          ctx["score"],
            "preview":        ctx["chunk_text"][:200],
        })

    # (optional: your existing heuristic that reorders contexts if question mentions a člen)
    prompt = build_prompt(question, contexts)
    answer = ollama_generate(prompt)

    return ChatResponse(answer=answer, citations=citations)
