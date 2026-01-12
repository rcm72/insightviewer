# filepath: /home/robert/insightViewer/source/InsightViewer/app/rag/quiz_vector.py
import configparser
import json
import os
import random
import textwrap
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import requests

from app.models.neo4jConnect import Neo4jConnector

# --- konfiguracija ---
DB_DIR = "chroma_db"  # not used here but kept for parity
# Ollama configuration (will be loaded from config.ini)
RESULTS_FILE = "quiz_vector_results.csv"

# locate config.ini like other scripts
BASE_DIR = Path(__file__).resolve().parents[4]
config_path = BASE_DIR / "config.ini"
print("config_path:", config_path)
config = configparser.ConfigParser()
config.read(config_path)
# Pull Ollama config from config.ini [OLLAMA] section with fallbacks
OLLAMA_BASE = config.get("OLLAMA", "BASE", fallback="http://192.168.1.38:11434")
EMB_MODEL = config.get("OLLAMA", "EMB_MODEL", fallback="mxbai-embed-large:latest")
MODEL = config.get("OLLAMA", "MODEL", fallback="qwen2.5:14b")
try:
    TOP_K = int(config.get("OLLAMA", "TOP_K", fallback="8"))
except Exception:
    TOP_K = 8
LLM_MODEL = MODEL
# Auth token (optional)
OLLAMA_AUTH = os.environ.get("OLLAMA_AUTH") or config.get("OLLAMA", "AUTH", fallback=None)


def ollama_generate(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 512) -> str:
    """
    Call local Ollama HTTP API to generate a response. Return the assistant text.
    The function is resilient to minor variations in Ollama response shape.
    """
    url = f"{OLLAMA_BASE}/api/generate"
    # Combine system and user into a single prompt
    prompt = f"SYSTEM:\n{system_prompt.strip()}\n\nUSER:\n{user_prompt.strip()}\n"
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if OLLAMA_AUTH:
        headers["Authorization"] = f"Bearer {OLLAMA_AUTH}"
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        text = None
        try:
            j = resp.json()
        except Exception:
            j = None
        if j:
            # common structures
            if "choices" in j and isinstance(j["choices"], list) and j["choices"]:
                c = j["choices"][0]
                # try message.content or text
                if isinstance(c, dict):
                    if "message" in c and isinstance(c["message"], dict) and "content" in c["message"]:
                        text = c["message"]["content"]
                    elif "content" in c:
                        text = c["content"]
            elif "output" in j:
                # sometimes output is list of strings
                out = j.get("output")
                if isinstance(out, list):
                    text = "".join(str(x) for x in out)
                else:
                    text = str(out)
            elif "text" in j:
                text = j["text"]
        if text is None:
            # fallback to raw body
            text = resp.text
        return str(text).strip()
    except Exception as e:
        return f"{{\"error\": \"ollama request failed: {e}\"}}"


# --- Neo4j helper ---
neo4j = Neo4jConnector()


def list_nodes(label: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Vrne seznam vozlišč z dano nalepko kot seznam dictov: {"id": int, "props": dict}.
    """
    cypher = f"MATCH (n:`{label}`) RETURN id(n) as id, properties(n) as props LIMIT $limit"
    records = neo4j.query(cypher, parameters={"limit": limit})
    out = []
    for r in records:
        # record may be Record with keys 'id' and 'props'
        try:
            rid = r["id"] if "id" in r.keys() else r[0]
            props = r["props"] if "props" in r.keys() else r[1]
        except Exception:
            # Fallback generic unpack
            try:
                rid = r[0]
                props = dict(r[1])
            except Exception:
                continue
        out.append({"id": int(rid), "props": dict(props)})
    return out


def fetch_chunks_for_node(node_id: int, max_depth: int = 6, limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Poišče CHUNK vozlišča, dosegljiva iz izbranega vozlišča z maksimalno globino max_depth.
    Vrne seznam dictov: {"id": int, "props": dict}.
    """
    cypher = (
        "MATCH (start) WHERE id(start) = $id "
        "MATCH p=(start)-[*1..$max_depth]->(c:CHUNK) "
        "RETURN DISTINCT id(c) as id, properties(c) as props LIMIT $limit"
    )
    records = neo4j.query(cypher, parameters={"id": node_id, "max_depth": max_depth, "limit": limit})
    out = []
    for r in records:
        try:
            rid = r["id"] if "id" in r.keys() else r[0]
            props = r["props"] if "props" in r.keys() else r[1]
        except Exception:
            try:
                rid = r[0]
                props = dict(r[1])
            except Exception:
                continue
        out.append({"id": int(rid), "props": dict(props)})
    return out


# --- LLM helpers (similar to existing quiz scripts) ---

def generate_question_from_context(context_text: str) -> Dict[str, str]:
    system_prompt = """
Ti si učitelj geografije in pripravljaš vprašanja za srednješolce.
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
    content = ollama_generate(system_prompt, user_prompt, temperature=0.5)
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
Vrni JSON {"score":0..5, "feedback":"..."}.
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
    content = ollama_generate(system_prompt, user_prompt, temperature=0.2)
    try:
        data = json.loads(content)
        data["score"] = int(data.get("score", 0))
        data["feedback"] = str(data.get("feedback", "")).strip()
    except (json.JSONDecodeError, ValueError):
        data = {"score": 0, "feedback": "Pri ocenjevanju je prišlo do napake."}
    return data


# --- results persistence ---

def init_results_file():
    if not os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                "timestamp",
                "selected_node_id",
                "selected_node_props",
                "chunk_node_id",
                "chunk_props",
                "question",
                "ideal_answer",
                "student_answer",
                "score",
                "feedback",
            ])


def save_result(selected_node_id, selected_node_props, chunk_node_id, chunk_props, question, ideal_answer, student_answer, score, feedback):
    with open(RESULTS_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            datetime.now().isoformat(timespec="seconds"),
            selected_node_id,
            json.dumps(selected_node_props, ensure_ascii=False),
            chunk_node_id,
            json.dumps(chunk_props, ensure_ascii=False),
            question,
            ideal_answer,
            student_answer,
            score,
            feedback.replace("\n", " "),
        ])


# --- interactive flow ---

def choose_label() -> str:
    choices = ["Course", "Chapter", "Section", "SubSection"]
    print("Izberi tip vozlišča (vnesi številko):")
    for i, c in enumerate(choices, 1):
        print(f"{i}. {c}")
    while True:
        sel = input("Izbira: ").strip()
        if not sel:
            continue
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print("Neveljavna izbira, poskusi ponovno.")


def pretty_props(props: Dict[str, Any]) -> str:
    # Prefer name/title fields for display
    for key in ("name", "title", "label", "id", "uid"):
        if key in props:
            return str(props[key])
    # Otherwise show a short JSON
    text = json.dumps(props, ensure_ascii=False)
    return text[:80]


def interactive():
    print("Kviz: quiz_vector — izberi vozlišče in generiraj vprašanja iz pripetih CHUNKov.")
    label = choose_label()
    nodes = list_nodes(label)
    if not nodes:
        print(f"Ni najdenih vozlišč z labelo {label}.")
        return
    print(f"Najdenih {len(nodes)} vozlišč. Izberi eno:")
    for i, n in enumerate(nodes, 1):
        print(f"{i}. id={n['id']} — {pretty_props(n['props'])}")
    while True:
        sel = input("Izberi številko vozlišča: ").strip()
        try:
            idx = int(sel) - 1
            if 0 <= idx < len(nodes):
                chosen = nodes[idx]
                break
        except Exception:
            pass
        print("Neveljavna izbira, poskusi ponovno.")

    print(f"Zbrano vozlišče: id={chosen['id']} — {pretty_props(chosen['props'])}")
    print("Poiščem CHUNK vozlišča pod izbranim podgrafom ...")
    chunks = fetch_chunks_for_node(chosen["id"]) if chosen else []
    if not chunks:
        print("Ni najdenih CHUNK vozlišč pod izbranim vozliščem.")
        return
    print(f"Najdenih {len(chunks)} CHUNKov."
          " Če je več, bodo vprašanja izbrana naključno.")

    init_results_file()
    # koliko vprašanj
    while True:
        n_q = input("Koliko vprašanj naj LLM pripravi? ").strip()
        try:
            n_q_int = int(n_q)
            if n_q_int > 0:
                break
        except Exception:
            pass
        print("Vnesi pozitivno celo število.")

    total_score = 0
    total_questions = 0
    for i in range(n_q_int):
        chunk = random.choice(chunks)
        chunk_text = None
        # try to find content field in chunk props
        props = chunk.get("props", {})
        for key in ("text", "content", "body", "chunk_text", "html"):
            if key in props and props[key]:
                chunk_text = props[key]
                break
        if not chunk_text:
            # fall back to any string property or JSON dump
            chunk_text = next((v for v in props.values() if isinstance(v, str) and len(v) > 20), json.dumps(props, ensure_ascii=False))

        qdata = generate_question_from_context(chunk_text)
        question = qdata.get("question", "")
        ideal = qdata.get("ideal_answer", "")
        print("\n----------------------------------------")
        print(f"Vprašanje {i+1} / {n_q_int}:")
        print(textwrap.fill(question, width=80))
        student_answer = input("\nTvoj odgovor (ali 'quit' za izhod): ").strip()
        if student_answer.lower() in ("quit", "exit"):
            break
        if not student_answer:
            print("Prazni odgovor – preskočimo.")
            continue

        grade = grade_answer(chunk_text, question, ideal, student_answer)
        score = int(grade.get("score", 0))
        feedback = grade.get("feedback", "")
        print(f"\nOcena: {score}")
        print("Povratna informacija:")
        print(textwrap.fill(feedback, width=80))

        save_result(chosen["id"], chosen["props"], chunk["id"], chunk["props"], question, ideal, student_answer, score, feedback)
        total_questions += 1
        total_score += score
        avg = total_score / total_questions if total_questions else 0
        print(f"\nDoslej: {total_score} točk pri {total_questions} vprašanjih (povprečje: {avg:.2f}).")

    print("\nKviz končan. Rezultati shranjeni v:", RESULTS_FILE)


if __name__ == "__main__":
    interactive()
