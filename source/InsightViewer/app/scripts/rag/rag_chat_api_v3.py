# rag_chat_api_v3.py

import configparser
import os
from pathlib import Path
import requests
import re
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from neo4j import GraphDatabase


# ===== CONFIG =====
PROJECT = "ZGD1"
# BASE_DIR = os.path.dirname(__file__)

# config = configparser.ConfigParser()
# config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

# BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = BASE_DIR / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

NEO4J_URI = config["NEO4J"]["URI"]
NEO4J_USER = config["NEO4J"]["USERNAME"]
NEO4J_PASSWORD = config["NEO4J"]["PASSWORD"]

OLLAMA_BASE = config["OLLAMA"]["BASE"]
EMB_MODEL = config["OLLAMA"]["EMB_MODEL"]          # e.g. mxbai-embed-large:latest
MODEL = config["OLLAMA"]["MODEL"]                  # e.g. qwen2.5:14b
TOP_K = int(config["OLLAMA"].get("TOP_K", "8"))

ASSESSABLE_CYPHER = """
MATCH (a:Article {projectName:$projectName})
WHERE $articleNum IS NULL OR a.num = $articleNum
MATCH (a)-[:HAS_PARAGRAPH]->(p:Paragraph {projectName:$projectName})
OPTIONAL MATCH (p)-[:HAS_POINT]->(pt:Point {projectName:$projectName})
OPTIONAL MATCH (p)-[:HAS_ITEM]->(ip:IndentItem {projectName:$projectName})
OPTIONAL MATCH (pt)-[:HAS_ITEM]->(it:IndentItem {projectName:$projectName})
WITH collect(p) + collect(pt) + collect(ip) + collect(it) AS ns
UNWIND ns AS n
WITH DISTINCT n
WHERE n.isAssessable = "true" AND n.text is not null
RETURN n.text AS txt
"""


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
    route: str  # "direct_article" | "vector"

class GradeRequest(BaseModel):
    question: str
    user_answer: str
    # optional: če želiš hint na člen, lahko dodaš:
    article_num: Optional[str] = None  # npr. '57.'


class GradeResponse(BaseModel):
    evaluation: str  # modelova razlaga, ali je odgovor pravilen / kaj manjka    


# ===== Ollama helpers =====
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
    r = requests.post(
        f"{OLLAMA_BASE}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192},
        },
        timeout=300,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama generate error: {r.text}")
    return (r.json().get("response") or "").strip()

def build_grading_prompt(
    question: str,
    user_answer: str,
    context_chunks: List[str],
    article_num: Optional[str] = None,
) -> str:
    ctx = "\n\n".join(context_chunks[:20])  # omejiš število blokov, če jih je veliko
    lines: List[str] = []
    lines.append("Si natančen pravni asistent za ZGD-1 (Slovenija).")
    lines.append("Tvoja naloga je OVREDNOTITI odgovor študenta glede na podan kontekst.")
    lines.append(
        "STROGO prepovedano je podajati popoln modelni odgovor ali navajati konkretne pravilne sestavine, alineje, pojme ali primere. "
        "NE SMEŠ navajati ali omenjati nobenih konkretnih pravnih izrazov iz konteksta (npr. imen posameznih poročil, mnenj, obveznosti)."
    )
    lines.append(
        "Tvoj cilj je SAMO ocenjevanje, ne poučevanje. "
        "Odgovor naj študentu nakaže, ali je odgovor (pravilen|delno pravilen|napačen) in ZGOLJ NA SPLOŠNO, "
        "ali mu manjka več sestavin, več podrobnosti, dodatna pojasnila ipd., brez konkretnih primerov."
    )
    lines.append("Če je odgovor napačen dobi študent 0 točk.")
    lines.append(
        "Struktura odgovora:\n"
        "1) Prva vrstica: 'Ocena: X/10, odgovor (pravilen|delno pravilen|napačen)'.\n"
        "2) Nato NAJVEČ tri kratke stavke, ki SPLOŠNO opišejo:\n"
        "   - ali se odgovor dotakne glavne teme ali samo manjšega dela vprašanja,\n"
        "   - ali mu manjka več pomembnih elementov ali podrobnosti, brez naštevanja teh elementov,\n"
        "   - na katere člene/odstavke naj se obrne (brez povzema vsebine teh členov)."
    )
    lines.append(
        "NE naštevaj konkretnih sestavin ali primerov, kot so npr. posamezna poročila, mnenja, postavke ali alineje. "
        "Takih konkretnih izrazov NE SME BITI v tvojem odgovoru."
    )

    if article_num:
        lines.append(
            f"Kontekst se nanaša na {article_num} člen ZGD-1 in njegove odstavke. "
            "Ne izmišljuj novih številk členov. "
            "Če omenjaš člen ali odstavek, uporabi podani člen in tisto oznako odstavka, ki je eksplicitno razvidna iz konteksta "
            "(npr. '57. člen, prvi odstavek'). "
            "Pri tem NE opisuj natančne vsebine tega odstavka, samo usmeri študenta nanj."
        )
    else:
        lines.append(
            "Če kontekst ne vsebuje eksplicitnih številk členov, ne izmišljuj novih številk členov; "
            "raje samo povej, da naj študent preveri ustrezne odstavke v podanem kontekstu."
        )

    lines.append("Odgovarjaj v slovenščini.")
    lines.append("")
    lines.append("KONTEKST (iz zakona, vozlišča isAssessable=true):")
    lines.append(ctx if ctx else "(Ni konteksta.)")
    lines.append("")
    lines.append(f"VPRAŠANJE: {question}")
    lines.append("")
    lines.append(f"ODGOVOR ŠTUDENTA: {user_answer}")
    lines.append("")
    lines.append(
        "Zdaj podaj oceno in zelo splošno razlago v skladu z zgornjimi navodili. "
        "Še enkrat: NE NAVAJAJ konkretnih pravnih pojmov, imen poročil, mnenj, obveznosti ali drugih podrobnosti iz konteksta."
    )
    return "\n".join(lines)


# ===== Router: detect explicit "X člen" =====
# Captures:
# - "10.a člen", "10.č člen"
# - "10. člen"
# Tolerates spaces: "10. a člen"
ARTICLE_IN_Q_RE = re.compile(
    r"\b(?P<num>\d{1,4})\s*\.\s*(?P<suf>[a-zčšž])\s*člen\b|\b(?P<num2>\d{1,4})\s*\.\s*člen\b",
    re.IGNORECASE
)

def extract_article_num(question: str) -> Optional[str]:
    """
    Returns canonical Article.num used in Neo4j:
      - '10.a' for '10.a člen'
      - '10.'  for '10. člen'
    """
    m = ARTICLE_IN_Q_RE.search(question or "")
    if not m:
        return None
    if m.group("num") and m.group("suf"):
        return f"{m.group('num')}.{m.group('suf').lower()}"
    if m.group("num2"):
        return f"{m.group('num2')}."
    return None


# ===== Cypher =====
DIRECT_ARTICLE_CYPHER = """
MATCH (a:Article {projectName:$projectName, num:$num})-[:HAS_PARAGRAPH]->(p:Paragraph {projectName:$projectName})
MATCH (c:Chunk {projectName:$projectName})-[:CHUNK_OF]->(p)
RETURN
  a.num   AS clen,
  p.order AS odst,
  p.id_rc AS paragraph_id_rc,
  c.id_rc AS chunk_id_rc,
  c.text  AS chunk_text,
  1.0     AS score
ORDER BY p.order ASC
LIMIT $limit
"""

VECTOR_CYPHER = """
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
    lines = []
    lines.append("Si zelo natančen pravni asistent za ZGD-1 (Slovenija).")
    lines.append("Odgovarjaj IZKLJUČNO na podlagi spodaj podanega konteksta.")
    lines.append("Če kontekst ne zadošča, to jasno povej.")
    lines.append("Na koncu odgovora navedi sklice v obliki [člen, odstavek, paragraph_id_rc].")
    lines.append("")
    lines.append("KONTEKST:")
    for i, c in enumerate(contexts, start=1):
        lines.append(
            f"{i}) Člen {c['clen']} odst. {c['odst']} "
            f"(paragraph_id_rc={c['paragraph_id_rc']})\n{c['chunk_text']}\n"
        )
    lines.append("")
    lines.append(f"VPRAŠANJE: {question}")
    lines.append("ODGOVOR (v slovenščini):")
    return "\n".join(lines)


def rows_to_context_and_citations(rows: List[dict], limit: int) -> Tuple[List[Dict[str, Any]], List[Citation]]:
    contexts: List[Dict[str, Any]] = []
    citations: List[Citation] = []
    for r in rows[:limit]:
        chunk_text = r["chunk_text"] or ""
        ctx = {
            "clen": r["clen"],
            "odst": int(r["odst"]),
            "paragraph_id_rc": r["paragraph_id_rc"],
            "chunk_id_rc": r["chunk_id_rc"],
            "chunk_text": chunk_text,
            "score": float(r["score"]),
        }
        contexts.append(ctx)
        citations.append(Citation(
            clen=ctx["clen"],
            odst=ctx["odst"],
            paragraph_id_rc=ctx["paragraph_id_rc"],
            chunk_id_rc=ctx["chunk_id_rc"],
            score=ctx["score"],
            preview=chunk_text[:200],
        ))
    return contexts, citations




# ===== App =====
app = FastAPI(title="ZGD1 RAG Chat API (router)")

# Dovoli klice iz Flask UI na 5001
origins = [
    "http://192.168.1.16:5001",
    "http://localhost:5001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # lahko začasno tudi ["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


@app.on_event("shutdown")
def shutdown_event():
    driver.close()


@app.get("/health")
def health():
    with driver.session() as session:
        chunks = session.run(
            "MATCH (c:Chunk {projectName:$p}) RETURN count(c) AS n",
            p=PROJECT
        ).single()["n"]
    return {
        "ok": True,
        "project": PROJECT,
        "chunks": chunks,
        "neo4j_uri": NEO4J_URI,
        "ollama": OLLAMA_BASE,
        "emb_model": EMB_MODEL,
        "model": MODEL,
        "top_k_default": TOP_K,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    top_k = req.top_k or TOP_K

    wanted_num = extract_article_num(question)

    # ===== Route A: direct article lookup (fast + exact) =====
    if wanted_num:
        with driver.session() as session:
            rows = list(session.run(
                DIRECT_ARTICLE_CYPHER,
                projectName=PROJECT,
                num=wanted_num,
                limit=max(200, top_k),  # fetch whole article; response will still cap to top_k
            ))

        if rows:
            contexts, citations = rows_to_context_and_citations(rows, top_k)
            prompt = build_prompt(question, contexts)
            answer = ollama_generate(prompt)
            return ChatResponse(answer=answer, citations=citations, route="direct_article")

        # If article wasn't found (rare), fall through to vector route.

    # ===== Route B: vector retrieval (semantic) =====
    qvec = ollama_embed(question)
    with driver.session() as session:
        rows = list(session.run(
            VECTOR_CYPHER,
            qvec=qvec,
            topK=top_k,
            projectName=PROJECT,
        ))

    if not rows:
        return ChatResponse(
            answer="Kontekst ne zadošča. V bazi ni najdenih ustreznih odstavkov.",
            citations=[],
            route="vector",
        )

    contexts, citations = rows_to_context_and_citations(rows, top_k)
    prompt = build_prompt(question, contexts)
    answer = ollama_generate(prompt)
    return ChatResponse(answer=answer, citations=citations, route="vector")

@app.post("/grade-answer", response_model=GradeResponse)
def grade_answer(req: GradeRequest):
    question = (req.question or "").strip()
    user_answer = (req.user_answer or "").strip()
    if not question or not user_answer:
        raise HTTPException(status_code=400, detail="question and user_answer are required")

    # če pride article_num iz frontenda, ga uporabi; sicer pusti None
    article_num = (req.article_num or "").strip() or None

    # 1) poberi kontekst iz Neo4j (samo isAssessable=true)
    try:
        with driver.session() as session:
            rows = list(session.run(
                ASSESSABLE_CYPHER,
                projectName=PROJECT,
                articleNum=article_num,
            ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Neo4j error in ASSESSABLE_CYPHER: {e}")

    context_chunks: List[str] = []
    for r in rows:
        txt = r.get("txt")
        if txt:
            context_chunks.append(txt)

    prompt = build_grading_prompt(question, user_answer, context_chunks, article_num)

    try:
        evaluation = ollama_generate(prompt)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama call failed: {e}")

    return GradeResponse(evaluation=evaluation)
