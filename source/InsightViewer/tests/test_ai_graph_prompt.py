import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("JWT_SECRET", "test-secret")
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from graph.context import format_nodes_for_prompt


class AiGraphPromptTests(unittest.TestCase):
    def test_prompt_includes_selected_node_identity_and_neighborhood(self):
        prompt = format_nodes_for_prompt(
            ["node-1"],
            [
                {
                    "id_rc": "node-1",
                    "labels": ["OracleProcedure"],
                    "name": "GET_CUSTOMER",
                },
                {
                    "id_rc": "node-2",
                    "labels": ["Table"],
                    "name": "CUSTOMER",
                },
            ],
        )

        self.assertIn("Selected starting node(s):", prompt)
        self.assertIn("id_rc=node-1; labels=['OracleProcedure']; name=GET_CUSTOMER", prompt)
        self.assertIn("id_rc=node-2; labels=['Table']; name=CUSTOMER", prompt)


if __name__ == "__main__":
    unittest.main()
