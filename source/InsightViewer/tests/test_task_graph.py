"""Contract tests for standalone CKEditor task graph generation."""

import importlib.util
import unittest
from pathlib import Path

from flask import Flask


APP_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "meeting_graph_under_test", APP_ROOT / "app/routes/meeting_graph.py"
)
meeting_graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meeting_graph)


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def single(self):
        return self.row

    def consume(self):
        return None


class FakeTransaction:
    def __init__(self, parent_name="TestProject.Parent"):
        self.calls = []
        self.parent_name = parent_name

    def run(self, query, params):
        self.calls.append((query, params))
        if "RETURN parent.name AS name" in query:
            return FakeResult({"name": self.parent_name} if self.parent_name else None)
        if "RETURN container.id_rc AS taskContainerId" in query:
            return FakeResult({
                "taskContainerId": "container-id",
                "documentId": "document-id",
                "taskId": "task-id",
            })
        if "RETURN c.id_rc AS chunkId" in query:
            return FakeResult({"chunkId": f"chunk-{params['section']}"})
        return FakeResult()


class FakeSession:
    def __init__(self, tx):
        self.tx = tx

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, callback, *args):
        return callback(self.tx, *args)


class FakeDriver:
    def __init__(self):
        self.tx = FakeTransaction()

    def session(self):
        return FakeSession(self.tx)


class TaskGraphTests(unittest.TestCase):
    def setUp(self):
        self.html = (APP_ROOT / "app/templates/template_snippets/taskTemplate.html").read_text()
        self.app = Flask(__name__)
        self.app.register_blueprint(meeting_graph.meeting_graph_bp)
        self.driver = FakeDriver()
        meeting_graph.init_driver(self.driver)

    def test_task_template_creates_graph_with_sections(self):
        parsed = meeting_graph.parse_task_html(self.html)
        self.assertEqual(parsed["title"], "Naziv naloge")
        self.assertEqual(len(parsed["chunks"]), 7)

        response = self.app.test_client().post("/graph/generate-graph", json={
            "html": self.html,
            "templateType": "CKEDITOR_TASK",
            "projectName": "TestProject",
            "graphNodeName": "Summary",
            "nodeId": "parent-id",
        })
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["title"], "Naziv naloge")
        self.assertEqual(body["taskContainerId"], "container-id")
        self.assertEqual(body["taskId"], "task-id")
        self.assertEqual(body["documentId"], "document-id")
        self.assertEqual(body["chunksCount"], 7)

        calls = self.driver.tx.calls
        primary_query, primary_params = calls[1]
        self.assertIn("MERGE (container:TaskContainer {name: $containerName})", primary_query)
        self.assertIn("MERGE (task:Task {name: $taskName})", primary_query)
        self.assertEqual(primary_params["taskTitle"], "Naziv naloge")
        self.assertEqual(primary_params["containerName"], "TestProject.Parent.TaskContainer.Naziv naloge")
        self.assertEqual(primary_params["documentName"], "TestProject.Parent.TaskContainer.Naziv naloge.Document")
        self.assertEqual(primary_params["taskName"], "TestProject.Parent.TaskContainer.Naziv naloge.Task")
        chunks = [(q, p) for q, p in calls if "MERGE (doc)-[:HAS_CHUNK]->(c)" in q]
        self.assertEqual(len(chunks), 7)
        self.assertTrue(all(p["documentId"] == "document-id" for _, p in chunks))
        self.assertIn("MERGE (parent)-[:HAS_DETAILS]->(container)", calls[-1][0])

    def test_repeated_writes_use_stable_merge_names(self):
        names = []
        for _ in range(2):
            parsed = meeting_graph.parse_task_html(self.html)
            tx = FakeTransaction()
            meeting_graph.write_task_graph(tx, "TestProject", self.html, parsed)
            names.append([p["containerName"] for q, p in tx.calls if "RETURN container.id_rc" in q] +
                         [p["chunkName"] for q, p in tx.calls if "RETURN c.id_rc" in q])
        self.assertEqual(names[0], names[1])

    def test_parent_name_without_project_prefix(self):
        tx = FakeTransaction(parent_name="Parent")
        parsed = meeting_graph.parse_task_html(self.html)
        meeting_graph.write_task_graph(tx, "TestProject", self.html, parsed, node_id="parent-id")
        self.assertEqual(tx.calls[1][1]["containerName"], "TestProject.Parent.TaskContainer.Naziv naloge")

    def test_missing_parent_does_not_create_orphan_container(self):
        tx = FakeTransaction(parent_name=None)
        parsed = meeting_graph.parse_task_html(self.html)
        with self.assertRaisesRegex(ValueError, "Parent node .* was not found"):
            meeting_graph.write_task_graph(tx, "TestProject", self.html, parsed, node_id="missing-id")
        self.assertEqual(len(tx.calls), 1)

    def test_finished_date_is_parsed_and_written(self):
        html = self.html.replace(
            "<th>Datum zaključka</th>\n                        <td>DD.MM.LLLL</td>",
            "<th>Datum zaključka</th>\n                        <td>30.09.2026</td>",
        )
        self.assertNotEqual(html, self.html)
        parsed = meeting_graph.parse_task_html(html)
        self.assertEqual(parsed["finishedDate"], "2026-09-30")
        self.assertEqual(parsed["tasks"][0]["finishedDate"], "2026-09-30")

        tx = FakeTransaction()
        meeting_graph.write_task_graph(tx, "TestProject", html, parsed)
        query, params = tx.calls[0]
        self.assertIn("task.finishedDate = CASE WHEN $finishedDate IS NULL THEN NULL ELSE date($finishedDate) END", query)
        self.assertEqual(params["finishedDate"], "2026-09-30")

    def test_task_without_finished_date_remains_unfinished(self):
        html = self.html.replace(
            "                    <tr>\n                        <th>Datum zaključka</th>\n"
            "                        <td>DD.MM.LLLL</td>\n                    </tr>\n",
            "",
        )
        self.assertNotEqual(html, self.html)
        parsed = meeting_graph.parse_task_html(html)
        self.assertIsNone(parsed["finishedDate"])
        self.assertIsNone(parsed["tasks"][0]["finishedDate"])


class MeetingGraphTests(unittest.TestCase):
    def test_meeting_task_binds_finished_date_when_present_or_missing(self):
        for finished_date in ("2026-09-30", None):
            with self.subTest(finished_date=finished_date):
                tx = FakeTransaction()
                parsed = {
                    "meetingId": "meeting-id",
                    "documentId": "document-id",
                    "graphNodeName": "Meeting",
                    "title": "Meeting",
                    "language": "sl",
                    "attendees": [],
                    "agenda": [],
                    "notes": "",
                    "chunks": [],
                    "tasks": [{
                        "title": "Task",
                        "owner": None,
                        "description": "Description",
                        "assignedDate": None,
                        "dueDate": None,
                        "finishedDate": finished_date,
                        "finished": None,
                        "status": "OPEN",
                    }],
                }
                meeting_graph.write_meeting_graph(tx, "TestProject", "<p>Meeting</p>", parsed)
                task_query, params = next(
                    (query, parameters) for query, parameters in tx.calls
                    if "t.finishedDate = CASE" in query
                )
                self.assertIn("$finishedDate", task_query)
                self.assertIn("finishedDate", params)
                self.assertEqual(params["finishedDate"], finished_date)


if __name__ == "__main__":
    unittest.main()
