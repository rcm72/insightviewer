"""Project scoping contract for the Add Existing Nodes endpoint."""

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
    "existing_nodes_routes_under_test",
    PROJECT_ROOT / "app" / "routes" / "createNodeTypes.py",
)
existing_nodes_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing_nodes_routes)


class ExistingNodesProjectTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(existing_nodes_routes.nodes_bp)
        self.client = app.test_client()
        self.driver = MagicMock()
        self.session = self.driver.session.return_value.__enter__.return_value
        self.session.run.return_value = [{
            "id": 17,
            "name": "Demo.package.Alpha",
            "properties": {"id_rc": "alpha-id", "name": "Demo.package.Alpha", "projectName": "Demo"},
            "labels": ["ExampleNode"],
        }]

    def request_nodes(self, body):
        with patch.object(existing_nodes_routes, "driver", self.driver), patch.object(
            existing_nodes_routes,
            "validate_jwt",
            return_value=({"uid": "test-user", "project": "Demo"}, None, None),
        ):
            return self.client.post("/nodes/get_nodes_by_type", json=body)

    def test_nodes_query_is_limited_to_authenticated_project(self):
        response = self.request_nodes({"nodeType": "ExampleNode", "projectName": "ALL"})

        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["nodes"][0]["properties"]["projectName"], "Demo")
        query = self.session.run.call_args.args[0]
        self.assertIn("n.projectName = $project", query)
        self.assertEqual(self.session.run.call_args.kwargs, {
            "nodeType": "ExampleNode",
            "allNodeTypes": False,
            "project": "Demo",
        })

    def test_all_nodes_option_removes_label_filter_but_keeps_project_filter(self):
        response = self.request_nodes({"nodeType": "__ALL__"})

        self.assertEqual(response.status_code, 200, response.get_json())
        query = self.session.run.call_args.args[0]
        self.assertIn("($allNodeTypes OR $nodeType IN labels(n))", query)
        self.assertIn("n.projectName = $project", query)
        self.assertEqual(self.session.run.call_args.kwargs["allNodeTypes"], True)
        self.assertEqual(self.session.run.call_args.kwargs["project"], "Demo")

    def test_node_type_is_required(self):
        response = self.request_nodes({})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])
        self.session.run.assert_not_called()

    def test_picker_includes_filter_and_matches_short_and_full_names(self):
        template = (PROJECT_ROOT / "app" / "templates" / "index.html").read_text(encoding="utf-8")
        frontend = (PROJECT_ROOT / "app" / "static" / "indexScript.js").read_text(encoding="utf-8")

        self.assertIn('id="existing-nodes-filter"', template)
        self.assertIn('oninput="renderExistingNodeList()"', template)
        self.assertIn("fullName.toLocaleLowerCase().includes(filterText)", frontend)
        self.assertIn("shortName.toLocaleLowerCase().includes(filterText)", frontend)
        self.assertIn('allOption.value = "__ALL__"', frontend)
        self.assertIn('["Short name", "Name"]', frontend)
        self.assertIn("cell.textContent = value", frontend)


if __name__ == "__main__":
    unittest.main()
