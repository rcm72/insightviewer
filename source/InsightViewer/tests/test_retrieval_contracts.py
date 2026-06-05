import os
import sys
import unittest
import importlib.util
from pathlib import Path

import jwt
from flask import Flask


os.environ.setdefault("JWT_SECRET", "test-secret")

APP_ROOT = Path("/home/robert/insightViewer/source/InsightViewer/app")
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

RETRIEVAL_PATH = Path("/home/robert/insightViewer/source/InsightViewer/app/routes/retrieval.py")
spec = importlib.util.spec_from_file_location("retrieval_under_test", RETRIEVAL_PATH)
retrieval = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(retrieval)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows


class _FakeSession:
    def run(self, query, **kwargs):
        if "db.index.fulltext.queryNodes" in query:
            return _FakeResult(
                [
                    {
                        "id_rc": "node-1",
                        "name": "test",
                        "labels": ["Department"],
                        "score": 1.0,
                    }
                ]
            )

        if "RETURN n.id_rc AS id_rc, labels(n) AS labels, n.name AS name" in query:
            return _FakeResult(
                [
                    {
                        "id_rc": "node-1",
                        "labels": ["Department"],
                        "name": "test",
                    }
                ]
            )

        if "OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c:Chunk)" in query:
            return _FakeResult(
                [
                    {
                        "id_rc": "chunk-1",
                        "labels": ["Chunk"],
                        "text": "chunk text",
                    }
                ]
            )

        return _FakeResult([])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def session(self):
        return _FakeSession()


class RetrievalContractTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        retrieval.init_driver(_FakeDriver())
        self.app.register_blueprint(retrieval.retrieval_bp)
        self.client = self.app.test_client()

        token = jwt.encode(
            {
                "sub": "test-user",
                "project": "TestProject",
            },
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        self.client.set_cookie("access_token", token, domain="localhost")

    def test_query_cypher_contract(self):
        response = self.client.post(
            "/api/retrieval/query-cypher",
            json={
                "query": "test",
                "index_name": "iv_global_search_idx",
                "retrieval_mode": "fulltext",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        for key in ("success", "cypher", "items", "meta", "telemetry"):
            self.assertIn(key, body)

        self.assertEqual(body["telemetry"]["strategy_used"], "fulltext_to_cypher")

    def test_chunks_by_depth_contract(self):
        response = self.client.post(
            "/api/retrieval/chunks-by-depth",
            json={"node_ids": ["node-1"], "depth": 1, "chunk_limit": 20},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()

        self.assertTrue(body["success"])
        self.assertIn("retrieval", body)

        retrieval_body = body["retrieval"]
        for key in (
            "input_node_ids",
            "depth",
            "visited_nodes_count",
            "chunks_count",
            "visited_nodes",
            "chunks",
            "telemetry",
        ):
            self.assertIn(key, retrieval_body)

        self.assertEqual(retrieval_body["telemetry"]["strategy_used"], "depth_chunks")

    def test_legacy_wrapper_parity(self):
        payload_retrieval = {
            "query": "test",
            "index_name": "iv_global_search_idx",
            "retrieval_mode": "fulltext",
            "entry_point": "retrieval-query-cypher",
        }
        payload_legacy = {
            "query": "test",
            "index_name": "iv_global_search_idx",
            "retrieval_mode": "fulltext",
            "entry_point": "global-search-neo4j",
        }

        with _FakeSession() as session:
            retrieval_result = retrieval.build_query_cypher_response(session, payload_retrieval, "TestProject")
            legacy_result = retrieval.build_query_cypher_response(session, payload_legacy, "TestProject")

        self.assertEqual(retrieval_result["status_code"], 200)
        self.assertEqual(legacy_result["status_code"], 200)
        self.assertEqual(retrieval_result["body"]["cypher"], legacy_result["body"]["cypher"])
        self.assertEqual(retrieval_result["body"]["items"], legacy_result["body"]["items"])
        self.assertEqual(retrieval_result["body"]["meta"], legacy_result["body"]["meta"])

    def test_auto_mode_falls_back_to_fulltext_when_vector_fails(self):
        original_vector_hits = retrieval._vector_hits
        original_fulltext_hits = retrieval._fulltext_hits

        def _boom(*args, **kwargs):
            raise RuntimeError("vector temporarily unavailable")

        def _ok(*args, **kwargs):
            return [
                {
                    "id_rc": "node-ft-1",
                    "name": "fallback node",
                    "labels": ["Department"],
                    "score": 0.42,
                }
            ]

        retrieval._vector_hits = _boom
        retrieval._fulltext_hits = _ok
        try:
            with _FakeSession() as session:
                result = retrieval.retrieve_nodes_for_query(
                    session,
                    {
                        "query": "test",
                        "index_name": "iv_global_search_idx",
                        "retrieval_mode": "auto",
                    },
                    "TestProject",
                )
        finally:
            retrieval._vector_hits = original_vector_hits
            retrieval._fulltext_hits = original_fulltext_hits

        self.assertEqual(result["telemetry"]["strategy_used"], "fulltext_query")
        self.assertEqual(result["items"][0]["id_rc"], "node-ft-1")
        self.assertIn("vector temporarily unavailable", str(result["meta"].get("vector_error") or ""))

    def test_vector_mode_returns_400_when_vector_fails(self):
        original_vector_hits = retrieval._vector_hits

        def _boom(*args, **kwargs):
            raise RuntimeError("vector hard-fail")

        retrieval._vector_hits = _boom
        try:
            response = self.client.post(
                "/api/retrieval/query",
                json={
                    "query": "test",
                    "index_name": "iv_global_search_idx",
                    "retrieval_mode": "vector",
                },
            )
        finally:
            retrieval._vector_hits = original_vector_hits

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertIn("Vector retrieval failed", body.get("error", ""))


if __name__ == "__main__":
    unittest.main()
