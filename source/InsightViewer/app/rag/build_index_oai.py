# filepath: /home/robert/insightViewer/source/InsightViewer/app/rag/build_index_oai.py
# cd /home/robert/insightViewer/source/InsightViewer/app/rag
# python build_index_oai.py \
#   --data-dir data/egipt \
#   --collection egipt \
#   --reset
import os
import textwrap
import configparser
from pathlib import Path
import argparse
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
from openai import OpenAI

# ---------- KONFIG (skupna) ----------

DB_DIR = "chroma_db"                 # ena baza za vse kvize
DEFAULT_DATA_DIR = "data/egipt"      # privzeti direktorij za Egipt kviz
DEFAULT_COLLECTION_NAME = "egipt"

EMBED_MODEL = "text-embedding-3-small"

# Preberi OPENAI_API_KEY iz okolja
load_dotenv()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment")

client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- POMOŽNE FUNKCIJE ----------

def load_documents(data_dir: str):
    """Prebere vse .txt datoteke iz mape in vrne seznam (ime, besedilo)."""
    docs = []
    data_path = Path(data_dir)
    if not data_path.is_dir():
        raise RuntimeError(f"DATA_DIR ne obstaja ali ni mapa: {data_dir}")
    for fname in os.listdir(data_dir):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(data_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append((fname, text))
    return docs


def simple_chunk(text, max_chars=800):
    """Zelo enostavno chunkanje: reži po znakovih."""
    text = text.replace("\n", " ").strip()
    chunks = []
    while text:
        chunk = text[:max_chars]
        text = text[max_chars:]
        chunks.append(chunk)
    return chunks


def embed_one(text: str):
    """Naredi embedding enega chunka besedila z OpenAI."""
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    )
    return resp.data[0].embedding


# ---------- GLAVNI DEL ----------

def main():
    parser = argparse.ArgumentParser(
        description="Zgradi Chroma indeks za en kviz (ena kolekcija) v skupni bazi."
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"Mapa z .txt datotekami (privzeto: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--collection",
        dest="collection_name",
        default=DEFAULT_COLLECTION_NAME,
        help=f"Ime Chroma kolekcije (privzeto: {DEFAULT_COLLECTION_NAME})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Pred dodajanjem pobriši obstoječo kolekcijo (če obstaja).",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    collection_name = args.collection_name

    print(f"Uporabljam DB_DIR={DB_DIR}")
    print(f"Uporabljam DATA_DIR={data_dir}")
    print(f"Ime kolekcije: {collection_name}")

    # 1. Inicializiraj ChromaDB (persistent client)
    client_chroma = chromadb.PersistentClient(
        path=DB_DIR,
        settings=Settings(allow_reset=True)
    )

    if args.reset:
        # zbriše VES indeks, pazljivo – pobriše tudi druge kolekcije
        # client_chroma.reset()
        # zato raje brišemo samo kolekcijo, če obstaja
        try:
            client_chroma.delete_collection(name=collection_name)
            print(f"Obstoječa kolekcija '{collection_name}' je bila pobrisana.")
        except Exception:
            print(f"Kolekcije '{collection_name}' ni bilo treba brisati (ne obstaja).")

    try:
        collection = client_chroma.get_collection(name=collection_name)
        print(f"Uporabljam obstoječo kolekcijo '{collection_name}'.")
    except Exception:
        collection = client_chroma.create_collection(name=collection_name)
        print(f"Ustvaril novo kolekcijo '{collection_name}'.")

    # 2. Naloži dokumente
    docs = load_documents(data_dir)
    print(f"Našel sem {len(docs)} datotek v {data_dir}.")

    ids = []
    texts = []
    metas = []

    doc_id_counter = 0

    for fname, text in docs:
        chunks = simple_chunk(text, max_chars=800)
        print(f"  {fname}: {len(chunks)} chunkov")
        for i, chunk in enumerate(chunks):
            doc_id = f"{fname}_{i}"
            ids.append(str(doc_id_counter))
            texts.append(chunk)
            metas.append({"source": fname, "chunk": i})
            doc_id_counter += 1

    if not texts:
        print("Ni najdenih chunkov (prazno). Končujem.")
        return

    # 3. Embeddingi za vse chunke
    embeddings = []
    for i, txt in enumerate(texts):
        print(f"Embedding {i+1}/{len(texts)} ...")
        emb = embed_one(txt)
        embeddings.append(emb)

    # 4. Shrani v zbirko
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metas,
        embeddings=embeddings,
    )

    print("Indeks (OpenAI) je zgrajen in shranjen v:", DB_DIR)
    print("Zbirka:", collection_name)


if __name__ == "__main__":
    main()
