from neo4j import GraphDatabase
import configparser

class TestNeo4jHalPlugin:
    def __init__(self):
        # Load configuration
        config = configparser.ConfigParser()
        config.read('config.ini')
        self.uri = config['NEO4J']['URI']
        self.user = config['NEO4J']['USERNAME']
        self.password = config['NEO4J']['PASSWORD']

        # Create a driver instance
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def test_connection(self):
        with self.driver.session() as session:
            result = session.run("RETURN 1 AS number")
            record = result.single()
            number = record["number"]
            print("Result number:", number)
            if number != 1:
                raise RuntimeError("Connection test failed")

    # Function to create a sample node (not used in this test)
    def create_sample_node(self, name):
        with self.driver.session() as session:
            session.run("CREATE (a:SampleNode {name: $name})", name=name)

    # Function to delete sample nodes (not used in this test)
    # def delete_sample_nodes(self):
    #     with self.driver.session() as session:
    #        session.run("MATCH (a:SampleNode) DETACH DELETE a")
           

# run test_connection 
if __name__ == "__main__":
    tester = TestNeo4jHalPlugin()
    try:
        tester.test_connection()
        print("test_connection OK")
        # Uncomment to create a sample node
        tester.create_sample_node("Test Node")
        #tester.delete_sample_nodes()
    finally:
        tester.close()        


