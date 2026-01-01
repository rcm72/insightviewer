import textwrap

import chromadb
from chromadb.config import Settings
import ollama

DB_DIR = "chroma_db"
COLLECTION_NAME = "egipt"

EMBED_MODEL = "nomic-embed-text"
#LLM_MODEL = "qwen2.5:3b"
#LLM_MODEL = "qwen2.5:1.5b"
#LLM_MODEL = "qwen-history-tutor:latest"
#LLM_MODEL = "gemma3:270m"
LLM_MODEL = "phi3:mini"
OLLAMA_HOST = "http://192.168.1.13:11434"  # Windows računalnik z Ollamo

# ustvari Ollama klient z nastavljenim hostom
ollama_client = ollama.Client(host=OLLAMA_HOST)

SYSTEM_PROMPT = """
Ti si učitelj zgodovine, specializiran za staroegipčansko zgodovino.
Odgovarjaš v slovenščini, jasno in razumljivo, na ravni osnovnošolcev.
Pri odgovorih se opiraj NAJPREJ na priložene odstavke (kontekst).
Če v njih ni dovolj informacij, to povej.
"""

def embed_query(query: str):
    """Naredi embedding vprašanja z Ollamo na Windowsu."""
    out = ollama_client.embeddings(
        model=EMBED_MODEL,
        prompt=query,
    )
    return out["embedding"]

def search_context(query_embedding, top_k: int = 4):
    """Najde najbolj podobne odstavke v ChromaDB."""
    client = chromadb.PersistentClient(
        path=DB_DIR,
        settings=Settings()
    )
    collection = client.get_collection(name=COLLECTION_NAME)

    res = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    docs = res["documents"][0]
    metas = res["metadatas"][0]
    return list(zip(docs, metas))

def build_user_prompt(context_chunks, question: str) -> str:
    """Sestavi uporabniški prompt: kontekst + vprašanje + navodilo."""
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
    """Pošlje sistemska navodila + uporabniški prompt Qwen modelu."""
    res = ollama_client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_prompt},
        ],
    )
    return res["message"]["content"]

def main():
    print("RAG tutor za Egipt – vpiši vprašanje ali 'quit' za izhod.")
    while True:
        try:
            question = input("\nVprašaš: ").strip()
        except EOFError:
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit"):
            break

        # 1) embedding vprašanja
        q_emb = embed_query(question)

        # 2) poiščemo relevantne odstavke
        chunks = search_context(q_emb, top_k=4)

        print("\n--- Najdeni odstavki (kontekst) ---")
        for doc, meta in chunks:
            print(f"\n[Vir: {meta.get('source')} – chunk {meta.get('chunk')}]")
            print(textwrap.fill(doc, width=80))

        # 3) sestavimo prompt za model
        user_prompt = build_user_prompt(chunks, question)

        # 4) vprašamo LLM
        print("\n--- Odgovor modela ---\n")
        answer = ask_llm(user_prompt)
        print(textwrap.fill(answer, width=80))

if __name__ == "__main__":
    main()
