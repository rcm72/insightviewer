"""Custom graph save query contracts; no live Neo4j connection is required."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import just this route module, bypassing routes/__init__.py and app startup.
spec = importlib.util.spec_from_file_location(
    "custom_graph_routes_under_test", PROJECT_ROOT / "app" / "routes" / "createNodeTypes.py"
)
custom_graph_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custom_graph_routes)


class CustomGraphIdTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(custom_graph_routes.nodes_bp)
        self.client = app.test_client()
        self.driver = MagicMock()
        self.session = self.driver.session.return_value.__enter__.return_value
        self.session.run.return_value = []

    def save_graph(self):
        with patch.object(custom_graph_routes, "driver", self.driver), patch.object(
            custom_graph_routes,
            "validate_jwt",
            return_value=({"uid": "test-user", "project": "Demo"}, None, None),
        ):
            response = self.client.post(
                "/nodes/connect-custom-graph-position",
                json={
                    "customGraphName": "Demo graph",
                    "nodes": [
                        {"id": "node-1", "vis_id": "node-1", "properties": {"name": "Alice"}, "x": 1, "y": 2, "shape": "ellipse"},
                        {"id": "node-2", "vis_id": "node-2", "properties": {"name": "Bob"}, "x": 3, "y": 4, "shape": "ellipse"},
                    ],
                },
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["success"])
        return self.session.run.call_args

    def test_position_ids_are_generated_per_node_not_per_save(self):
        call = self.save_graph()
        query = call.args[0]
        self.assertIn("UNWIND $nodeDataCgPos AS nodeDataCgPos", query)
        self.assertRegex(query, r"ON CREATE SET\s+newNodeCg\.id_rc\s*=\s*randomUUID\(\)")
        self.assertNotIn("$id_rc", query)
        self.assertNotIn("id_rc", call.kwargs)
        self.assertEqual(len(call.kwargs["nodeDataCgPos"]), 2)

    def test_resaving_updates_positions_without_overwriting_existing_ids(self):
        self.save_graph()
        query = self.save_graph().args[0]
        update_clause = query.split("ON MATCH SET", 1)[1].split("RETURN", 1)[0]
        self.assertNotIn("id_rc", update_clause)
        for field in ("x", "y", "shape"):
            self.assertIn(f"newNodeCg.{field}", update_clause)

    def test_position_records_keep_a_reference_to_the_original_node(self):
        query = self.save_graph().args[0]
        self.assertIn("newNodeCg.original_id = nodeDataCgPos.vis_id", query)
        self.assertNotIn("newNodeCg.id_rc = nodeDataCgPos.id", query)


if __name__ == "__main__":
    unittest.main()
