#!/usr/bin/env python3
import argparse
import configparser
import os
import sys
import importlib
from typing import Iterable

from neo4j import GraphDatabase, custom_auth
from neo4j.exceptions import AuthError

APP_ROOT = "/home/robert/insightViewer/source/InsightViewer/app"
PROJECT_ROOT = "/home/robert/insightViewer/source/InsightViewer"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

ProviderRegistry = importlib.import_module("ai.registry").ProviderRegistry
EmbedRequest = importlib.import_module("ai.types").EmbedRequest


def _pick_text(row: dict, properties: Iterable[str]) -> str:
    for name in properties:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_neo4j_from_config() -> tuple[str | None, str | None, str | None, str | None]:
    parser = configparser.ConfigParser()
    parser.read(
        [
            os.path.join(PROJECT_ROOT, "config_private.ini"),
            os.path.join(PROJECT_ROOT, "config.ini"),
        ]
    )
    if not parser.has_section("NEO4J"):
        return None, None, None, None
    section = parser["NEO4J"]
    return section.get("URI"), section.get("USERNAME"), section.get("PASSWORD"), section.get("DATABASE")


def _get_nonempty_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill embeddings on Chunk nodes")
    p.add_argument("--provider", default="ollama", choices=["ollama", "openai"], help="Embedding provider")
    p.add_argument("--model", default="mxbai-embed-large:latest", help="Embedding model name")
    p.add_argument("--batch-size", type=int, default=100, help="Rows per fetch")
    p.add_argument("--chunk-label", default="Chunk", help="Chunk label to process")
    p.add_argument("--embedding-property", default="embedding", help="Property name for vector")
    p.add_argument(
        "--text-properties",
        default="text,content,body,chunkText,value",
        help="Comma-separated text property priority",
    )
    p.add_argument("--project", default="", help="Optional projectName filter")
    p.add_argument("--database", default="", help="Optional Neo4j database name")
    p.add_argument("--list-projects", action="store_true", help="List Project node names and exit")
    p.add_argument(
        "--max-chars",
        type=int,
        default=1000,
        help="Truncate chunk text to this many chars before embedding (0 disables truncation)",
    )
    p.add_argument("--dry-run", action="store_true", help="Do not write embeddings")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    cfg_uri, cfg_user, cfg_password, cfg_database = _read_neo4j_from_config()

    uri = _get_nonempty_env("NEO4J_URI") or cfg_uri
    user = _get_nonempty_env("NEO4J_USER") or cfg_user
    password = _get_nonempty_env("NEO4J_PASSWORD") or cfg_password
    database = args.database or _get_nonempty_env("NEO4J_DATABASE") or cfg_database

    if not uri:
        print("Missing NEO4J_URI (env or config.ini/config_private.ini)", file=sys.stderr)
        return 2

    # Allow auth-less Neo4j instances by making credentials optional.
    use_auth = bool(user) and password is not None and password != ""
    if bool(user) != bool(password):
        print("NEO4J_USER/NEO4J_PASSWORD are incomplete; falling back to no-auth connection", file=sys.stderr)

    print(f"Neo4j target: uri={uri} database={database or '<default>'} auth={'user/pass' if use_auth else 'none'}")

    registry = ProviderRegistry()
    provider = registry.get_provider(args.provider)

    text_props = [x.strip() for x in args.text_properties.split(",") if x.strip()]
    if not text_props:
        print("No text properties configured", file=sys.stderr)
        return 2

    # For auth-disabled servers, send an explicit no-auth token.
    auth_token = (user, password) if use_auth else custom_auth(None, None, None, "none")
    driver = GraphDatabase.driver(uri, auth=auth_token)

    try:
        driver.verify_connectivity()
    except AuthError as e:
        print(
            "Neo4j authentication failed. If Browser connects without typing a password, it likely uses saved credentials. "
            "Set NEO4J_USER/NEO4J_PASSWORD env vars or fill [NEO4J] USERNAME/PASSWORD in config.ini/config_private.ini.",
            file=sys.stderr,
        )
        print(f"Driver error: {e}", file=sys.stderr)
        driver.close()
        return 2

    if args.list_projects:
        with driver.session(database=database or None) as session:
            rows = session.run(
                "MATCH (s:Project) RETURN s.name AS name ORDER BY s.name"
            ).data()
        for row in rows:
            print(row.get("name"))
        driver.close()
        return 0

    fetch_cypher = f"""
    MATCH (c:{args.chunk_label})
    WHERE c.{args.embedding_property} IS NULL
      AND ($project = '' OR c.projectName = $project)
    RETURN elementId(c) AS eid, c.id_rc AS id_rc, c.text AS text, c.content AS content, c.body AS body, c.chunkText AS chunkText, c.value AS value
    LIMIT $limit
    """

    write_cypher = f"""
    MATCH (c)
    WHERE elementId(c) = $eid
    SET c.{args.embedding_property} = $embedding
    """

    processed = 0
    skipped = 0
    failed = 0

    with driver.session(database=database or None) as session:
        while True:
            rows = session.run(fetch_cypher, project=args.project, limit=args.batch_size).data()
            if not rows:
                break

            for row in rows:
                text = _pick_text(row, text_props)
                if not text:
                    skipped += 1
                    continue

                if args.max_chars > 0 and len(text) > args.max_chars:
                    text = text[: args.max_chars]

                try:
                    emb = provider.embed(EmbedRequest(text=text, model=args.model)).embedding
                except Exception as e:
                    failed += 1
                    print(
                        f"embed-fail eid={row.get('eid')} chars={len(text)} err={type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    continue

                if not args.dry_run:
                    session.run(write_cypher, eid=row["eid"], embedding=emb).consume()
                processed += 1

            print(f"processed={processed} skipped={skipped} failed={failed}")

            if args.dry_run:
                print("dry-run mode: stopping after first batch to avoid re-reading unchanged NULL rows")
                break

    driver.close()
    print(f"Done. processed={processed} skipped={skipped} failed={failed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
