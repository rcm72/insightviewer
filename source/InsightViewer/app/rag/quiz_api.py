# filepath: /home/robert/insightViewer/source/InsightViewer/app/rag/quiz_api.py
import os
import json
import random
import configparser
from pathlib import Path
from typing import Dict, Any

import chromadb
from chromadb.config import Settings
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI

# ------- skupna konfiguracija (več kvizov, ena baza) -------

DB_DIR = "chroma_db"
LLM_MODEL = "gpt-4o-mini"

# mapping: ID kviza -> ime kolekcije v Chroma
QUIZ_COLLECTIONS: dict[str, str] = {
    "egipt": "egipt_oai",
    # tukaj dodaj druge kvize:
    # "reinsurance": "reinsurance_oai",
    # "biblija": "biblija_oai",
}

config = configparser.ConfigParser()

BASE_DIR = Path(__file__).resolve().parents[2]
config_path = BASE_DIR / "config.ini"
print("config_path:", config_path)

config.read(config_path)

OPENAI_API_KEY = (
    os.environ.get("OPENAI_API_KEY")
    or config.get("OPENAI", "OPENAI_API_KEY", fallback=None)
)
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment or config.ini")

client = OpenAI(api_key=OPENAI_API_KEY)

chroma_client = chromadb.PersistentClient(path=DB_DIR, settings=Settings())

# lokalni cache, da ne odpiraš iste kolekcije večkrat
_collection_cache: dict[str, chromadb.Collection] = {}


def get_collection_for_quiz(quiz_id: str):
    """
    Glede na ID kviza (npr. 'egipt') vrne Chroma kolekcijo.
    """
    name = QUIZ_COLLECTIONS.get(quiz_id)
    if not name:
        raise HTTPException(status_code=404, detail=f"Neznan kviz '{quiz_id}'.")
    if name not in _collection_cache:
        _collection_cache[name] = chroma_client.get_collection(name=name)
    return _collection_cache[name]


# ------- FastAPI app -------

quiz_api = FastAPI(title="RAG Quiz API (multi-quiz)")

quiz_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_random_chunk(collection) -> Dict[str, Any]:
    """
    Vrne en naključen chunk iz podane Chroma kolekcije.
    """
    dim = 1536
    dummy_embedding = [0.0] * dim

    res = collection.query(
        query_embeddings=[dummy_embedding],
        n_results=200
    )

    docs = res["documents"][0]
    metas = res["metadatas"][0]

    if not docs:
        raise HTTPException(status_code=404, detail="No chunks in collection.")

    idx = random.randrange(len(docs))
    return {
        "text": docs[idx],
        "meta": metas[idx],
        "index": idx,
    }


def generate_question_from_context(context_text: str) -> Dict[str, str]:
    system_prompt = """
Ti si učitelj zgodovine in pripravljaš vprašanja za srednješolce.
Vprašanja naj bodo kratka, jasna in naj se nanašajo izključno na podani odstavek.
Odgovarjaj v slovenščini. Vrni JSON: {"question":"...", "ideal_answer":"..."}.
"""
    user_prompt = f"""
ODSTAVEK:
{context_text}

NAVODILO:
Na podlagi odstavka napiši ENO kratko vprašanje in idealen odgovor.
Vrni strogo JSON objekt brez dodatnega besedila okoli.
"""

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.5,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "question": "Povej na kratko, o čem govori ta odstavek.",
            "ideal_answer": context_text[:200],
        }
    return data


def grade_answer(context_text: str, question: str, ideal_answer: str, student_answer: str) -> Dict[str, Any]:
    system_prompt = """
Ti si učitelj, ki ocenjuje odgovore učencev.
Vrni JSON {"score":0..2, "feedback":"..."}.
"""
    user_prompt = f"""
ODSTAVEK (kontekst):
{context_text}

VPRAŠANJE:
{question}

IDEALEN ODGOVOR:
{ideal_answer}

ODGOVOR UČENCA:
{student_answer}
"""

    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
    )

    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        data["score"] = int(data.get("score", 0))
        data["feedback"] = str(data.get("feedback", "")).strip()
    except (json.JSONDecodeError, ValueError):
        data = {"score": 0, "feedback": "Pri ocenjevanju je prišlo do napake."}
    return data


# ------- API endpoints -------

@quiz_api.get("/quiz/next")
def api_quiz_next(
    quiz: str = Query("egipt", description="ID kviza, npr. 'egipt' ali 'reinsurance'")
):
    """
    Vrne naslednje vprašanje za izbrani kviz.
    Query param: ?quiz=egipt (privzeto) ali npr. ?quiz=reinsurance
    """
    collection = get_collection_for_quiz(quiz)
    chunk = get_random_chunk(collection)
    q = generate_question_from_context(chunk["text"])
    return {
        "quiz": quiz,
        "source": chunk["meta"].get("source", "unknown"),
        "chunk": chunk["meta"].get("chunk", -1),
        "context": chunk["text"],
        "question": q["question"],
        "ideal_answer": q["ideal_answer"],
    }


@quiz_api.post("/quiz/grade")
def api_quiz_grade(
    payload: Dict[str, Any],
    quiz: str = Query("egipt", description="ID kviza, npr. 'egipt' ali 'reinsurance'")
):
    """
    Pričakuje JSON:
    {
      "context": "...",
      "question": "...",
      "ideal_answer": "...",
      "student_answer": "..."
    }
    Query param 'quiz' je tu predvsem informativen (ista ocenjevalna logika).
    """
    required = ["context", "question", "ideal_answer", "student_answer"]
    if not all(k in payload for k in required):
        raise HTTPException(status_code=400, detail="Missing fields in payload.")

    res = grade_answer(
        payload["context"],
        payload["question"],
        payload["ideal_answer"],
        payload["student_answer"],
    )
    # opcijsko vrnemo tudi, kateri kviz je bil uporabljen
    res["quiz"] = quiz
    return res
