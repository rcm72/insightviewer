"""Project-scoped Chunk embedding backfill used by the operations API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ai.registry import ProviderRegistry
from ai.types import EmbedRequest
from ai.vector_config import VECTOR_DIMENSIONS

TEXT_PROPERTIES = ("text", "content", "body", "chunkText", "value")
BATCH_SIZE = 32
MAX_EMBED_CHARS = 1000


def _text_from_row(row: dict[str, Any]) -> str:
    for key in TEXT_PROPERTIES:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:MAX_EMBED_CHARS]
    return ""


def inspect_vector_index(session, index_name: str) -> tuple[str | None, int | None, list[str], list[str]]:
    row = session.run(
        """
        SHOW VECTOR INDEXES YIELD name, state, options, labelsOrTypes, properties
        WHERE name = $index_name
        RETURN state, options, labelsOrTypes, properties
        """,
        index_name=index_name,
    ).single()
    if not row:
        return None, None, [], []

    options = row.get("options") or {}
    index_config = options.get("indexConfig") or {}
    dimensions = index_config.get("vector.dimensions")
    try:
        dimensions = int(dimensions) if dimensions is not None else None
    except (TypeError, ValueError):
        dimensions = None
    labels = [str(value) for value in (row.get("labelsOrTypes") or [])]
    properties = [str(value) for value in (row.get("properties") or [])]
    return str(row.get("state") or ""), dimensions, labels, properties


def run_embedding_backfill(
    *,
    driver,
    project: str,
    provider_id: str,
    model: str,
    index_name: str,
    update_job: Callable[..., None],
) -> None:
    """Generate vectors for missing Chunk embeddings in exactly one project."""
    with driver.session() as session:
        index_state, index_dimensions, index_labels, index_properties = inspect_vector_index(session, index_name)
        if index_state != "ONLINE":
            raise RuntimeError(f"Vector index '{index_name}' must be ONLINE before generating embeddings.")
        if "Chunk" not in index_labels or "embedding" not in index_properties:
            raise RuntimeError(f"Vector index '{index_name}' must index Chunk.embedding.")
        if index_dimensions != VECTOR_DIMENSIONS:
            raise RuntimeError(
                f"Vector index '{index_name}' must use {VECTOR_DIMENSIONS} dimensions; "
                f"found {index_dimensions if index_dimensions is not None else 'unspecified'}."
            )

        total_row = session.run(
            """
            MATCH (c:Chunk)
            WHERE c.projectName = $project AND c.embedding IS NULL
            RETURN count(c) AS total
            """,
            project=project,
        ).single()
        total = int((total_row or {}).get("total") or 0)

    update_job(status="running", total=total, started_at=datetime.now(timezone.utc).isoformat())
    if total == 0:
        update_job(status="completed", completed_at=datetime.now(timezone.utc).isoformat())
        return

    provider = ProviderRegistry().get_provider(provider_id)
    processed = 0
    skipped = 0
    failed = 0
    last_eid = ""
    error_samples: list[str] = []

    while True:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (c:Chunk)
                WHERE c.projectName = $project
                  AND c.embedding IS NULL
                  AND elementId(c) > $last_eid
                RETURN elementId(c) AS eid,
                       c.text AS text,
                       c.content AS content,
                       c.body AS body,
                       c.chunkText AS chunkText,
                       c.value AS value
                ORDER BY eid
                LIMIT $limit
                """,
                project=project,
                last_eid=last_eid,
                limit=BATCH_SIZE,
            ).data()

            if not rows:
                break

            for row in rows:
                eid = str(row.get("eid") or "")
                if not eid:
                    skipped += 1
                    continue
                last_eid = eid
                text = _text_from_row(row)
                if not text:
                    skipped += 1
                    continue

                try:
                    vector = provider.embed(
                        EmbedRequest(text=text, model=model, dimensions=VECTOR_DIMENSIONS)
                    ).embedding
                    if len(vector) != VECTOR_DIMENSIONS:
                        raise ValueError(
                            f"Embedding has {len(vector)} dimensions; expected {VECTOR_DIMENSIONS}."
                        )
                    session.run(
                        """
                        MATCH (c:Chunk)
                        WHERE elementId(c) = $eid
                          AND c.projectName = $project
                          AND c.embedding IS NULL
                        SET c.embedding = $embedding,
                            c.embeddingModel = $model,
                            c.embeddingProvider = $provider,
                            c.embeddedAt = datetime()
                        """,
                        eid=eid,
                        project=project,
                        embedding=vector,
                        model=model,
                        provider=provider_id,
                    ).consume()
                    processed += 1
                except Exception as exc:
                    failed += 1
                    if len(error_samples) < 5:
                        error_samples.append(f"{type(exc).__name__}: {str(exc)[:240]}")

                update_job(
                    processed=processed,
                    skipped=skipped,
                    failed=failed,
                    error_samples=list(error_samples),
                )

    update_job(
        status="completed",
        processed=processed,
        skipped=skipped,
        failed=failed,
        error_samples=error_samples,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
