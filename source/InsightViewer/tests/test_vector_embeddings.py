import os
import sys
import importlib.util
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from flask import Flask

os.environ.setdefault("JWT_SECRET", "test-secret")
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

ROUTES_ROOT = APP_ROOT / "routes"
retrieval_spec = importlib.util.spec_from_file_location(
    "retrieval_for_vector_tests", ROUTES_ROOT / "retrieval.py"
)
retrieval = importlib.util.module_from_spec(retrieval_spec)
retrieval_spec.loader.exec_module(retrieval)

# The legacy routes package initializer imports app.py; temporarily provide only
# the dependency needed by ops_vector while loading the route module directly.
routes_stub = types.ModuleType("routes")
routes_stub.__path__ = [str(ROUTES_ROOT)]
retrieval_stub = types.ModuleType("routes.retrieval")
retrieval_stub.validate_jwt = retrieval.validate_jwt
old_routes = sys.modules.get("routes")
old_retrieval = sys.modules.get("routes.retrieval")
sys.modules["routes"] = routes_stub
sys.modules["routes.retrieval"] = retrieval_stub
try:
    ops_spec = importlib.util.spec_from_file_location(
        "ops_vector_for_tests", ROUTES_ROOT / "ops_vector.py"
    )
    ops_vector = importlib.util.module_from_spec(ops_spec)
    ops_spec.loader.exec_module(ops_vector)
finally:
    if old_routes is None:
        sys.modules.pop("routes", None)
    else:
        sys.modules["routes"] = old_routes
    if old_retrieval is None:
        sys.modules.pop("routes.retrieval", None)
    else:
        sys.modules["routes.retrieval"] = old_retrieval


class _ImmediateExecutor:
    def submit(self, fn, *args):
        fn(*args)


class _ConsumeResult:
    def consume(self):
        return None


class _IndexSession:
    def __init__(self):
        self.queries = []

    def run(self, query, **_params):
        self.queries.append(query)
        return _ConsumeResult()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class VectorEmbeddingRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(ops_vector.ops_vector_bp)
        ops_vector.init_driver(object())
        ops_vector._jobs.clear()
        self.original_executor = ops_vector._job_executor
        ops_vector._job_executor = _ImmediateExecutor()
        self.client = self.app.test_client()
        self._set_user("alice", "ProjectA")

    def tearDown(self):
        ops_vector._job_executor = self.original_executor
        ops_vector._jobs.clear()

    def _set_user(self, uid, project):
        token = jwt.encode(
            {"sub": uid, "project": project},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        self.client.set_cookie("access_token", token, domain="localhost")

    def test_start_uses_authenticated_project_not_request_project(self):
        captured = {}

        def fake_backfill(**kwargs):
            captured.update(kwargs)
            kwargs["update_job"](status="running", total=2)
            kwargs["update_job"](status="completed", processed=2, completed_at="2026-01-01T00:00:00+00:00")

        with patch.object(ops_vector, "run_embedding_backfill", side_effect=fake_backfill):
            response = self.client.post(
                "/api/ops/vector-embeddings",
                json={
                    "project": "OtherProject",
                    "provider": "ollama",
                    "model": "mxbai-embed-large:latest",
                    "vector_index_name": "chunk_embedding_index",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(captured["project"], "ProjectA")
        self.assertEqual(captured["index_name"], "chunk_embedding_index")
        job_id = response.get_json()["job"]["id"]
        status = self.client.get(f"/api/ops/vector-embeddings/{job_id}")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["job"]["status"], "completed")
        self.assertNotIn("owner", status.get_json()["job"])

    def test_job_status_is_private_to_owner(self):
        ops_vector._jobs["secret-job"] = {
            "id": "secret-job",
            "owner": "alice",
            "project": "ProjectA",
            "status": "running",
        }
        self._set_user("bob", "ProjectA")
        response = self.client.get("/api/ops/vector-embeddings/secret-job")
        self.assertEqual(response.status_code, 404)

    def test_job_status_is_scoped_to_authenticated_project(self):
        ops_vector._jobs["secret-job"] = {
            "id": "secret-job",
            "owner": "alice",
            "project": "ProjectA",
            "status": "running",
        }
        self._set_user("alice", "ProjectB")
        response = self.client.get("/api/ops/vector-embeddings/secret-job")
        self.assertEqual(response.status_code, 404)

    def test_embedding_job_requires_authentication(self):
        self.client.delete_cookie("access_token", domain="localhost")
        response = self.client.post("/api/ops/vector-embeddings", json={})
        self.assertEqual(response.status_code, 401)

    def test_rejects_invalid_index_name(self):
        response = self.client.post(
            "/api/ops/vector-embeddings",
            json={"vector_index_name": "name; MATCH (n) DELETE n"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_vector_index_uses_expected_schema_and_dimensions(self):
        session = _IndexSession()

        class Driver:
            def session(self):
                return session

        ops_vector.init_driver(Driver())
        with patch.object(
            ops_vector,
            "inspect_vector_index",
            side_effect=[
                (None, None, [], []),
                ("POPULATING", 1024, ["Chunk"], ["embedding"]),
            ],
        ):
            response = self.client.post(
                "/api/ops/vector-index-ensure",
                json={"index_name": "chunk_embedding_index"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["created"])
        self.assertFalse(body["ready"])
        self.assertIn("CREATE VECTOR INDEX chunk_embedding_index IF NOT EXISTS", session.queries[0])
        self.assertIn("`vector.dimensions`: 1024", session.queries[0])

    def test_incompatible_vector_index_is_not_dropped_or_recreated(self):
        session = _IndexSession()

        class Driver:
            def session(self):
                return session

        ops_vector.init_driver(Driver())
        with patch.object(
            ops_vector,
            "inspect_vector_index",
            return_value=("ONLINE", 768, ["Chunk"], ["embedding"]),
        ):
            response = self.client.post(
                "/api/ops/vector-index-ensure",
                json={"index_name": "chunk_embedding_index"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(session.queries, [])
        self.assertIn("was not changed", response.get_json()["error"])

    def test_vector_index_status_reports_online_readiness(self):
        class Driver:
            def session(self):
                return _IndexSession()

        ops_vector.init_driver(Driver())
        with patch.object(
            ops_vector,
            "inspect_vector_index",
            return_value=("ONLINE", 1024, ["Chunk"], ["embedding"]),
        ):
            response = self.client.get(
                "/api/ops/vector-index-status?index_name=chunk_embedding_index"
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ready"])


if __name__ == "__main__":
    unittest.main()
