#!/usr/bin/env python3
# -*- coding: utf-8 -*-


  


from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError


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
    cypher_path = Path("out.cypher")
    payload_path = Path("payload.json")

    if not cypher_path.exists():
        print(f"ERROR: missing {cypher_path.resolve()}", file=sys.stderr)
        return 2
    if not payload_path.exists():
        print(f"ERROR: missing {payload_path.resolve()}", file=sys.stderr)
        return 2

    # Neo4j bolt from host -> container port mapping is exposed (7687)
    URI = "bolt://localhost:7687"
    USER = "neo4j"
    PASSWORD = "Sonja1val."  # <-- your password

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

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
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

        print("\n✔ Import completed.")
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
