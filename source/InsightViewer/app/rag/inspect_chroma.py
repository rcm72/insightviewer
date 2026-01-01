# filepath: /home/robert/insightViewer/source/InsightViewer/app/rag/inspect_chroma.py
import chromadb
from chromadb.config import Settings

DB_DIR = "chroma_db"

client = chromadb.PersistentClient(path=DB_DIR, settings=Settings())

print("Kolekcije v bazi:")
for coll in client.list_collections():
    print(" -", coll.name)

name = input("Vnesi ime kolekcije za vpogled (npr. egipt, egipt_oai, reinsurance_oai): ").strip()
if not name:
    exit()

collection = client.get_collection(name=name)

print(f"\nŠtevilo shranjenih elementov v kolekciji '{name}':", collection.count())

# preberi prvih N zapisov (n_results)
N = 5
res = collection.get(
    include=["documents", "metadatas"],
)

docs = res.get("documents", [])
metas = res.get("metadatas", [])

print(f"\nPrvih {min(N, len(docs))} dokumentov:")
for i, (doc, meta) in enumerate(zip(docs, metas)):
    if i >= N:
        break
    print(f"\n--- #{i} ---")
    print("META:", meta)
    print("DOC:", doc[:300].replace("\n", " "), "...")
