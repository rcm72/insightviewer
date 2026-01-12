import os
import json
import random
import configparser
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import csv
import requests
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase

# ------- Konfiguracija -------
LLM_MODEL = None

config = configparser.ConfigParser()
BASE_DIR = Path(__file__).resolve().parents[2]
config_path = BASE_DIR / "config.ini"
print("config_path:", config_path)
config.read(config_path)

# Ollama config from [OLLAMA]
OLLAMA_BASE = config.get("OLLAMA", "BASE", fallback="http://192.168.1.38:11434")
EMB_MODEL = config.get("OLLAMA", "EMB_MODEL", fallback="mxbai-embed-large:latest")
LLM_MODEL = config.get("OLLAMA", "MODEL", fallback="qwen2.5:14b")
try:
    TOP_K = int(config.get("OLLAMA", "TOP_K", fallback="8"))
except Exception:
    TOP_K = 8
OLLAMA_AUTH = os.environ.get("OLLAMA_AUTH") or config.get("OLLAMA", "AUTH", fallback=None)

# Neo4j config
NEO4J_URI = config.get("NEO4J", "URI")
NEO4J_USER = config.get("NEO4J", "USERNAME")
NEO4J_PASS = config.get("NEO4J", "PASSWORD")
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

# Results storage path
RESULTS_CSV_PATH = Path(__file__).parent / "quiz_results.csv"

# ------- Embedding helpers -------
def get_embedding(text: str) -> List[float]:
    """
    Get embedding vector for text using mxbai-embed-large model.
    """
    url = f"{OLLAMA_BASE}/api/embeddings"
    payload = {
        "model": EMB_MODEL,
        "prompt": text
    }
    headers = {"Content-Type": "application/json"}
    if OLLAMA_AUTH:
        headers["Authorization"] = f"Bearer {OLLAMA_AUTH}"
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        embedding = data.get("embedding")
        if embedding and isinstance(embedding, list):
            return embedding
        else:
            raise ValueError(f"Invalid embedding response: {data}")
    except Exception as e:
        print(f"Error getting embedding: {e}")
        raise

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    """
    import math
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)

def ollama_generate(system_prompt: str, user_prompt: str, temperature: float = 0.5, max_tokens: int = 512) -> str:
    url = f"{OLLAMA_BASE}/api/generate"
    prompt = f"SYSTEM:\n{system_prompt.strip()}\n\nUSER:\n{user_prompt.strip()}\n"
    payload = {
        "model": LLM_MODEL, 
        "prompt": prompt, 
        "temperature": temperature, 
        "num_predict": max_tokens,
        "stream": False  # IMPORTANT: disable streaming to get full response
    }
    headers = {"Content-Type": "application/json"}
    if OLLAMA_AUTH:
        headers["Authorization"] = f"Bearer {OLLAMA_AUTH}"
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        
        # Parse JSON response
        data = resp.json()
        
        # Ollama API returns response in "response" field
        if "response" in data:
            return data["response"].strip()
        
        # Fallback for other formats
        if "choices" in data and isinstance(data["choices"], list) and data["choices"]:
            c = data["choices"][0]
            if isinstance(c, dict):
                if "message" in c and isinstance(c["message"], dict) and "content" in c["message"]:
                    return c["message"]["content"].strip()
                elif "content" in c:
                    return c["content"].strip()
        
        # Last resort
        return str(data).strip()
        
    except requests.exceptions.RequestException as e:
        print(f"Error calling Ollama API: {e}")
        return json.dumps({"error": f"ollama request failed: {e}"})
    except json.JSONDecodeError as e:
        print(f"Error parsing Ollama response: {e}")
        return resp.text if resp else ""

# ------- Neo4j helpers -------

def get_chunks_for_node(id_rc: str, max_depth: int = 10) -> List[Dict[str, Any]]:
    """
    Poišče vse CHUNK node-e dosegljive iz danega node-a (po id_rc).
    Vrne seznam dict-ov: {"id_rc": str, "text": str, ...}.
    """
    # Neo4j ne dovoljuje parametra za dolžino poti, zato uporabimo f-string
    # Label je 'Chunk' (ne 'CHUNK')
    cypher = f"""
    MATCH (start {{id_rc: $id_rc}})
    MATCH path=(start)-[*1..{max_depth}]->(c:Chunk)
    RETURN DISTINCT c.id_rc AS id_rc, c.text AS text, properties(c) AS props
    LIMIT 1000
    """
    with neo4j_driver.session() as session:
        result = session.run(cypher, id_rc=id_rc)
        chunks = []
        for record in result:
            chunks.append({
                "id_rc": record["id_rc"],
                "text": record["text"] or "",
                "props": dict(record["props"]) if record["props"] else {}
            })
    return chunks

def semantic_search_chunks(query: str, id_rc: str = None, top_k: int = None) -> List[Dict[str, Any]]:
    """
    Semantic search using embedding similarity.
    If id_rc is provided, searches only within chunks connected to that node.
    Otherwise searches all chunks.
    """
    if top_k is None:
        top_k = TOP_K
    
    # Get query embedding
    query_embedding = get_embedding(query)
    
    # Get candidate chunks
    if id_rc:
        chunks = get_chunks_for_node(id_rc)
    else:
        # Get all chunks
        cypher = """
        MATCH (c:Chunk)
        WHERE c.text IS NOT NULL AND c.text <> ''
        RETURN c.id_rc AS id_rc, c.text AS text, properties(c) AS props
        LIMIT 1000
        """
        with neo4j_driver.session() as session:
            result = session.run(cypher)
            chunks = []
            for record in result:
                chunks.append({
                    "id_rc": record["id_rc"],
                    "text": record["text"] or "",
                    "props": dict(record["props"]) if record["props"] else {}
                })
    
    if not chunks:
        return []
    
    # Calculate similarity for each chunk
    chunk_scores = []
    for chunk in chunks:
        text = chunk.get("text", "")
        if not text or len(text) < 20:
            continue
        
        try:
            chunk_embedding = get_embedding(text)
            similarity = cosine_similarity(query_embedding, chunk_embedding)
            chunk_scores.append((chunk, similarity))
        except Exception as e:
            print(f"Error processing chunk {chunk.get('id_rc')}: {e}")
            continue
    
    # Sort by similarity (descending)
    chunk_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Return top_k chunks with their similarity scores
    results = []
    for chunk, score in chunk_scores[:top_k]:
        chunk_with_score = chunk.copy()
        chunk_with_score["similarity_score"] = score
        results.append(chunk_with_score)
    
    return results

def search_nodes_by_label(label: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Vrne node-e z dano label (npr. 'Course', 'Chapter', 'Section', 'SubSection').
    """
    cypher = f"""
    MATCH (n:`{label}`)
    RETURN n.id_rc AS id_rc, n.name AS name, properties(n) AS props
    LIMIT $limit
    """
    with neo4j_driver.session() as session:
        result = session.run(cypher, limit=limit)
        nodes = []
        for record in result:
            nodes.append({
                "id_rc": record["id_rc"],
                "name": record.get("name") or record["id_rc"],
                "props": dict(record["props"]) if record["props"] else {}
            })
    return nodes

# ------- LLM helpers -------

def generate_question_from_context(context_text: str) -> Dict[str, str]:
    system_prompt = """
Si učitelj geografije. Generiraj ENO kratko, jasno vprašanje.

PRAVILA:
1. Vprašanje mora biti KRATKO (max 10 besed)
2. Vprašanje mora biti razumljivo BREZ konteksta
3. Uporabi KONKRETNA IMENA (ne zaimkov: "to", "oni", "njimi")
4. Začni z: "Kaj je...", "Definiraj...", "Opiši...", "Kako..."

PRIMERI (upoštevaj format):
Kontekst: "Neurje je močna padavina s formi vetra."
✅ DOBRO: {"question": "Kaj je neurje?", "ideal_answer": "Neurje je močna padavina s formi vetra."}
❌ SLABO: {"question": "Kaj je to?", ...}

Kontekst: "Vreme označuje stanje v ozračju."
✅ DOBRO: {"question": "Kaj označuje vreme?", "ideal_answer": "Vreme označuje stanje v ozračju."}
❌ SLABO: {"question": "Povej o tem.", ...}

Format: {"question":"...", "ideal_answer":"..."}
"""
    user_prompt = f"""
Kontekst:
{context_text[:500]}

Generiraj ENO konkretno vprašanje z jasnim odgovorom.
Vrni JSON: {{"question":"...", "ideal_answer":"..."}}
"""
    
    print(f"\n[DEBUG] Generating question from context: {context_text[:100]}...")
    content = ollama_generate(system_prompt, user_prompt, temperature=0.4, max_tokens=300)
    print(f"[DEBUG] LLM raw response: {content[:300]}")
    
    # Try parsing JSON response
    try:
        # Strip any markdown formatting and whitespace
        content_clean = content.strip()
        
        # Remove markdown code fences
        if content_clean.startswith("```"):
            import re
            content_clean = re.sub(r'^```(?:json)?\s*', '', content_clean)
            content_clean = re.sub(r'\s*```$', '', content_clean)
            content_clean = content_clean.strip()
        
        # Try to find JSON object in the response
        import re
        json_match = re.search(r'\{[^}]+\}', content_clean, re.DOTALL)
        if json_match:
            content_clean = json_match.group(0)
        
        data = json.loads(content_clean)
        
        # Validate that we got proper fields
        if not data.get("question") or not data.get("ideal_answer"):
            raise ValueError("Missing required fields in JSON response")
        
        question = data["question"].strip()
        answer = data["ideal_answer"].strip()
        
        # Additional validation: question quality checks
        question_lower = question.lower()
        
        # Check minimum length
        if len(question) < 10:
            raise ValueError("Question too short")
        
        # Check for bad question patterns
        bad_patterns = [
            "o čem govori",
            "kaj piše",
            "povej o",
            "vsebina odstavka",
            "tema besedila",
            "glavna tema",
            " to?",  # "Kaj je to?"
            " ta?",  # "Kaj je ta?"
        ]
        if any(pattern in question_lower for pattern in bad_patterns):
            print(f"[DEBUG] Question failed bad pattern check: {question}")
            raise ValueError(f"Question is too generic or context-dependent: {question}")
        
        # Check for pronouns without referent
        pronoun_patterns = [
            r'\b(to|ta|oni|njimi|njem|njej)\b\?',  # ends with pronoun + ?
        ]
        for pattern in pronoun_patterns:
            if re.search(pattern, question_lower):
                print(f"[DEBUG] Question contains bad pronoun: {question}")
                raise ValueError(f"Question uses pronouns without clear referent: {question}")
        
        # Check if question has proper structure (starts with question word or is a command)
        good_starts = ["kaj", "definiraj", "opiši", "razloži", "kako", "zakaj", "kdaj", "kje", "kateri", "katera", "katero"]
        if not any(question_lower.startswith(start) for start in good_starts):
            print(f"[DEBUG] Question doesn't start properly: {question}")
            raise ValueError(f"Question doesn't start with appropriate question word: {question}")
        
        print(f"[DEBUG] Valid question generated: {question}")
        return {"question": question, "ideal_answer": answer}
        
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[WARNING] LLM response parsing/validation failed ({e}).")
        print(f"[WARNING] Using fallback. Full response: {content}")
        
        # Enhanced fallback: extract concepts more intelligently
        import re
        
        # Strategy 1: Look for definitions (strongest signal)
        definition_patterns = [
            r'([A-ZČŠŽ][a-zčšžćđ]+(?:\s+[a-zčšžćđ]+){0,3})\s+je\s+([^.]+\.)',
            r'([A-ZČŠŽ][a-zčšžćđ]+(?:\s+[a-zčšžćđ]+){0,3})\s+pomeni\s+([^.]+\.)',
            r'([A-ZČŠŽ][a-zčšžćđ]+(?:\s+[a-zčšžćđ]+){0,3})\s+predstavlja\s+([^.]+\.)',
            r'([A-ZČŠŽ][a-zčšžćđ]+(?:\s+[a-zčšžćđ]+){0,3})\s+označuje\s+([^.]+\.)',
            r'([A-ZČŠŽ][a-zčšžćđ]+(?:\s+[a-zčšžćđ]+){0,3})\s+imenujemo\s+([^.]+\.)',
        ]
        
        concept = None
        definition = None
        
        for pattern in definition_patterns:
            match = re.search(pattern, context_text)
            if match:
                concept = match.group(1).strip()
                full_match = match.group(0)
                # Skip if concept is too short or too generic
                if len(concept) > 3 and concept.lower() not in ['to', 'kaj', 'kako', 'zakaj', 'nato', 'tudi', 'zato']:
                    definition = full_match
                    print(f"[DEBUG] Fallback found definition: {concept}")
                    break
        
        if concept and definition:
            return {
                "question": f"Kaj je {concept.lower()}?",
                "ideal_answer": definition.strip()
            }
        
        # Strategy 2: Look for key terms at start of sentences
        sentences = [s.strip() for s in context_text.split('.') if len(s.strip()) > 30]
        if sentences:
            first_sentence = sentences[0]
            # Extract first noun phrase (capitalized words)
            words = first_sentence.split()
            concept_words = []
            for word in words:
                if word and len(word) > 3 and word[0].isupper():
                    concept_words.append(word)
                    if len(concept_words) >= 2:
                        break
            
            if concept_words:
                concept = ' '.join(concept_words)
                return {
                    "question": f"Razloži: {concept}",
                    "ideal_answer": first_sentence
                }
        
        # Last resort: use first sentence as context
        if sentences:
            return {
                "question": "Razloži glavni koncept iz učne snovi.",
                "ideal_answer": sentences[0]
            }
        else:
            # If all else fails
            return {
                "question": "Razloži učno snov.",
                "ideal_answer": context_text[:200].strip()
            }

def grade_answer(context_text: str, question: str, ideal_answer: str, student_answer: str) -> Dict[str, Any]:
    system_prompt = """
Ti si učitelj, ki ocenjuje odgovore učencev.
Oceni odgovor na skali 1..5 (1 = popolnoma napačno, 5 = popolnoma pravilen) in podaj kratko utemeljitev.
Vrni strogo JSON: {"score": <int 1..5>, "feedback": "..."}.
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

Vrni JSON: {{"score": <1-5>, "feedback": "..."}}
"""
    
    print(f"\n[DEBUG] Grading answer: {student_answer[:100]}...")
    content = ollama_generate(system_prompt, user_prompt, temperature=0.2, max_tokens=512)
    print(f"[DEBUG] Grading LLM raw response: {content[:300]}")
    
    try:
        # Strip any markdown formatting and whitespace
        content_clean = content.strip()
        
        # Remove markdown code fences
        if content_clean.startswith("```"):
            import re
            content_clean = re.sub(r'^```(?:json)?\s*', '', content_clean)
            content_clean = re.sub(r'\s*```$', '', content_clean)
            content_clean = content_clean.strip()
        
        # Try to find JSON object in the response
        import re
        json_match = re.search(r'\{[^}]+\}', content_clean, re.DOTALL)
        if json_match:
            content_clean = json_match.group(0)
        
        data = json.loads(content_clean)
        score = int(data.get("score", 0))
        if score < 1: score = 1
        if score > 5: score = 5
        feedback = str(data.get("feedback", "")).strip()
        
        if not feedback:
            feedback = "Odgovor ocenjen."
        
        print(f"[DEBUG] Grade parsed successfully: score={score}")
        return {"score": score, "feedback": feedback}
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"[WARNING] Grading response parsing failed ({e}).")
        print(f"[WARNING] Full response: {content}")
        
        # Fallback: try to extract score and feedback from text
        import re
        
        # Try to find score in text (e.g., "score: 3", "ocena: 3", "3/5")
        score_patterns = [
            r'["\']?score["\']?\s*:\s*(\d)',
            r'["\']?ocena["\']?\s*:\s*(\d)',
            r'(\d)\s*/\s*5',
        ]
        
        score = 1  # default
        for pattern in score_patterns:
            match = re.search(pattern, content.lower())
            if match:
                try:
                    score = int(match.group(1))
                    if 1 <= score <= 5:
                        print(f"[DEBUG] Extracted score from text: {score}")
                        break
                except ValueError:
                    pass
        
        # Try to extract feedback
        feedback_match = re.search(r'["\']?feedback["\']?\s*:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
        if feedback_match:
            feedback = feedback_match.group(1).strip()
        else:
            # Use the entire response as feedback if it looks reasonable
            if len(content) < 500 and len(content) > 10:
                feedback = content.strip()
            else:
                feedback = "Odgovor je bil ocenjen, vendar ni bilo mogoče pridobiti podrobne povratne informacije."
        
        print(f"[DEBUG] Fallback grade: score={score}, feedback={feedback[:100]}")
        return {"score": score, "feedback": feedback}

# ------- Results storage helpers -------

def save_result_to_csv(result_data: Dict[str, Any]) -> None:
    """
    Save quiz result to CSV file.
    """
    try:
        # Ensure parent directory exists
        RESULTS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file exists to determine if we need to write header
        file_exists = RESULTS_CSV_PATH.exists()
        
        with open(RESULTS_CSV_PATH, 'a', newline='', encoding='utf-8') as f:
            fieldnames = [
                'session_id', 'timestamp', 'node_id_rc', 'node_name', 'quiz_type',
                'total_questions', 'total_score', 'max_score', 'average_score',
                'student_name', 'question', 'student_answer', 'ideal_answer', 
                'score', 'feedback'
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            if not file_exists:
                writer.writeheader()
            
            # Write each question result as a row
            for q_result in result_data.get('results', []):
                writer.writerow({
                    'session_id': result_data.get('session_id', ''),
                    'timestamp': result_data.get('timestamp', ''),
                    'node_id_rc': result_data.get('node_id_rc', ''),
                    'node_name': result_data.get('node_name', ''),
                    'quiz_type': result_data.get('quiz_type', 'llm'),
                    'total_questions': result_data.get('total_questions', 0),
                    'total_score': result_data.get('total_score', 0),
                    'max_score': result_data.get('max_score', 0),
                    'average_score': result_data.get('average_score', 0),
                    'student_name': result_data.get('student_name', 'Anonymous'),
                    'question': q_result.get('question', ''),
                    'student_answer': q_result.get('answer', ''),
                    'ideal_answer': q_result.get('ideal_answer', ''),
                    'score': q_result.get('score', 0),
                    'feedback': q_result.get('feedback', '')
                })
        
        print(f"[INFO] Saved quiz result to CSV: {RESULTS_CSV_PATH}")
    except Exception as e:
        print(f"[ERROR] Failed to save result to CSV: {e}")
        raise

def save_result_to_neo4j(result_data: Dict[str, Any]) -> str:
    """
    Save quiz result to Neo4j as QuizSession and QuizResult nodes.
    Returns the created session_id.
    """
    try:
        session_id = result_data.get('session_id')
        timestamp = result_data.get('timestamp')
        
        with neo4j_driver.session() as session:
            # Create QuizSession node
            session_cypher = """
            CREATE (qs:QuizSession {
                session_id: $session_id,
                timestamp: $timestamp,
                node_id_rc: $node_id_rc,
                node_name: $node_name,
                quiz_type: $quiz_type,
                student_name: $student_name,
                total_questions: $total_questions,
                total_score: $total_score,
                max_score: $max_score,
                average_score: $average_score
            })
            RETURN qs.session_id AS session_id
            """
            
            session_result = session.run(session_cypher,
                session_id=session_id,
                timestamp=timestamp,
                node_id_rc=result_data.get('node_id_rc', ''),
                node_name=result_data.get('node_name', ''),
                quiz_type=result_data.get('quiz_type', 'llm'),
                student_name=result_data.get('student_name', 'Anonymous'),
                total_questions=result_data.get('total_questions', 0),
                total_score=result_data.get('total_score', 0),
                max_score=result_data.get('max_score', 0),
                average_score=result_data.get('average_score', 0)
            )
            
            # Create QuizResult nodes for each question
            for i, q_result in enumerate(result_data.get('results', [])):
                result_cypher = """
                MATCH (qs:QuizSession {session_id: $session_id})
                CREATE (qr:QuizResult {
                    session_id: $session_id,
                    question_number: $question_number,
                    question: $question,
                    student_answer: $student_answer,
                    ideal_answer: $ideal_answer,
                    score: $score,
                    feedback: $feedback
                })
                CREATE (qs)-[:HAS_RESULT]->(qr)
                """
                
                session.run(result_cypher,
                    session_id=session_id,
                    question_number=i + 1,
                    question=q_result.get('question', ''),
                    student_answer=q_result.get('answer', ''),
                    ideal_answer=q_result.get('ideal_answer', ''),
                    score=q_result.get('score', 0),
                    feedback=q_result.get('feedback', '')
                )
            
            # Link to the original node if exists
            link_cypher = """
            MATCH (qs:QuizSession {session_id: $session_id})
            MATCH (n {id_rc: $node_id_rc})
            MERGE (n)-[:HAS_QUIZ_SESSION]->(qs)
            """
            try:
                session.run(link_cypher, 
                    session_id=session_id, 
                    node_id_rc=result_data.get('node_id_rc', ''))
            except Exception as e:
                print(f"[WARNING] Could not link quiz session to node: {e}")
        
        print(f"[INFO] Saved quiz result to Neo4j: session_id={session_id}")
        return session_id
        
    except Exception as e:
        print(f"[ERROR] Failed to save result to Neo4j: {e}")
        raise

def get_quiz_results(limit: int = 50, student_name: str = None) -> List[Dict[str, Any]]:
    """
    Get quiz results from Neo4j.
    """
    try:
        with neo4j_driver.session() as session:
            cypher = """
            MATCH (qs:QuizSession)
            OPTIONAL MATCH (qs)-[:HAS_RESULT]->(qr:QuizResult)
            """
            
            if student_name:
                cypher += " WHERE qs.student_name = $student_name"
            
            cypher += """
            RETURN qs.session_id AS session_id,
                   qs.timestamp AS timestamp,
                   qs.node_name AS node_name,
                   qs.quiz_type AS quiz_type,
                   qs.student_name AS student_name,
                   qs.total_questions AS total_questions,
                   qs.total_score AS total_score,
                   qs.max_score AS max_score,
                   qs.average_score AS average_score,
                   collect({
                       question_number: qr.question_number,
                       question: qr.question,
                       student_answer: qr.student_answer,
                       ideal_answer: qr.ideal_answer,
                       score: qr.score,
                       feedback: qr.feedback
                   }) AS results
            ORDER BY qs.timestamp DESC
            LIMIT $limit
            """
            
            params = {'limit': limit}
            if student_name:
                params['student_name'] = student_name
            
            result = session.run(cypher, **params)
            
            sessions = []
            for record in result:
                sessions.append({
                    'session_id': record['session_id'],
                    'timestamp': record['timestamp'],
                    'node_name': record['node_name'],
                    'quiz_type': record['quiz_type'],
                    'student_name': record['student_name'],
                    'total_questions': record['total_questions'],
                    'total_score': record['total_score'],
                    'max_score': record['max_score'],
                    'average_score': record['average_score'],
                    'results': [r for r in record['results'] if r.get('question')]
                })
            
            return sessions
            
    except Exception as e:
        print(f"[ERROR] Failed to get quiz results from Neo4j: {e}")
        raise

# ------- FastAPI app -------

quiz_api = FastAPI(title="RAG Quiz API (Neo4j + Embeddings)")

quiz_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------- API endpoints -------

@quiz_api.get("/quiz/nodes")
def api_list_nodes(label: str = Query("Course", description="Node label (npr. Course, Chapter, Section, SubSection)")):
    """
    Vrne seznam node-ov z dano label, da uporabnik lahko izbere enega.
    """
    try:
        nodes = search_nodes_by_label(label, limit=200)
        return {"success": True, "nodes": nodes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@quiz_api.get("/quiz/start")
def api_quiz_start(
    id_rc: str = Query(..., description="id_rc izbranega node-a"),
    num_questions: int = Query(5, description="Število vprašanj"),
    query: str = Query(None, description="Semantic search query (optional) - if provided, uses embedding-based search"),
    use_semantic: bool = Query(True, description="Use semantic search with embeddings (default: True)")
):
    """
    Pripravi kviz: poišče chunke z embedding-based semantic search ali graph traversal.
    Če je podan 'query', uporabi semantično iskanje za izbiro najbolj relevantnih chunk-ov.
    Če use_semantic=True, uporabi node name kot query za semantično iskanje.
    Sicer naključno izbere chunk-e iz grafa.
    """
    try:
        if query or use_semantic:
            # Use semantic search with embeddings
            if not query:
                # Get node name to use as search query
                cypher = "MATCH (n {id_rc: $id_rc}) RETURN n.name AS name, n.title AS title"
                with neo4j_driver.session() as session:
                    result = session.run(cypher, id_rc=id_rc)
                    record = result.single()
                    if record:
                        query = record.get("name") or record.get("title") or "educational content"
                    else:
                        query = "educational content"
            
            print(f"Using semantic search with query: '{query}'")
            selected = semantic_search_chunks(query, id_rc=id_rc, top_k=num_questions)
            
            if not selected:
                # Fallback to random selection
                print("Semantic search returned no results, falling back to random selection")
                chunks = get_chunks_for_node(id_rc)
                if not chunks:
                    raise HTTPException(status_code=404, detail="Ni najdenih CHUNK node-ov za ta node.")
                selected = random.sample(chunks, min(num_questions, len(chunks)))
        else:
            # Original method: random selection from graph traversal
            chunks = get_chunks_for_node(id_rc)
            if not chunks:
                raise HTTPException(status_code=404, detail="Ni najdenih CHUNK node-ov za ta node.")
            
            # Naključno izberi max num_questions chunk-ov
            selected = random.sample(chunks, min(num_questions, len(chunks)))
        
        questions = []
        for chunk in selected:
            text = chunk.get("text", "")
            if not text or len(text) < 20:
                continue
            q_data = generate_question_from_context(text)
            question_obj = {
                "chunk_id_rc": chunk["id_rc"],
                "context": text,
                "question": q_data["question"],
                "ideal_answer": q_data["ideal_answer"]
            }
            # Include similarity score if available
            if "similarity_score" in chunk:
                question_obj["similarity_score"] = chunk["similarity_score"]
            questions.append(question_obj)
        
        return {
            "success": True,
            "node_id_rc": id_rc,
            "query": query,
            "method": "semantic_search" if (query or use_semantic) else "random",
            "embedding_model": EMB_MODEL,
            "questions": questions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@quiz_api.post("/quiz/grade")
def api_quiz_grade(payload: Dict[str, Any]):
    """
    Oceni en odgovor.
    Pričakuje JSON:
    {
      "context": "...",
      "question": "...",
      "ideal_answer": "...",
      "student_answer": "..."
    }
    """
    required = ["context", "question", "ideal_answer", "student_answer"]
    if not all(k in payload for k in required):
        raise HTTPException(status_code=400, detail="Missing fields in payload.")
    
    res = grade_answer(
        payload["context"],
        payload["question"],
        payload["ideal_answer"],
        payload["student_answer"],
    )
    return res

@quiz_api.get("/quiz/semantic_search")
def api_semantic_search(
    query: str = Query(..., description="Search query"),
    id_rc: str = Query(None, description="Optional: limit search to chunks connected to this node"),
    top_k: int = Query(None, description="Number of results to return")
):
    """
    Test endpoint for semantic search using embeddings.
    Returns chunks most similar to the query.
    """
    try:
        results = semantic_search_chunks(query, id_rc=id_rc, top_k=top_k)
        return {
            "success": True,
            "query": query,
            "embedding_model": EMB_MODEL,
            "top_k": top_k or TOP_K,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@quiz_api.post("/quiz/submit")
def api_submit_quiz(payload: Dict[str, Any] = Body(...)):
    """
    Submit complete quiz results for storage.
    Saves to both CSV and Neo4j.
    
    Expected JSON:
    {
      "node_id_rc": "...",
      "node_name": "...",
      "student_name": "Anonymous",
      "quiz_type": "llm",
      "results": [
        {
          "question": "...",
          "answer": "...",
          "ideal_answer": "...",
          "score": 3,
          "feedback": "..."
        },
        ...
      ]
    }
    """
    try:
        import uuid
        
        # Generate session ID and timestamp
        session_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Calculate totals
        results = payload.get('results', [])
        total_questions = len(results)
        total_score = sum(r.get('score', 0) for r in results)
        max_score = total_questions * 5
        average_score = round(total_score / total_questions, 2) if total_questions > 0 else 0
        
        # Prepare result data
        result_data = {
            'session_id': session_id,
            'timestamp': timestamp,
            'node_id_rc': payload.get('node_id_rc', ''),
            'node_name': payload.get('node_name', ''),
            'student_name': payload.get('student_name', 'Anonymous'),
            'quiz_type': payload.get('quiz_type', 'llm'),
            'total_questions': total_questions,
            'total_score': total_score,
            'max_score': max_score,
            'average_score': average_score,
            'results': results
        }
        
        # Save to both CSV and Neo4j
        save_result_to_csv(result_data)
        save_result_to_neo4j(result_data)
        
        return {
            "success": True,
            "session_id": session_id,
            "timestamp": timestamp,
            "total_score": total_score,
            "max_score": max_score,
            "average_score": average_score,
            "message": "Results saved successfully to CSV and Neo4j"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to submit quiz: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@quiz_api.get("/quiz/results")
def api_get_results(
    limit: int = Query(50, description="Number of results to return"),
    student_name: str = Query(None, description="Filter by student name")
):
    """
    Get quiz results from Neo4j.
    Returns recent quiz sessions with details.
    """
    try:
        results = get_quiz_results(limit=limit, student_name=student_name)
        return {
            "success": True,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        print(f"[ERROR] Failed to get results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@quiz_api.get("/quiz/results/{session_id}")
def api_get_result_by_id(session_id: str):
    """
    Get specific quiz result by session ID.
    """
    try:
        with neo4j_driver.session() as session:
            cypher = """
            MATCH (qs:QuizSession {session_id: $session_id})
            OPTIONAL MATCH (qs)-[:HAS_RESULT]->(qr:QuizResult)
            RETURN qs.session_id AS session_id,
                   qs.timestamp AS timestamp,
                   qs.node_name AS node_name,
                   qs.node_id_rc AS node_id_rc,
                   qs.quiz_type AS quiz_type,
                   qs.student_name AS student_name,
                   qs.total_questions AS total_questions,
                   qs.total_score AS total_score,
                   qs.max_score AS max_score,
                   qs.average_score AS average_score,
                   collect({
                       question_number: qr.question_number,
                       question: qr.question,
                       student_answer: qr.student_answer,
                       ideal_answer: qr.ideal_answer,
                       score: qr.score,
                       feedback: qr.feedback
                   }) AS results
            """
            
            result = session.run(cypher, session_id=session_id)
            record = result.single()
            
            if not record:
                raise HTTPException(status_code=404, detail="Quiz session not found")
            
            return {
                "success": True,
                "session_id": record['session_id'],
                "timestamp": record['timestamp'],
                "node_name": record['node_name'],
                "node_id_rc": record['node_id_rc'],
                "quiz_type": record['quiz_type'],
                "student_name": record['student_name'],
                "total_questions": record['total_questions'],
                "total_score": record['total_score'],
                "max_score": record['max_score'],
                "average_score": record['average_score'],
                "results": [r for r in record['results'] if r.get('question')]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to get result: {e}")
        raise HTTPException(status_code=500, detail=str(e))
