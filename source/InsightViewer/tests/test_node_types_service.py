import unittest

from app.services import create_node_types


class _FakeSession:
    def __init__(self):
        self.query = None
        self.parameters = None

    def run(self, query, **parameters):
        self.query = query
        self.parameters = parameters
        return [{"nt.name": "Person"}, {"nt.name": "Organization"}]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeDriver:
    def __init__(self):
        self.fake_session = _FakeSession()

    def session(self):
        return self.fake_session


class NodeTypesServiceTests(unittest.TestCase):
    def test_creates_node_types_using_supplied_driver_and_options(self):
        driver = _FakeDriver()

        node_types = create_node_types(
            driver,
            project_name="demo",
            created_by="demo-user",
            color="#123456",
            shape="ellipse",
            size=30,
            url="https://example.test",
        )

        self.assertEqual(node_types, ["Person", "Organization"])
        self.assertIn("MERGE (nt:NodeType", driver.fake_session.query)
        self.assertEqual(driver.fake_session.parameters["projectName"], "demo")
        self.assertEqual(driver.fake_session.parameters["createdBy"], "demo-user")
        self.assertEqual(driver.fake_session.parameters["color"], "#123456")
        self.assertEqual(driver.fake_session.parameters["shape"], "ellipse")
        self.assertEqual(driver.fake_session.parameters["size"], 30)
        self.assertEqual(driver.fake_session.parameters["url"], "https://example.test")

    def test_requires_a_driver(self):
        with self.assertRaisesRegex(ValueError, "Neo4j driver is required"):
            create_node_types(None, project_name="demo")


if __name__ == "__main__":
    unittest.main()
