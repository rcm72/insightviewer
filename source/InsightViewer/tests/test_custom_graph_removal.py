"""Custom graph removal route contracts; no live Neo4j connection is required."""

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

spec = importlib.util.spec_from_file_location(
    "custom_graph_removal_routes_under_test",
    PROJECT_ROOT / "app" / "routes" / "createNodeTypes.py",
)
custom_graph_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custom_graph_routes)


class CustomGraphRemovalTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(custom_graph_routes.nodes_bp)
        self.client = app.test_client()
        self.driver = MagicMock()
        self.session = self.driver.session.return_value.__enter__.return_value
        self.session.run.return_value.single.return_value = {"removed": 1}

    def request_removal(self, payload):
        with patch.object(custom_graph_routes, "driver", self.driver), patch.object(
            custom_graph_routes,
            "validate_jwt",
            return_value=({"uid": "test-user", "project": "Demo"}, None, None),
        ):
            return self.client.post("/nodes/remove-node-custom-graph", json=payload)

    def test_registered_route_removes_only_the_selected_graph_position(self):
        response = self.request_removal({
            "node_id": "source-node-123",
            "custom_graph_name": "Demo graph",
        })

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json(), {"success": True, "removed_count": 1})
        query = self.session.run.call_args.args[0]
        self.assertIn("(g:CustomGraph {name: $custom_graph_name})-[:isPartOf]-(position:CustomGraphNode)", query)
        self.assertIn("position.original_id = $node_id", query)
        self.assertIn("DETACH DELETE position", query)
        self.assertNotIn("MATCH (n)", query)
        self.assertNotIn("DELETE r", query)
        self.assertEqual(self.session.run.call_args.kwargs, {
            "node_id": "source-node-123",
            "custom_graph_name": "Demo graph",
        })

    def test_requires_both_node_and_custom_graph_ids(self):
        response = self.request_removal({"node_id": "source-node-123"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])
        self.session.run.assert_not_called()

    def test_frontend_uses_the_registered_post_endpoint(self):
        frontend = (PROJECT_ROOT / "app" / "static" / "indexScript.js").read_text(encoding="utf-8")

        self.assertIn('fetch("/nodes/remove-node-custom-graph"', frontend)
        self.assertIn("custom_graph_name: gCustomGraphName", frontend)
        self.assertNotIn('url: "/remove-node-custom-graph"', frontend)


if __name__ == "__main__":
    unittest.main()
