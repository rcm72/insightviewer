import configparser
import csv
import json
import os
from pathlib import Path
import random
import textwrap
from datetime import datetime

import chromadb
from chromadb.config import Settings
from openai import OpenAI
from dotenv import load_dotenv

# ---------- KONFIG ----------

DB_DIR = "chroma_db"
COLLECTION_NAME = "egipt_oai"

LLM_MODEL = "gpt-4o-mini"  # ali 'gpt-4o'
RESULTS_FILE = "quiz_results.csv"

config = configparser.ConfigParser()

# base_dir = insightViewer root = 4 nivoje nad tem fajlom
# /home/robert/insightViewer/source/InsightViewer/app/rag/build_index_oai.py

BASE_DIR = Path(__file__).resolve().parents[4]
config_path = BASE_DIR / "config.ini"
print("config_path:", config_path)

config.read(config_path)

load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

client = OpenAI(api_key=OPENAI_API_KEY)


# ---------- POMOŽNE FUNKCIJE: delo s ChromaDB ----------

def get_all_chunks(limit_per_doc=5):
    """
    Zbere nekaj chunkov iz ChromaDB, da imamo gradivo za vprašanja.
    limit_per_doc: največ chunkov na datoteko (da ne dobimo 1000 kosov).
    """
    client_chroma = chromadb.PersistentClient(
        path=DB_DIR,
        settings=Settings()
    )
    collection = client_chroma.get_collection(name=COLLECTION_NAME)

    # Ker vemo, da je zbirka egipt_oai narejena z text-embedding-3-small (1536 dim),
    # neposredno uporabimo to dimenzijo:
    dim = 1536

    dummy_embedding = [0.0] * dim

    res = collection.query(
        query_embeddings=[dummy_embedding],
        n_results=1000
    )

    docs = res["documents"][0]
    metas = res["metadatas"][0]

    by_source = {}
    for doc, meta in zip(docs, metas):
        src = meta.get("source", "unknown")
        by_source.setdefault(src, []).append((doc, meta))

    selected = []
    for src, items in by_source.items():
        random.shuffle(items)
        selected.extend(items[:limit_per_doc])

    random.shuffle(selected)
    return selected


# ---------- POMOŽNE FUNKCIJE: delo z LLM ----------

def generate_question_from_context(context_text: str):
    """
    Na podlagi konteksta OpenAI modelu naroči,
    naj vrne JSON: { "question": "...", "ideal_answer": "..." }.
    """
    system_prompt = """
Ti si učitelj zgodovine (stari Egipt) in pripravljaš vprašanja za srednješolce.
Vprašanja naj bodo kratka, jasna in naj se nanašajo izključno na podani odstavek.
Ne sprašuj podrobnosti, ki niso v odstavku.
Odgovarjaj v slovenščini.
"""

    user_prompt = f"""
ODSTAVEK (kontekst):
{context_text}

NAVODILO:
Na podlagi odstavka napiši ENO kratko vprašanje za učenca in idealen odgovor.
Vrni strogo JSON objekt oblike:
{{
  "question": "...",
  "ideal_answer": "..."
}}
Brez dodatnega besedila okoli JSON-a.
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

    # Poskusimo razparsati JSON
    try:
        data = json.loads(content)
        question = data.get("question", "").strip()
        ideal_answer = data.get("ideal_answer", "").strip()
        return question, ideal_answer
    except json.JSONDecodeError:
        # Če se kaj zalomi, vrnemo fallback vprašanje
        return "Povej na kratko, o čem govori ta odstavek.", context_text[:200]


def grade_answer(context_text: str, question: str, ideal_answer: str, student_answer: str):
    """
    Oceni odgovor učenca glede na kontekst in idealen odgovor.
    Vrne (score, feedback).
    """
    system_prompt = """
Ti si učitelj zgodovine, ki ocenjuje odgovore učencev.
Bodi prijazen, a natančen. Upoštevaj PODANI ODASTAVEK kot glavni vir.
"""

    user_prompt = f"""
ODSTAVEK (kontekst):
{context_text}

VPRAŠANJE:
{question}

IDEALEN ODGOVOR (učiteljev):
{ideal_answer}

ODGOVOR UČENCA:
{student_answer}

NAVODILO ZA OCENJEVANJE:
1. Najprej oceni odgovor učenca z ENO celo številko med 0 in 2:
   - 0 = napačno ali popolnoma mimo odstavka
   - 1 = ni popolnoma napačen odgovor
   - 2 = delno pravilen odgovor
   - 3 = dober odgovor na ravni srednješolca
   - 4 = zelo dober odgovor na ravni srednješolca
   - 5 = popolnoma pravilen odgovor na ravni srednješolca
2. Nato na kratko razloži, zakaj je dobil to oceno.
3. Odgovori v slovenskem jeziku.
4. Odgovor vrni v strogo JSON obliki:
{{
  "score": 0,
  "feedback": "..."
}}
Brez dodatnega besedila okoli JSON-a.
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
        score = int(data.get("score", 0))
        feedback = data.get("feedback", "").strip()
        return score, feedback
    except (json.JSONDecodeError, ValueError):
        return 0, "Pri ocenjevanju je prišlo do napake. Poskusi še enkrat."


# ---------- POMOŽNE FUNKCIJE: shranjevanje rezultatov ----------

def init_results_file():
    """Ustvari CSV z glavo, če še ne obstaja."""
    if not os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "timestamp",
                "source",
                "chunk",
                "question",
                "ideal_answer",
                "student_answer",
                "score",
                "feedback"
            ])


def save_result(source, chunk_idx, question, ideal_answer, student_answer, score, feedback):
    """Zapiše en rezultat v CSV."""
    with open(RESULTS_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            source,
            chunk_idx,
            question,
            ideal_answer,
            student_answer,
            score,
            feedback.replace("\n", " ")
        ])


# ---------- GLAVNI KVIZ LOOP ----------

def main():
    print("Kvizi za Egipt (OpenAI RAG) – odgovori na vprašanja, 'quit' za izhod.\n")

    init_results_file()
    chunks = get_all_chunks(limit_per_doc=5)

    if not chunks:
        print("Ni najdenih chunkov v ChromaDB. Najprej zaženi build_index_oai.py.")
        return

    total_questions = 0
    total_score = 0

    for doc, meta in chunks:
        source = meta.get("source", "unknown")
        chunk_idx = meta.get("chunk", -1)

        # 1) Generiraj vprašanje iz konteksta
        question, ideal_answer = generate_question_from_context(doc)

        print("\n----------------------------------------")
        print(f"[Vir: {source} – chunk {chunk_idx}]")
        print("\nVprašanji za odsek učbenika:")
        print(textwrap.fill(question, width=80))

        # 2) Odgovor učenca
        student_answer = input("\nTvoj odgovor (ali 'quit' za izhod): ").strip()
        if student_answer.lower() in ("quit", "exit"):
            break

        if not student_answer:
            print("Prazni odgovor – preskočimo.")
            continue

        # 3) Oceni odgovor
        score, feedback = grade_answer(doc, question, ideal_answer, student_answer)

        print(f"\nOcena: {score} / 2")
        print("Povratna informacija:")
        print(textwrap.fill(feedback, width=80))

        # 4) Shrani rezultat
        save_result(source, chunk_idx, question, ideal_answer, student_answer, score, feedback)

        total_questions += 1
        total_score += score

        # Malo povprečja
        avg = total_score / total_questions if total_questions else 0
        print(f"\nDoslej: {total_score} točk pri {total_questions} vprašanjih (povprečje: {avg:.2f}).")

    print("\nKviz zaključen. Rezultati so shranjeni v:", RESULTS_FILE)


if __name__ == "__main__":
    main()
