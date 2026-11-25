import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ai.vector_config import VECTOR_DIMENSIONS  # noqa: E402  # type: ignore[import-not-found]
from services import vector_embeddings  # noqa: E402  # type: ignore[import-not-found]


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def single(self):
        return self.row

    def data(self):
        return self.rows

    def consume(self):
        return None


class _Session:
    def __init__(self):
        self.fetches = 0
        self.calls = []

    def run(self, query, **params):
        self.calls.append((query, params))
        if "SHOW VECTOR INDEXES" in query:
            return _Result({
                "state": "ONLINE",
                "options": {"indexConfig": {"vector.dimensions": VECTOR_DIMENSIONS}},
                "labelsOrTypes": ["Chunk"],
                "properties": ["embedding"],
            })
        if "RETURN count(c) AS total" in query:
            return _Result({"total": 1})
        if "RETURN elementId(c) AS eid" in query:
            self.fetches += 1
            if self.fetches == 1:
                return _Result(rows=[{"eid": "4:ab", "text": "Useful chunk text"}])
            return _Result()
        return _Result()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Driver:
    def __init__(self):
        self.session_instance = _Session()

    def session(self):
        return self.session_instance


class _Provider:
    def __init__(self):
        self.requests = []

    def embed(self, request):
        self.requests.append(request)
        return type("Response", (), {"embedding": [0.0] * VECTOR_DIMENSIONS})()


class VectorEmbeddingServiceTests(unittest.TestCase):
    def test_backfill_is_project_scoped_and_checks_dimension(self):
        driver = _Driver()
        provider = _Provider()
        updates = []
        with patch.object(vector_embeddings, "ProviderRegistry") as registry_type:
            registry_type.return_value.get_provider.return_value = provider
            vector_embeddings.run_embedding_backfill(
                driver=driver,
                project="ProjectA",
                provider_id="ollama",
                model="mxbai-embed-large:latest",
                index_name="chunk_embedding_index",
                update_job=lambda **update: updates.append(update),
            )

        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].dimensions, VECTOR_DIMENSIONS)
        self.assertEqual(updates[-1]["status"], "completed")
        self.assertEqual(updates[-1]["processed"], 1)
        for query, params in driver.session_instance.calls:
            if "MATCH (c:Chunk)" in query:
                self.assertEqual(params["project"], "ProjectA")
        write = next(params for query, params in driver.session_instance.calls if "SET c.embedding =" in query)
        self.assertEqual(write["project"], "ProjectA")
        self.assertEqual(write["model"], "mxbai-embed-large:latest")

    def test_index_dimensions_must_match_vector_configuration(self):
        driver = _Driver()
        driver.session_instance.run = lambda query, **params: _Result({
            "state": "ONLINE",
            "options": {"indexConfig": {"vector.dimensions": 768}},
            "labelsOrTypes": ["Chunk"],
            "properties": ["embedding"],
        })
        with self.assertRaisesRegex(RuntimeError, "must use 1024 dimensions"):
            vector_embeddings.run_embedding_backfill(
                driver=driver,
                project="ProjectA",
                provider_id="ollama",
                model="mxbai-embed-large:latest",
                index_name="chunk_embedding_index",
                update_job=lambda **_update: None,
            )

    def test_backfill_reports_missing_text_and_provider_failures(self):
        class MixedSession(_Session):
            def run(self, query, **params):
                if "RETURN count(c) AS total" in query:
                    return _Result({"total": 2})
                if "RETURN elementId(c) AS eid" in query:
                    self.fetches += 1
                    if self.fetches == 1:
                        return _Result(rows=[
                            {"eid": "4:ab", "text": "provider should fail"},
                            {"eid": "4:ac", "text": None, "content": ""},
                        ])
                    return _Result()
                return super().run(query, **params)

        class MixedDriver:
            def __init__(self):
                self.session_instance = MixedSession()

            def session(self):
                return self.session_instance

        provider = type(
            "FailingProvider",
            (),
            {"embed": lambda _self, _request: (_ for _ in ()).throw(RuntimeError("provider unavailable"))},
        )()
        updates = []
        with patch.object(vector_embeddings, "ProviderRegistry") as registry_type:
            registry_type.return_value.get_provider.return_value = provider
            vector_embeddings.run_embedding_backfill(
                driver=MixedDriver(),
                project="ProjectA",
                provider_id="ollama",
                model="mxbai-embed-large:latest",
                index_name="chunk_embedding_index",
                update_job=lambda **update: updates.append(update),
            )

        self.assertEqual(updates[-1]["status"], "completed")
        self.assertEqual(updates[-1]["skipped"], 1)
        self.assertEqual(updates[-1]["failed"], 1)
        self.assertIn("provider unavailable", updates[-1]["error_samples"][0])


if __name__ == "__main__":
    unittest.main()
