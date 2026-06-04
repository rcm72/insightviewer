from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from ai.errors import AIError, ProviderConfigError, ProviderRequestError, ProviderResponseError
from ai.registry import ProviderRegistry
from ai.selection import (
    COOKIE_MODEL,
    COOKIE_PROVIDER,
    default_selection,
    get_selection_from_request,
    selection_to_json,
    validate_selection,
)
from ai.types import ChatRequest, ModelSelection
from graph.context import fetch_graph_context, format_context_for_prompt


ai_graph_bp = Blueprint("ai_graph", __name__, url_prefix="/api/ai")

driver = None


def _fetch_node_type_names(session, project):
    cypher = """
    MATCH (n:NodeType)
    WHERE $project IS NULL OR n.projectName = $project OR n.projectName IS NULL
    RETURN DISTINCT n.name AS name
    ORDER BY name
    LIMIT 200
    """
    rows = session.run(cypher, project=project).data()
    if not rows and project:
        rows = session.run(cypher, project=None).data()
    return [str(row.get("name") or "").strip() for row in rows if str(row.get("name") or "").strip()]


def init_driver(d) -> None:
    global driver
    driver = d


def _ensure_driver() -> None:
    if driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver(driver) on startup.")


def _provider_models_map(registry: ProviderRegistry) -> dict[str, list[str]]:
    return {p.id: p.models for p in registry.list_providers()}


def _parse_selection(payload: dict[str, Any]) -> ModelSelection:
    req_selection = get_selection_from_request(request)
    provider = (payload.get("provider") or req_selection.provider or default_selection().provider)
    model = (payload.get("model") or req_selection.model or default_selection().model)
    provider = str(provider).strip().lower()
    model = str(model).strip()

    if provider not in ("openai", "ollama"):
        raise ValueError("provider must be one of: openai, ollama")
    if not model:
        raise ValueError("model is required")

    return ModelSelection(provider=provider, model=model)  # type: ignore[arg-type]


def _normalize_node_ids(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("node_ids")
    if not isinstance(raw, list):
        raise ValueError("node_ids must be a list of id_rc strings")
    out: list[str] = []
    for x in raw:
        s = str(x or "").strip()
        if s:
            out.append(s)
    # preserve order, remove duplicates
    unique: list[str] = []
    seen: set[str] = set()
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    if not unique:
        raise ValueError("node_ids must not be empty")
    if len(unique) > 50:
        raise ValueError("node_ids supports at most 50 entries")
    return unique


def _collect_chunks_by_depth(
    session,
    node_ids: list[str],
    depth: int,
    project: str | None,
    chunk_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    depth = max(0, int(depth))

    visited_query = f"""
        UNWIND $node_ids AS nid
        MATCH (s {{id_rc: nid}})
        WHERE $project IS NULL OR s.projectName = $project
        WITH collect(DISTINCT s) AS starts
        UNWIND starts AS s
        MATCH p = (s)-[*0..{depth}]-(v)
        WHERE ALL(n IN nodes(p) WHERE $project IS NULL OR n.projectName = $project OR n:Chunk)
        WITH collect(DISTINCT v) AS all_nodes
        UNWIND all_nodes AS n
        WITH DISTINCT n
        RETURN n.id_rc AS id_rc, labels(n) AS labels, n.name AS name
        LIMIT 2000
    """
    rows = session.run(
        visited_query,
        node_ids=node_ids,
        project=project,
    ).data()

    visited_nodes = [
        {
            "id_rc": r.get("id_rc"),
            "labels": r.get("labels") or [],
            "name": r.get("name"),
        }
        for r in rows
        if r.get("id_rc")
    ]

 

    # chunks_query = f"""
    #     UNWIND $node_ids AS nid
    #     MATCH (s {{id_rc: nid}})
    #     WHERE $project IS NULL OR s.projectName = $project
    #     WITH collect(DISTINCT s) AS starts
    #     UNWIND starts AS s
    #     MATCH p = (s)-[*0..{depth}]-(v)
    #     WHERE ALL(n IN nodes(p) WHERE $project IS NULL OR n.projectName = $project OR n:Chunk)
    #     WITH collect(DISTINCT v) AS all_nodes
    #     UNWIND all_nodes AS n
    #     WITH DISTINCT n
    #     OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c1:Chunk)
    #     WITH collect(DISTINCT c1) + collect(DISTINCT c2) AS cs
    #     UNWIND cs AS c
    #     WITH DISTINCT c
    #     WHERE c IS NOT NULL
    #     RETURN
    #       c.id_rc AS id_rc,
    #       labels(c) AS labels,
    #       coalesce(c.text, c.content, c.body, c.chunkText, c.value, '') AS text
    #     LIMIT $chunk_limit
    # """

    chunks_query = f"""
        UNWIND $node_ids AS nid
        MATCH (s  {{id_rc: nid}})
        WHERE $project IS NULL OR s.projectName = $project

        MATCH p = (s)-[*0..{depth}]-(n)
        WHERE ALL(x IN nodes(p) WHERE $project IS NULL OR x.projectName = $project OR x:Chunk)

        WITH n, min(length(p)) AS dist
        WITH DISTINCT n, dist

        OPTIONAL MATCH (n)-[:HAS_CHUNK]->(c:Chunk)
        WHERE c IS NOT NULL

        WITH c, min(dist) AS min_dist
        RETURN
        c.id_rc AS id_rc,
        labels(c) AS labels,
        coalesce(c.text, c.content, c.body, c.chunkText, c.value, '') AS text,
        min_dist
        ORDER BY min_dist ASC, id_rc ASC
        LIMIT $chunk_limit
    """   

    print(chunks_query)
    print(f"{{depth}}")
    print(f"traversal = [*0..{depth}]")    
    print(f"chunk_limit = {chunk_limit}")

    chunk_rows = session.run(
        chunks_query,
        node_ids=node_ids,
        project=project,
        chunk_limit=int(chunk_limit),
    ).data()

    chunks = [
        {
            "id_rc": r.get("id_rc"),
            "labels": r.get("labels") or ["Chunk"],
            "text": str(r.get("text") or "").strip(),
        }
        for r in chunk_rows
        if str(r.get("text") or "").strip()
    ]
    return visited_nodes, chunks


def _chunks_to_prompt(chunks: list[dict[str, Any]], max_chars: int) -> str:
    parts: list[str] = []
    total = 0
    for i, ch in enumerate(chunks, start=1):
        cid = ch.get("id_rc") or f"chunk-{i}"
        txt = str(ch.get("text") or "").strip()
        if not txt:
            continue
        if len(txt) > 1400:
            txt = txt[:1400].rstrip() + " ..."
        block = f"[Chunk {i} | id_rc={cid}]\n{txt}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts).strip()


@ai_graph_bp.route("/providers", methods=["GET"])
def list_ai_providers():
    registry = ProviderRegistry()
    providers = [
        {
            "id": p.id,
            "label": p.label,
            "models": p.models,
        }
        for p in registry.list_providers()
    ]
    return jsonify({"success": True, "providers": providers})


@ai_graph_bp.route("/graph/ask", methods=["POST"])
def ask_graph():
    try:
        _ensure_driver()
        payload = request.get_json(silent=True) or {}

        question = str(payload.get("question") or "").strip()
        if not question:
            return jsonify({"success": False, "error": "question is required"}), 400

        registry = ProviderRegistry()
        provider_models = _provider_models_map(registry)

        requested_selection = _parse_selection(payload)
        model_explicitly_set = bool(str(payload.get("model") or "").strip())
        # If the caller explicitly set model, honor it even if it is not listed in config.
        # This avoids silent fallback to a different model and makes API behavior predictable.
        if model_explicitly_set:
            selection = requested_selection
        else:
            selection = validate_selection(requested_selection, provider_models)
        provider = registry.get_provider(selection.provider)

        project = payload.get("project")
        sample_limit = int(payload.get("sample_limit") or 8)
        sample_limit = max(1, min(sample_limit, 30))

        with driver.session() as session:
            ctx = fetch_graph_context(session, project=project, sample_limit=sample_limit)
            node_type_names = _fetch_node_type_names(session, project)

        prompt_parts = [format_context_for_prompt(ctx).strip()]
        if node_type_names:
            shown = ", ".join(node_type_names[:80])
            suffix = " ..." if len(node_type_names) > 80 else ""
            prompt_parts.append(f"Known NodeType names:\n- {shown}{suffix}")

        prompt_parts.append(
            "Instructions:\n"
            "- Base your answer on graph context when possible.\n"
            "- When writing Cypher that traverses paths, always use this exact RETURN pattern:\n"
            "    MATCH p = (a)-[*1..N]-(b)\n"
            "    UNWIND relationships(p) AS r\n"
            "    RETURN DISTINCT startNode(r) AS s, r AS rel, endNode(r) AS t\n"
            "  Rules: (1) return the relationship object r itself (aliased, e.g. AS rel) — NEVER type(r) or any scalar in place of r;\n"
            "  (2) do NOT add extra scalar columns such as type(r) AS relationshipType;\n"
            "  (3) do NOT RETURN p directly.\n"
            "- If context is insufficient, say what additional graph data is needed."
        )
        prompt_parts.append(f"User question:\n{question}")

        system_prompt = str(
            payload.get("system")
            or "You are a Neo4j graph assistant. Use only known graph context, state uncertainty when needed."
        ).strip()

        user_prompt = "\n\n".join(part for part in prompt_parts if part).strip()

        temperature = float(payload.get("temperature") or 0.2)
        max_tokens = int(payload.get("max_tokens") or 1200)

        resp = provider.chat(
            ChatRequest(
                system=system_prompt,
                user=user_prompt,
                model=selection.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        out = jsonify(
            {
                "success": True,
                "provider": selection.provider,
                "model": selection.model,
                "selection": selection_to_json(selection),
                "graph_context": {
                    "project": ctx.project,
                    "labels": ctx.labels,
                    "relationship_types": ctx.rel_types,
                    "sample_nodes": ctx.sample_nodes,
                    "node_types": node_type_names,
                },
                "answer": resp.text,
            }
        )
        out.set_cookie(COOKIE_PROVIDER, selection.provider, max_age=60 * 60 * 24 * 30, samesite="Lax")
        out.set_cookie(COOKIE_MODEL, selection.model, max_age=60 * 60 * 24 * 30, samesite="Lax")
        return out

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ProviderConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except ProviderRequestError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except ProviderResponseError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except AIError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Unexpected error: {e}"}), 500


@ai_graph_bp.route("/graph/ask-by-depth", methods=["POST"])
def ask_graph_by_depth():
    try:
        _ensure_driver()
        payload = request.get_json(silent=True) or {}

        question = str(payload.get("question") or "").strip()
        if not question:
            return jsonify({"success": False, "error": "question is required"}), 400

        node_ids = _normalize_node_ids(payload)
        depth = int(payload.get("depth") or 2)
        depth = max(0, min(depth, 100))
        chunk_limit = int(payload.get("chunk_limit") or 80)
        chunk_limit = max(1, min(chunk_limit, 300))
        max_chunk_chars = int(payload.get("max_chunk_chars") or 18000)
        max_chunk_chars = max(2000, min(max_chunk_chars, 60000))
        project = (str(payload.get("project") or "").strip() or None)

        with driver.session() as session:
            visited_nodes, chunks = _collect_chunks_by_depth(
                session=session,
                node_ids=node_ids,
                depth=depth,
                project=project,
                chunk_limit=chunk_limit,
            )

        if not chunks:
            suggestion = (
                f"No text chunks were found within traversal depth {depth}. "
                f"Visited {len(visited_nodes)} node(s) — none had attached chunks. "
                f"Try increasing the traversal depth (currently {depth}) to reach more nodes, "
                "or verify that the selected nodes have neighbours with HAS_CHUNK relationships."
            )
            return jsonify(
                {
                    "success": True,
                    "provider": None,
                    "model": None,
                    "answer": suggestion,
                    "retrieval": {
                        "project": project,
                        "input_node_ids": node_ids,
                        "depth": depth,
                        "visited_nodes_count": len(visited_nodes),
                        "chunks_count": 0,
                        "visited_nodes": visited_nodes[:200],
                        "chunks": [],
                    },
                }
            )

        registry = ProviderRegistry()
        provider_models = _provider_models_map(registry)
        requested_selection = _parse_selection(payload)
        model_explicitly_set = bool(str(payload.get("model") or "").strip())
        if model_explicitly_set:
            selection = requested_selection
        else:
            selection = validate_selection(requested_selection, provider_models)
        provider = registry.get_provider(selection.provider)

        with driver.session() as session:
            ctx = fetch_graph_context(session, project=project, sample_limit=8)
            node_type_names = _fetch_node_type_names(session, project)

        schema_parts = [format_context_for_prompt(ctx).strip()]
        if node_type_names:
            shown = ", ".join(node_type_names[:80])
            suffix = " ..." if len(node_type_names) > 80 else ""
            schema_parts.append(f"Known NodeType names:\n- {shown}{suffix}")
        schema_block = "\n\n".join(schema_parts)

        chunks_block = _chunks_to_prompt(chunks, max_chars=max_chunk_chars)
        system_prompt = str(
            payload.get("system")
            or (
                "You are a knowledgeable assistant. Prefer the provided chunk evidence when answering, "
                "but you may also use your general knowledge to complement or clarify when the chunks "
                "are insufficient. Always indicate when you are drawing on general knowledge."
            )
        ).strip()

        user_prompt = (
            f"{schema_block}\n\n"
            "Retrieved evidence from graph traversal.\n"
            f"- project: {project or 'ALL'}\n"
            f"- start_node_ids: {', '.join(node_ids)}\n"
            f"- traversal_depth: {depth}\n"
            f"- visited_nodes_count: {len(visited_nodes)}\n"
            f"- chunks_count: {len(chunks)}\n\n"
            "Evidence chunks:\n"
            f"{chunks_block}\n\n"
            "Task instructions:\n"
            "- Prefer the evidence chunks when answering; use your general knowledge to fill gaps when chunks are insufficient.\n"
            "- Use only label names and relationship types from the graph context above.\n"
            "- Do NOT add projectName filters to any Cypher query you write.\n"
            "- When writing Cypher that traverses paths, always use this exact RETURN pattern:\n"
            "    MATCH p = (a)-[*1..N]-(b)\n"
            "    UNWIND relationships(p) AS r\n"
            "    RETURN DISTINCT startNode(r) AS s, r AS rel, endNode(r) AS t\n"
            "  Rules: (1) return the relationship object r itself (aliased, e.g. AS rel) — NEVER type(r) or any scalar in place of r;\n"
            "  (2) do NOT add extra scalar columns such as type(r) AS relationshipType;\n"
            "  (3) do NOT RETURN p directly.\n"
            "- If uncertain, say so and mention which chunk ID_RC are relevant.\n"
            "- If you can't answer suggest increasing the depth or chunk size.\n"
            "- Prefer concise and factual answers.\n"
            + (f"- {str(payload.get('extra_instructions')).strip()}\n" if payload.get("extra_instructions") else "")
            + f"\nUser question:\n{question}"
        )

        temperature = float(payload.get("temperature") or 0.2)
        max_tokens = int(payload.get("max_tokens") or 1400)

        resp = provider.chat(
            ChatRequest(
                system=system_prompt,
                user=user_prompt,
                model=selection.model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        out = jsonify(
            {
                "success": True,
                "provider": selection.provider,
                "model": selection.model,
                "selection": selection_to_json(selection),
                "answer": resp.text,
                "retrieval": {
                    "project": project,
                    "input_node_ids": node_ids,
                    "depth": depth,
                    "visited_nodes_count": len(visited_nodes),
                    "chunks_count": len(chunks),
                    "visited_nodes": visited_nodes[:200],
                    "chunks": chunks,
                },
            }
        )
        out.set_cookie(COOKIE_PROVIDER, selection.provider, max_age=60 * 60 * 24 * 30, samesite="Lax")
        out.set_cookie(COOKIE_MODEL, selection.model, max_age=60 * 60 * 24 * 30, samesite="Lax")
        return out

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except ProviderConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except ProviderRequestError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except ProviderResponseError as e:
        return jsonify({"success": False, "error": str(e)}), 502
    except AIError as e:
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Unexpected error: {e}"}), 500
