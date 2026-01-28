#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# cd /home/robert/insightViewer/source/InsightViewer/app/scripts/content_from_text/src
# python importCypherpy.py
  


from __future__ import annotations

import configparser
import json
import sys
from pathlib import Path
from typing import List

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable


def split_cypher_statements(script: str) -> List[str]:
    """
    Split Cypher script into statements by ';' but don't split inside strings.
    Removes // comments.
    """
    # strip // comments
    cleaned_lines = []
    for ln in script.splitlines():
        s = ln.strip()
        if s.startswith("//"):
            continue
        if "//" in ln:
            ln = ln.split("//", 1)[0]
        cleaned_lines.append(ln)
    s = "\n".join(cleaned_lines)

    stmts = []
    buf = []
    in_single = False
    in_double = False
    escape = False

    for ch in s:
        if escape:
            buf.append(ch)
            escape = False
            continue

        if ch == "\\":
            buf.append(ch)
            escape = True
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
            continue

        if ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            buf = []
            if stmt:
                stmts.append(stmt)
            continue

        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)

    return stmts


def main() -> int:
    # Resolve paths relative to the script's location
    BASE_DIR = Path(__file__).resolve().parent.parent  # Go up one level to `content_from_text`
    OUTPUT_DIR = BASE_DIR / "output"  # Point to the `output` directory

    cypher_path = OUTPUT_DIR / "utBiologija1_ch2.cypher"  # Updated to match the new location
    payload_path = OUTPUT_DIR / "payloadBiologija1_ch2.json"  # Updated to match the new location

    if not cypher_path.exists():
        print(f"ERROR: missing {cypher_path.resolve()}", file=sys.stderr)
        return 2
    if not payload_path.exists():
        print(f"ERROR: missing {payload_path.resolve()}", file=sys.stderr)
        return 2

    # BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
    BASE_DIR = Path(__file__).resolve().parents[4]
    CONFIG_PATH = BASE_DIR / "config.ini"
    print(f"Using config file: {CONFIG_PATH}")

    # Read configuration
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    # Extract Neo4j connection details from the config file
    # Replace '192.168.1.16' with the container's IP or host IP if ports are exposed
    URI = config.get("NEO4J", "URI", fallback="bolt://192.168.1.16:7687")
    USER = config.get("NEO4J", "USER", fallback="neo4j")
    PASSWORD = config.get("NEO4J", "PASSWORD", fallback="password")

    print(f"Using Neo4j URI: {URI}, User: {USER}")
    print("URI" + (" found in config." if config.has_option("NEO4J", "URI") else " not found in config, using default."))
    print("password" + (" found in config." if config.has_option("NEO4J", "PASSWORD") else " not found in config, using default."))


    script = cypher_path.read_text(encoding="utf-8")
    statements = split_cypher_statements(script)

    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    params = {
        "projectName": payload.get("projectName"),
        "nodes": payload.get("nodes", []),
        "rels": payload.get("rels", []),
    }

    print(f"Statements found: {len(statements)}")
    print(f"Nodes: {len(params['nodes'])}, Rels: {len(params['rels'])}")

    try:
        # Test connection to Neo4j
        print("Testing connection to Neo4j...")
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        with driver.session() as session:
            session.run("RETURN 1").consume()  # Simple test query
        print("Connection to Neo4j successful.")

        # Proceed with Cypher script execution
        with driver.session() as session:
            for i, stmt in enumerate(statements, start=1):
                use_params = params if "$" in stmt else {}
                try:
                    session.run(stmt, **use_params).consume()
                    print(f"[OK] statement {i}/{len(statements)}")
                except Neo4jError as e:
                    print(f"\n[FAIL] statement {i}/{len(statements)}:\n{stmt}\n", file=sys.stderr)
                    print(f"{e.__class__.__name__}: {e}", file=sys.stderr)
                    return 1
    except ServiceUnavailable as e:
        print(f"ERROR: Unable to connect to Neo4j at {URI}.", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        print("Please check your network connection, Neo4j configuration, and ensure the service is running.", file=sys.stderr)
        return 3
    finally:
        if 'driver' in locals():
            driver.close()

    print("\n✔ Import completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
