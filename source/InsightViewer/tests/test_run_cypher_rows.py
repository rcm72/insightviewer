"""Contract tests for Cypher projection export without a live Neo4j server."""

import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from neo4j import Record
from neo4j.graph import Graph, Node

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET", "test-only-jwt-secret")
from app import app as app_module  # noqa: E402


class FakeResult:
    def __init__(self, columns, values):
        self.columns = columns
        self.values = values

    def keys(self):
        return self.columns

    def __iter__(self):
        return (Record(zip(self.columns, row)) for row in self.values)


class FakeDriver:
    def __init__(self, result):
        self.result = result

    def session(self):
        driver = self

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                return False

            def run(self, query):
                driver.query = query
                return driver.result

        return Session()


class RunCypherRowsTests(unittest.TestCase):
    def query(self, result):
        driver = FakeDriver(result)
        with patch.object(app_module, "driver", driver), patch.object(
            app_module, "validate_jwt", return_value=({"uid": "test", "project": "Demo"}, None, None)
        ):
            response = app_module.app.test_client().post("/run-cypher", json={
                "query": "MATCH (n) RETURN n.name AS name, n.amount AS amount", "project": "Demo"
            })
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_scalar_projection_keeps_names_order_duplicates_nulls_and_dates(self):
        body = self.query(FakeResult(
            ["name", "amount", "due", "name"],
            [["Alice", 3, date(2026, 10, 1), None], ["Bob", 0, None, "B"]],
        ))
        self.assertEqual(body["columns"], ["name", "amount", "due", "name"])
        self.assertEqual(body["rows"], [
            ["Alice", 3, "2026-10-01", None], ["Bob", 0, None, "B"]
        ])
        self.assertTrue(body["hasScalarColumns"])
        self.assertEqual(body["nodes"], [])

    def test_empty_result_keeps_headers(self):
        body = self.query(FakeResult(["name", "amount"], []))
        self.assertEqual(body["columns"], ["name", "amount"])
        self.assertEqual(body["rows"], [])

    def test_rows_exclude_graph_entities_from_other_projects(self):
        graph = Graph()
        own = Node(graph, "own", 1, ["Task"], {"name": "Alice", "projectName": "Demo"})
        other = Node(graph, "other", 2, ["Task"], {"name": "Private", "projectName": "Elsewhere"})
        body = self.query(FakeResult(["node", "name"], [
            [own, "Alice"], [other, "Private"],
        ]))
        self.assertEqual(len(body["rows"]), 1)
        self.assertEqual(body["rows"][0][0]["properties"]["name"], "Alice")
        self.assertEqual(body["rows"][0][1], "Alice")
        self.assertEqual(len(body["nodes"]), 1)

    def test_optional_null_graph_values_keep_graph_export_mode(self):
        graph = Graph()
        own = Node(graph, "own", 1, ["Task"], {"name": "Alice", "projectName": "Demo"})
        body = self.query(FakeResult(["s", "r", "t"], [[own, None, None]]))
        self.assertFalse(body["hasScalarColumns"])
        self.assertEqual(len(body["nodes"]), 1)


if __name__ == "__main__":
    unittest.main()
