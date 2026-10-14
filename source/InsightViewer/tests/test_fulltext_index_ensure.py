import importlib
import os
import sys
import types
import unittest
from pathlib import Path

import jwt
from flask import Flask


os.environ.setdefault("JWT_SECRET", "test-secret")
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

# Load the route without running routes/__init__.py, which imports the whole app.
routes_package = types.ModuleType("routes")
routes_package.__path__ = [str(APP_ROOT / "routes")]
sys.modules.setdefault("routes", routes_package)
global_search = importlib.import_module("routes.global_search")


class _FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def data(self):
        return self.rows

    def consume(self):
        return None


class _IndexSession:
    def __init__(self, analyzer):
        self.index_info = {
            "name": "test_fulltext_idx",
            "type": "FULLTEXT",
            "state": "ONLINE",
            "labels": ["OracleProcedure"],
            "properties": [
                "name",
                "id_rc",
                "title",
                "text",
                "html",
                "description",
                "projectName",
            ],
            "options": {"indexConfig": {"fulltext.analyzer": analyzer}},
        }
        self.queries = []

    def run(self, query, **kwargs):
        self.queries.append(query)
        if "SHOW INDEXES" in query:
            return _FakeResult([dict(self.index_info)] if self.index_info else [])
        if query.startswith("DROP INDEX"):
            self.index_info = None
        elif query.startswith("CREATE FULLTEXT INDEX"):
            self.index_info = {
                "name": "test_fulltext_idx",
                "type": "FULLTEXT",
                "state": "POPULATING",
                "labels": ["OracleProcedure"],
                "properties": [
                    "name",
                    "id_rc",
                    "title",
                    "text",
                    "html",
                    "description",
                    "projectName",
                ],
                "options": {
                    "indexConfig": {
                        "fulltext.analyzer": "simple",
                        "fulltext.eventually_consistent": False,
                    }
                },
            }
        return _FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


class FulltextIndexEnsureTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(global_search.global_search_bp)
        self.client = self.app.test_client()
        token = jwt.encode(
            {"sub": "test-user", "project": "TestProject"},
            os.environ["JWT_SECRET"],
            algorithm="HS256",
        )
        self.client.set_cookie("access_token", token, domain="localhost")
        self.original_driver = global_search.driver

    def tearDown(self):
        global_search.driver = self.original_driver

    def _ensure(self, session):
        global_search.init_driver(_FakeDriver(session))
        return self.client.post(
            "/api/search/fulltext-index-ensure",
            json={"index_name": "test_fulltext_idx", "labels": ["OracleProcedure"]},
        )

    def test_recreates_index_when_analyzer_is_not_simple(self):
        session = _IndexSession("standard-no-stop-words")

        response = self._ensure(session)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["replaced"])
        self.assertEqual(body["analyzer"], "simple")
        self.assertTrue(any(query.startswith("DROP INDEX") for query in session.queries))
        create_query = next(query for query in session.queries if query.startswith("CREATE FULLTEXT INDEX"))
        self.assertIn("`fulltext.analyzer`: 'simple'", create_query)
        self.assertIn("`fulltext.eventually_consistent`: false", create_query)

    def test_keeps_index_when_analyzer_is_already_simple(self):
        session = _IndexSession("simple")

        response = self._ensure(session)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["replaced"])
        self.assertEqual(response.get_json()["analyzer"], "simple")
        self.assertFalse(any(query.startswith("DROP INDEX") for query in session.queries))


if __name__ == "__main__":
    unittest.main()
