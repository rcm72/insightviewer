#!/usr/bin/env python3
"""
Test script za quiz_api - generira vprašanja iz Neo4j Chunk nodes z embedding-based semantic search
Primer uporabe:
    python3 test_quiz_api.py
    python3 test_quiz_api.py --query "ozračje in vreme"
    python3 test_quiz_api.py --random  # brez embeddings, samo naključna izbira
"""
import requests
import json
import argparse

API_BASE = "http://192.168.1.16:8001"

def test_semantic_search(query: str, id_rc: str = None):
    """Test semantic search endpoint"""
    print("\n" + "=" * 60)
    print(f"TEST SEMANTIČNEGA ISKANJA")
    print("=" * 60)
    print(f"Query: '{query}'")
    if id_rc:
        print(f"Omejeno na node: {id_rc}")
    
    params = {"query": query, "top_k": 5}
    if id_rc:
        params["id_rc"] = id_rc
    
    resp = requests.get(f"{API_BASE}/quiz/semantic_search", params=params)
    
    if resp.status_code != 200:
        print(f"Napaka {resp.status_code}: {resp.text}")
        return
    
    data = resp.json()
    results = data.get("results", [])
    
    print(f"\nNajdenih {len(results)} rezultatov:")
    for i, chunk in enumerate(results, 1):
        score = chunk.get("similarity_score", 0)
        text = chunk.get("text", "")
        print(f"\n{i}. Similarity: {score:.4f}")
        print(f"   Chunk ID: {chunk.get("id_rc")}")
        print(f"   Text: {text[:150]}...")
    
    print("=" * 60)

def test_quiz(use_semantic: bool = True, query: str = None, num_questions: int = 3):
    print("=" * 60)
    print(f"KVIZ TEST - {'Semantic Search' if use_semantic else 'Random Selection'}")
    print("=" * 60)
    
    # 1. Pridobi seznam Course nodes
    print("\n1. Nalagam Course vozlišča...")
    resp = requests.get(f"{API_BASE}/quiz/nodes?label=Course")
    data = resp.json()
    
    if not data.get("success") or not data.get("nodes"):
        print("Napaka: Ni najdenih Course vozlišč")
        return
    
    nodes = data["nodes"]
    print(f"   Najdenih {len(nodes)} vozlišč:")
    for i, node in enumerate(nodes, 1):
        print(f"   {i}. {node['name']} (id_rc: {node['id_rc']})")
    
    # 2. Izberi prvo vozlišče (Geografija)
    node = nodes[0]
    print(f"\n2. Izbrano vozlišče: {node['name']}")
    
    # 2b. Optional: test semantic search first
    if use_semantic and query:
        test_semantic_search(query, node['id_rc'])
    
    # 3. Generiraj vprašanja
    print(f"\n3. Generiram {num_questions} vprašanj...")
    
    params = {
        "id_rc": node['id_rc'],
        "num_questions": num_questions,
        "use_semantic": use_semantic
    }
    if query:
        params["query"] = query
        print(f"   Semantic query: '{query}'")
    
    resp = requests.get(f"{API_BASE}/quiz/start", params=params)
    
    if resp.status_code != 200:
        print(f"   Napaka {resp.status_code}: {resp.text}")
        return
    
    quiz_data = resp.json()
    questions = quiz_data.get("questions", [])
    method = quiz_data.get("method", "unknown")
    embedding_model = quiz_data.get("embedding_model")
    
    print(f"   Metoda: {method}")
    if embedding_model:
        print(f"   Embedding model: {embedding_model}")
    
    if not questions:
        print("   Napaka: Ni bilo mogoče generirati vprašanj (ni Chunk nodes?)")
        return
    
    print(f"   Generirano {len(questions)} vprašanj\n")
    
    # 4. Prikaži vprašanja
    print("=" * 60)
    for i, q in enumerate(questions, 1):
        print(f"\nVPRAŠANJE {i}:")
        
        # Show similarity score if available
        if "similarity_score" in q:
            print(f"  [Similarity: {q['similarity_score']:.4f}]")
        
        print(f"  {q['question']}")
        print(f"\nKONTEKST (odstavek iz katerega je vprašanje):")
        context = q['context']
        if len(context) > 300:
            print(f"  {context[:300]}...")
        else:
            print(f"  {context}")
        
        print(f"\nIDEALEN ODGOVOR:")
        print(f"  {q['ideal_answer']}")
        print("-" * 60)
    
    # 5. Test ocenjevanja (primer)
    print("\n5. Test ocenjevanja...")
    
    # Test 1: Slab odgovor
    print("\n   Test 1: Slab odgovor")
    test_payload = {
        "context": questions[0]["context"],
        "question": questions[0]["question"],
        "ideal_answer": questions[0]["ideal_answer"],
        "student_answer": "Ne vem."
    }
    resp = requests.post(f"{API_BASE}/quiz/grade", json=test_payload)
    grade = resp.json()
    print(f"   Odgovor: 'Ne vem.'")
    print(f"   Ocena: {grade.get('score', '?')} / 5")
    print(f"   Feedback: {grade.get('feedback', 'N/A')}")
    
    # Test 2: Dober odgovor (uporabi idealen odgovor)
    print("\n   Test 2: Dober odgovor (idealen)")
    test_payload["student_answer"] = questions[0]["ideal_answer"]
    resp = requests.post(f"{API_BASE}/quiz/grade", json=test_payload)
    grade = resp.json()
    print(f"   Odgovor: '{questions[0]['ideal_answer'][:60]}...'")
    print(f"   Ocena: {grade.get('score', '?')} / 5")
    print(f"   Feedback: {grade.get('feedback', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("KVIZ TEST KONČAN")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test quiz API with semantic search")
    parser.add_argument("--random", action="store_true", help="Use random selection instead of semantic search")
    parser.add_argument("--query", type=str, help="Semantic search query (e.g., 'ozračje in vreme')")
    parser.add_argument("--num", type=int, default=3, help="Number of questions (default: 3)")
    parser.add_argument("--test-search", type=str, help="Just test semantic search with given query")
    
    args = parser.parse_args()
    
    try:
        if args.test_search:
            test_semantic_search(args.test_search)
        else:
            test_quiz(
                use_semantic=not args.random,
                query=args.query,
                num_questions=args.num
            )
    except Exception as e:
        print(f"Napaka: {e}")
        import traceback
        traceback.print_exc()
