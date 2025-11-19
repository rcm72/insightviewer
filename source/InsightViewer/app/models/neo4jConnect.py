# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec


# app/models/neo4jConnect.py
from neo4j import GraphDatabase
import configparser
from pathlib import Path
import os
import sys
#import rcmrlec.insightViewer.config as config  # Import the configuration file

# Locate config.ini:
# 1) environment variable INSIGHTVIEWER_CONFIG or CONFIG_PATH
# 2) project locations (project/config.ini, project/app/config.ini)
# 3) CWD, user home, /etc
env_path = os.environ.get("INSIGHTVIEWER_CONFIG") or os.environ.get("CONFIG_PATH")
candidates = []
if env_path:
    candidates.append(Path(env_path))

here = Path(__file__).resolve()
project_root = here.parents[2] if len(here.parents) >= 3 else here.parent
candidates += [
    project_root / "config.ini",
    project_root / "app" / "config.ini",
    Path.cwd() / "config.ini",
    Path.home() / ".config" / "insightViewer" / "config.ini",
    Path.home() / "config.ini",
    Path("/etc/insightViewer/config.ini"),
]

config = configparser.ConfigParser()
found = None
for p in candidates:
    if p and p.exists():
        found = p
        break

if not found:
    searched = ", ".join(str(p) for p in candidates)
    raise RuntimeError(f"config.ini not found. Searched: {searched}. Set INSIGHTVIEWER_CONFIG env var to point to config.ini.")

CONFIG_PATH = str(found)
config.read(CONFIG_PATH)

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

