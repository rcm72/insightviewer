#!/usr/bin/env python3
import argparse
import os
import sys
import importlib
from typing import Iterable

from neo4j import GraphDatabase

APP_ROOT = "/home/robert/insightViewer/source/InsightViewer/app"
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

    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not uri or not user or not password:
        print("Missing NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD in environment", file=sys.stderr)
        return 2

    registry = ProviderRegistry()
    provider = registry.get_provider(args.provider)

    text_props = [x.strip() for x in args.text_properties.split(",") if x.strip()]
    if not text_props:
        print("No text properties configured", file=sys.stderr)
        return 2

    driver = GraphDatabase.driver(uri, auth=(user, password))

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

    with driver.session() as session:
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
