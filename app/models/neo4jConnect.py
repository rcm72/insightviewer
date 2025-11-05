# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec


# app/models/neo4jConnect.py
from neo4j import GraphDatabase
import configparser
#import rcmrlec.insightViewer.config as config  # Import the configuration file

CONFIG_PATH = "/home/pi/Documents/rcmrlec/insightViewer/config.ini"  # <-- Fixed path

# Load configuration
config = configparser.ConfigParser()
config.read('/home/pi/Documents/rcmrlec/insightViewer/config.ini')

# Check if config loaded correctly
if "NEO4J" not in config:
    raise RuntimeError(f"NEO4J section is missing in {CONFIG_PATH}!")


class Neo4jConnector:
    def __init__(self):
        """Initialize Neo4j connection using config settings."""
        #self.driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD))
        self.driver = GraphDatabase.driver(config.get('NEO4J', 'URI'), auth=(config.get('NEO4J', 'USERNAME'), config.get('NEO4J', 'PASSWORD')))


    def query(self, cypher_query, parameters=None):
        """Execute a Neo4j query and return results."""
        with self.driver.session() as session:
            result = session.run(cypher_query, parameters)
            return [record for record in result]  # Fetch all records before returning

    def close(self):
        """Close Neo4j connection."""
        self.driver.close()
