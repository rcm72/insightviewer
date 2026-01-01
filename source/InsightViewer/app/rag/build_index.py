import os
import textwrap

import chromadb
from chromadb.config import Settings
import ollama

DATA_DIR = "data"
DB_DIR = "chroma_db"
EMBED_MODEL = "nomic-embed-text"
OLLAMA_HOST = "http://192.168.1.13:11434"

# create an Ollama client pointing to your host
ollama_client = ollama.Client(host=OLLAMA_HOST)

def load_documents(data_dir):
    docs = []
    for fname in os.listdir(data_dir):
        if not fname.endswith(".txt"):
            continue
        path = os.path.join(data_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append((fname, text))
    return docs

def simple_chunk(text, max_chars=800):
    # zelo enostavno: razrežemo besedilo na kose po max_chars
    text = text.replace("\n", " ").strip()
    chunks = []
    while text:
        chunk = text[:max_chars]
        text = text[max_chars:]
        chunks.append(chunk)
    return chunks

def embed_one(text):
    out = ollama_client.embeddings(
        model=EMBED_MODEL,
        prompt=text,
    )
    return out["embedding"]

def main():
    # 1. inicializiraj ChromaDB
    client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(allow_reset=True))
    # po potrebi reset baze
    client.reset()

    collection = client.create_collection(name="egipt")

    # 2. naloži dokumente
    docs = load_documents(DATA_DIR)
    print(f"Našel sem {len(docs)} datotek.")

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

    # 3. za vsak chunk naredimo embedding in shranimo v ChromaDB
    embeddings = []
    for i, txt in enumerate(texts):
        print(f"Embedding {i+1}/{len(texts)} ...")
        emb = embed_one(txt)
        embeddings.append(emb)

    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metas,
        embeddings=embeddings,
    )

    print("Indeks je zgrajen in shranjen v:", DB_DIR)

if __name__ == "__main__":
    main()
