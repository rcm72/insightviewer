# filepath: /home/robert/insightViewer/source/InsightViewer/app/rag/inspect_collection_egipt.py
import chromadb
from chromadb.config import Settings

DB_DIR = "chroma_db"
COLLECTION_NAME = "egipt"  # ali "egipt_oai" ipd.

client = chromadb.PersistentClient(path=DB_DIR, settings=Settings())
coll = client.get_collection(name=COLLECTION_NAME)

print("Count:", coll.count())
res = coll.get(include=["documents", "metadatas"])
for i in range(min(5, len(res["documents"]))):
    print("----", i, "----")
    print("META:", res["metadatas"][i])
    print("DOC :", res["documents"][i][:300], "...")

