from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class GraphContext:
    project: str | None
    labels: list[str]
    rel_types: list[str]
    sample_nodes: list[dict[str, Any]]


def _flatten_labels(rows: Iterable[dict[str, Any]]) -> list[str]:
    out: set[str] = set()
    for r in rows:
        ls = r.get("labels") or []
        if isinstance(ls, list):
            for x in ls:
                if isinstance(x, str) and x:
                    out.add(x)
    return sorted(out)


def fetch_graph_context(session, project: str | None, sample_limit: int = 8) -> GraphContext:
    """
    Fetch lightweight schema-ish context to ground LLM prompts.
    Avoids privileged procedures and returns only small samples.
    """
    proj = (project or "").strip() or None

    # Distinct labels used by nodes in the project
    label_rows = session.run(
        """
        MATCH (n)
        WHERE $project IS NULL OR n.projectName = $project
        RETURN DISTINCT labels(n) AS labels
        LIMIT 200
        """,
        project=proj,
    ).data()
    labels = _flatten_labels(label_rows)

    # Distinct relationship types (limit).
    # Many graphs do not store projectName on relationships, only on nodes,
    # so filter by endpoints as fallback to avoid returning an empty set.
    rel_rows = session.run(
        """
        MATCH (a)-[r]->(b)
        WHERE $project IS NULL
           OR r.projectName = $project
           OR a.projectName = $project
           OR b.projectName = $project
        RETURN DISTINCT type(r) AS t
        LIMIT 200
        """,
        project=proj,
    ).data()
    rel_types = sorted([r.get("t") for r in rel_rows if isinstance(r.get("t"), str)])

    # Small node sample for naming conventions
    sample_rows = session.run(
        """
        MATCH (n)
        WHERE $project IS NULL OR n.projectName = $project
        RETURN labels(n) AS labels, n.name AS name, n.id_rc AS id_rc
        LIMIT $lim
        """,
        project=proj,
        lim=int(sample_limit),
    ).data()
    sample_nodes = [
        {
            "labels": r.get("labels"),
            "name": r.get("name"),
            "id_rc": r.get("id_rc"),
        }
        for r in sample_rows
    ]

    return GraphContext(project=proj, labels=labels, rel_types=rel_types, sample_nodes=sample_nodes)


def format_context_for_prompt(ctx: GraphContext) -> str:
    parts: list[str] = []
    parts.append("Graph context:")
    parts.append(f"- project: {ctx.project or 'ALL'}")
    if ctx.labels:
        parts.append(f"- labels: {', '.join(ctx.labels[:50])}" + (" ..." if len(ctx.labels) > 50 else ""))
    if ctx.rel_types:
        parts.append(f"- relationship_types: {', '.join(ctx.rel_types[:50])}" + (" ..." if len(ctx.rel_types) > 50 else ""))
    if ctx.sample_nodes:
        parts.append("- sample_nodes:")
        for n in ctx.sample_nodes[:8]:
            parts.append(f"  - labels={n.get('labels')} name={n.get('name')} id_rc={n.get('id_rc')}")
    return "\n".join(parts).strip() + "\n"

