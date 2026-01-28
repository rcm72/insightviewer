import configparser
from http import client
import os
from pathlib import Path
import textwrap
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
from openai import OpenAI

# ---------- KONFIG ----------

DB_DIR = "chroma_db"
COLLECTION_NAME = "egipt_oai"

EMBED_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"  # lahko tudi 'gpt-4o'

# Preberi OPENAI_API_KEY iz okolja ali config.ini v projektni mapi
load_dotenv()

# base_dir = insightViewer root = 4 nivoje nad tem fajlom
# /home/robert/insightViewer/source/InsightViewer/app/rag/build_index_oai.py
# parents[0] = rag
# parents[1] = app
# parents[2] = InsightViewer
# parents[3] = source
# parents[4] = insightViewer   <-- to rabimo
BASE_DIR = Path(__file__).resolve().parents[4]
config_path = BASE_DIR / "config.ini"
print("config_path:", config_path)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """
Ti si učitelj zgodovine, specializiran za staroegipčansko zgodovino.
Odgovarjaš v slovenščini, jasno in razumljivo, na ravni osnovnošolcev.
Pri odgovorih se opiraj NAJPREJ na priložene odstavke (kontekst).
Če v njih ni dovolj informacij, to povej.
"""


# ---------- POMOŽNE FUNKCIJE ----------

def embed_query(query: str):
    """Embedding vprašanja z OpenAI."""
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=query
    )
    return resp.data[0].embedding


def search_context(query_embedding, top_k: int = 4):
    """Najde najbolj podobne odstavke v ChromaDB (zbirka egipt_oai)."""
    client_chroma = chromadb.PersistentClient(
        path=DB_DIR,
        settings=Settings()
    )
    collection = client_chroma.get_collection(name=COLLECTION_NAME)

    res = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    return list(zip(docs, metas))


def build_user_prompt(context_chunks, question: str) -> str:
    """Sestavi prompt (kontekst + navodilo + vprašanje) za LLM."""
    context_texts = []
    for doc, meta in context_chunks:
        source = meta.get("source", "neznan")
        context_texts.append(f"[{source}] {doc}")

    context_block = "\n\n".join(context_texts)

    user_prompt = f"""
KONTEKST (odstavki iz učbenika o Egiptu):
{context_block}

NAVODILO:
Na podlagi zgornjega konteksta odgovori na vprašanje učenca.
Odgovor naj bo kratek (3–6 stavkov) in v slovenskem jeziku.

Če v kontekstu ni dovolj informacij, to jasno povej.

Vprašanje učenca:
{question}
"""
    return textwrap.dedent(user_prompt).strip()


def ask_llm(user_prompt: str) -> str:
    """Pošlje SYSTEM_PROMPT + user_prompt OpenAI modelu."""
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


# ---------- GLAVNI DEL ----------

def main():
    print("RAG tutor za Egipt (OpenAI) – vpiši vprašanje ali 'quit' za izhod.")
    while True:
        try:
            question = input("\nVprašaš: ").strip()
        except EOFError:
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            break

        # 1) Embedding vprašanja
        q_emb = embed_query(question)

        # 2) Iskanje konteksta v ChromaDB
        chunks = search_context(q_emb, top_k=4)

        print("\n--- Najdeni odstavki (kontekst) ---")
        for doc, meta in chunks:
            print(f"\n[Vir: {meta.get('source')} – chunk {meta.get('chunk')}]")
            print(textwrap.fill(doc, width=80))

        # 3) Sestavimo prompt za LLM
        user_prompt = build_user_prompt(chunks, question)

        # 4) Pošljemo v LLM (OpenAI)
        print("\n--- Odgovor modela ---\n")
        answer = ask_llm(user_prompt)
        print(textwrap.fill(answer, width=80))


if __name__ == "__main__":
    main()
