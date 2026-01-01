import requests

OLLAMA = "http://192.168.1.38:11434"

q = "Kaj določa 10.a člen ZGD-1?"
r = requests.post(
    f"{OLLAMA}/api/embeddings",
    json={
        "model": "mxbai-embed-large:latest",
        "prompt": q
    }
)

qvec = r.json()["embedding"]
print(len(qvec))      # npr. 1024
print(qvec[:5])       # sanity check
print(qvec)
