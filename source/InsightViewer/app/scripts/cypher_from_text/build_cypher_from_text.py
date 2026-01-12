#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# cd /home/robert/insightViewer/source/InsightViewer/app/scripts/cypher_from_text

# docker exec -it neo4j cypher-shell


#  python build_cypher_from_text.py geo1_2_Podnebje.txt \
#   --project Geografija \
#   --out out.cypher \
#   --out-json payload.json

"""
Build Neo4j Cypher import script from a textbook-like .txt file.

Nodes created:
  (:GeoEntity:Chapter)
  (:GeoEntity:Section)
  (:GeoEntity:Chunk)

Properties on every node:
  projectName = <given>
  id_rc      = randomUUID()
  name       = <unique within project via key>
  key        = projectName + '|' + name

Relationships:
  (Chapter)-[:HAS_SECTION]->(Section)     (top-level sections)
  (Section)-[:HAS_SECTION]->(Section)     (subsections)
  (Section)-[:HAS_CHUNK]->(Chunk)
  (Chunk)-[:NEXT]->(Chunk)                (within same section)
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PAGE_RE = re.compile(r"^\s*Stran\s+(\d+)\s*$", re.IGNORECASE)

# Matches:
#  "2. PODNEBJE"  -> id="2" title="PODNEBJE"
#  "2.1 Uvod"     -> id="2.1" title="Uvod"
#  "2.2.1 ATMOSFERA IN NJENA SESTAVA" -> id="2.2.1" title="ATMOSFERA IN NJENA SESTAVA"
HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")


def cypher_escape(s: str) -> str:
    """Escape text for Cypher single-quoted string."""
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s


@dataclass
class Node:
    kind: str  # "Chapter" | "Section" | "SubSection" | "Chunk"
    sid: str   # structural id like "2.2.4" or chunk id like "2.2.4-0001"
    name: str  # must be unique within project via key
    page_start: Optional[int] = None
    order: Optional[int] = None
    title: Optional[str] = None
    text: Optional[str] = None
    parent_sid: Optional[str] = None  # for sections: parent section id or chapter id
    chunk_index: Optional[int] = None


@dataclass
class ParseState:
    current_page: Optional[int] = None
    current_section_sid: Optional[str] = None
    current_section_title: Optional[str] = None
    buffer_lines: List[str] = field(default_factory=list)


def normalize_whitespace(text: str) -> str:
    # Keep paragraph breaks, normalize internal whitespace
    lines = [ln.rstrip() for ln in text.split("\n")]
    # collapse multiple blank lines to max 2
    out = []
    blank = 0
    for ln in lines:
        if ln.strip() == "":
            blank += 1
            if blank <= 2:
                out.append("")
        else:
            blank = 0
            out.append(ln)
    return "\n".join(out).strip()


def split_into_paragraphs(text: str) -> List[str]:
    text = normalize_whitespace(text)
    if not text:
        return []
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_paragraphs(paragraphs: List[str], max_chars: int = 1400) -> List[str]:
    """
    Make chunks by concatenating paragraphs up to max_chars.
    max_chars is a simple proxy; you can tune it later.
    """
    chunks: List[str] = []
    cur: List[str] = []
    cur_len = 0

    for p in paragraphs:
        add_len = len(p) + (2 if cur else 0)
        if cur and cur_len + add_len > max_chars:
            chunks.append("\n\n".join(cur).strip())
            cur = [p]
            cur_len = len(p)
        else:
            if cur:
                cur.append(p)
                cur_len += add_len
            else:
                cur = [p]
                cur_len = len(p)

    if cur:
        chunks.append("\n\n".join(cur).strip())

    return chunks


def parent_of_section(section_id: str) -> str:
    """
    For "2.2.4" -> "2.2"
    For "2.2"   -> "2"
    For "2.1"   -> "2"
    """
    parts = section_id.split(".")
    if len(parts) == 1:
        return parts[0]
    return ".".join(parts[:-1])


def is_chapter_id(section_id: str) -> bool:
    return "." not in section_id


def flush_section(state: ParseState, sections_text: Dict[str, str]) -> None:
    if state.current_section_sid is None:
        return
    text = "\n".join(state.buffer_lines).strip()
    if text:
        sections_text[state.current_section_sid] = sections_text.get(state.current_section_sid, "") + "\n" + text
    state.buffer_lines = []


def parse_text(content: str) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Returns:
      headings: dict[sid] -> {title, pageStart, order, parent}
      sections_text: dict[sid] -> full text body under heading
    """
    headings: Dict[str, Dict] = {}
    sections_text: Dict[str, str] = {}
    state = ParseState()

    order_counter: Dict[str, int] = {}  # parentSid -> next order

    lines = content.splitlines()

    for raw in lines:
        line = raw.rstrip("\n")

        mpage = PAGE_RE.match(line)
        if mpage:
            state.current_page = int(mpage.group(1))
            continue

        mh = HEADING_RE.match(line)
        if mh:
            sid = mh.group(1).strip()
            title = mh.group(2).strip()

            # Commit previous section buffer
            flush_section(state, sections_text)

            # Determine parent
            parent = parent_of_section(sid) if not is_chapter_id(sid) else None
            if is_chapter_id(sid):
                parent_key = "ROOT"
            else:
                parent_key = parent if parent else "ROOT"

            order_counter[parent_key] = order_counter.get(parent_key, 0) + 1

            headings[sid] = {
                "sid": sid,
                "title": title,
                "pageStart": state.current_page,
                "order": order_counter[parent_key],
                "parent": parent,
            }

            state.current_section_sid = sid
            state.current_section_title = title
            state.buffer_lines = []
            continue

        # ordinary line -> add to current buffer
        if state.current_section_sid is not None:
            state.buffer_lines.append(line)

    # flush last
    flush_section(state, sections_text)

    # normalize body text
    for sid in list(sections_text.keys()):
        sections_text[sid] = normalize_whitespace(sections_text[sid])

    return headings, sections_text


def build_nodes(project: str, headings: Dict[str, Dict], sections_text: Dict[str, str],
                make_chunks: bool = True, max_chunk_chars: int = 1400) -> Tuple[List[Node], List[Tuple[str, str, str]]]:
    """
    Returns:
      nodes: list of Node
      rels:  list of (fromKey, relType, toKey)

    Hierarhija:
      Chapter      : npr. "2"
      Section      : npr. "2.1"
      SubSection   : npr. "2.1.1", "2.1.2" ...
      Chunk        : vsebinski koščki, pripeti na SubSection ali, če ga ni, na Section
    """
    nodes: List[Node] = []
    rels: List[Tuple[str, str, str]] = []

    # Identify chapter(s): headings with id like "2"
    chapters = [sid for sid in headings.keys() if is_chapter_id(sid)]
    chapters.sort(key=lambda x: [int(p) for p in x.split(".")])

    # Sections (prve podravni, npr. "2.1", "2.2")
    section_ids = [sid for sid in headings.keys() if not is_chapter_id(sid) and len(sid.split(".")) == 2]
    section_ids.sort(key=lambda x: [int(p) for p in x.split(".")])

    # SubSections (globji nivoji, npr. "2.1.1", "2.2.3.1" ...)
    subsection_ids = [sid for sid in headings.keys() if not is_chapter_id(sid) and len(sid.split(".")) > 2]
    subsection_ids.sort(key=lambda x: [int(p) for p in x.split(".")])

    # --- Chapter nodes ---
    for ch_id in chapters:
        title = headings[ch_id]["title"]
        page = headings[ch_id]["pageStart"]
        name = f"{ch_id} {title}"
        nodes.append(Node(
            kind="Chapter",
            sid=ch_id,
            name=name,
            page_start=page,
            order=headings[ch_id]["order"],
            title=title
        ))

    # --- Section nodes (level 2) ---
    for sid in section_ids:
        meta = headings[sid]
        title = meta["title"]
        page = meta["pageStart"]
        order = meta["order"]
        parent = meta["parent"]        # to je ID Chapterja
        name = f"{sid} {title}"
        nodes.append(Node(
            kind="Section",
            sid=sid,
            name=name,
            page_start=page,
            order=order,
            title=title,
            parent_sid=parent
        ))

    # --- SubSection nodes (level >= 3) ---
    for sid in subsection_ids:
        meta = headings[sid]
        title = meta["title"]
        page = meta["pageStart"]
        order = meta["order"]
        parent = meta["parent"]        # to je ID Section ali SubSection
        name = f"{sid} {title}"
        nodes.append(Node(
            kind="SubSection",
            sid=sid,
            name=name,
            page_start=page,
            order=order,
            title=title,
            parent_sid=parent
        ))

    # --- Structural relationships ---

    # 1) Chapter -> Section
    for sid in section_ids:
        parent = headings[sid]["parent"]    # npr. "2"
        if parent is None:
            continue
        if parent in headings:
            from_name = f"{parent} {headings[parent]['title']}"   # chapter name
            to_name = f"{sid} {headings[sid]['title']}"           # section name
            rels.append((project + "|" + from_name, "HAS_SECTION", project + "|" + to_name))

    # 2) Section/SubSection hierarchy
    #    Section -> SubSection, SubSection -> SubSection (globji nivoji)
    for sid in subsection_ids:
        parent = headings[sid]["parent"]
        if parent is None:
            continue
        if parent in headings:
            from_name = f"{parent} {headings[parent]['title']}"
            to_name = f"{sid} {headings[sid]['title']}"
            # lahko uporabiš isto relType (HAS_SECTION) ali novo (HAS_SUBSECTION)
            rels.append((project + "|" + from_name, "HAS_SECTION", project + "|" + to_name))

    # --- Chunks ---
    if make_chunks:
        # v chunkih gremo čez VSE sid-je, vključno s Chapter, Section in SubSection
        all_sids = chapters + section_ids + subsection_ids

        for sid in all_sids:
            body = sections_text.get(sid, "").strip()
            if not body:
                continue

            paragraphs = split_into_paragraphs(body)
            chunks = chunk_paragraphs(paragraphs, max_chars=max_chunk_chars)

            prev_chunk_key: Optional[str] = None
            for i, ch_text in enumerate(chunks, start=1):
                chunk_id = f"{sid}-{i:04d}"
                title = headings[sid]["title"] if sid in headings else ""
                chunk_name = f"{chunk_id} | {title}".strip()
                page = headings[sid]["pageStart"] if sid in headings else None

                node = Node(
                    kind="Chunk",
                    sid=chunk_id,
                    name=chunk_name,
                    page_start=page,
                    order=i,
                    title=title,
                    text=ch_text,
                    parent_sid=sid,
                    chunk_index=i,
                )
                nodes.append(node)

                # kam pripnemo Chunk?
                #  - če je sid v subsection_ids -> pripnemo na SubSection node
                #  - če je sid v section_ids    -> pripnemo na Section node
                #  - če je sid v chapters       -> po želji; tu ga lahko preskočimo ali pripnemo direktno
                if sid in subsection_ids or sid in section_ids:
                    section_name = f"{sid} {headings[sid]['title']}"
                    rels.append((project + "|" + section_name, "HAS_CHUNK", project + "|" + chunk_name))
                else:
                    # opcijsko: Chunks direktno na Chapter (redkeje)
                    ch_name = f"{sid} {headings[sid]['title']}"
                    rels.append((project + "|" + ch_name, "HAS_CHUNK", project + "|" + chunk_name))

                # NEXT med chunk-i znotraj istega sid
                chunk_key = project + "|" + chunk_name
                if prev_chunk_key is not None:
                    rels.append((prev_chunk_key, "NEXT", chunk_key))
                prev_chunk_key = chunk_key

    return nodes, rels


def generate_cypher(project: str, nodes: List[Node], rels: List[Tuple[str, str, str]],
                    create_indexes: bool = True) -> str:
    lines: List[str] = []
    lines.append("// --- Generated by build_cypher_from_text.py ---")
    lines.append(f"// Project: {project}")
    lines.append("")

    if create_indexes:
        lines.append("// Constraints / Indexes")
        # key unique per label
        lines.append("CREATE CONSTRAINT chapter_key_unique    IF NOT EXISTS FOR (n:Chapter)    REQUIRE n.key IS UNIQUE;")
        lines.append("CREATE CONSTRAINT section_key_unique    IF NOT EXISTS FOR (n:Section)    REQUIRE n.key IS UNIQUE;")
        lines.append("CREATE CONSTRAINT subsection_key_unique IF NOT EXISTS FOR (n:SubSection) REQUIRE n.key IS UNIQUE;")
        lines.append("CREATE CONSTRAINT chunk_key_unique      IF NOT EXISTS FOR (n:Chunk)      REQUIRE n.key IS UNIQUE;")
        # id_rc unique per label (če ga uporabljaš)
        lines.append("CREATE CONSTRAINT chapter_idrc_unique    IF NOT EXISTS FOR (n:Chapter)    REQUIRE n.id_rc IS UNIQUE;")
        lines.append("CREATE CONSTRAINT section_idrc_unique    IF NOT EXISTS FOR (n:Section)    REQUIRE n.id_rc IS UNIQUE;")
        lines.append("CREATE CONSTRAINT subsection_idrc_unique IF NOT EXISTS FOR (n:SubSection) REQUIRE n.id_rc IS UNIQUE;")
        lines.append("CREATE CONSTRAINT chunk_idrc_unique      IF NOT EXISTS FOR (n:Chunk)      REQUIRE n.id_rc IS UNIQUE;")
        # index na projectName (poljubno)
        lines.append("CREATE INDEX chapter_projectName    IF NOT EXISTS FOR (n:Chapter)    ON (n.projectName);")
        lines.append("CREATE INDEX section_projectName    IF NOT EXISTS FOR (n:Section)    ON (n.projectName);")
        lines.append("CREATE INDEX subsection_projectName IF NOT EXISTS FOR (n:SubSection) ON (n.projectName);")
        lines.append("CREATE INDEX chunk_projectName      IF NOT EXISTS FOR (n:Chunk)      ON (n.projectName);")
        lines.append("")

    # Nodes
    lines.append("// Nodes")
    lines.append("WITH $projectName AS projectName")
    lines.append("UNWIND $nodes AS row")
    lines.append("CALL {")
    lines.append("  WITH projectName, row")
    lines.append("  // Merge by key so reruns are idempotent")
    lines.append("  MERGE (n {key: row.key})")
    lines.append("  ON CREATE SET n.id_rc = randomUUID()")
    lines.append("  SET n.projectName = projectName,")
    lines.append("      n.name = row.name")
    lines.append("  // Set single label (Chapter / Section / Chunk)")
    lines.append("  WITH n, row")
    lines.append("  CALL apoc.create.setLabels(n, [row.label]) YIELD node")
    lines.append("  WITH node, row")
    lines.append("  // Optional properties")
    lines.append("  SET node.sid       = row.sid")
    lines.append("  FOREACH (_ IN CASE WHEN row.title IS NULL THEN [] ELSE [1] END | SET node.title = row.title)")
    lines.append("  FOREACH (_ IN CASE WHEN row.pageStart IS NULL THEN [] ELSE [1] END | SET node.pageStart = row.pageStart)")
    lines.append("  FOREACH (_ IN CASE WHEN row.order IS NULL THEN [] ELSE [1] END | SET node.order = row.order)")
    lines.append("  FOREACH (_ IN CASE WHEN row.text IS NULL THEN [] ELSE [1] END | SET node.text = row.text)")
    lines.append("  RETURN 1 AS ok")
    lines.append("}")
    lines.append("RETURN count(*) AS nodes_processed;")
    lines.append("")

    # Relationships
    lines.append("// Relationships")
    lines.append("WITH $rels AS rels")
    lines.append("UNWIND rels AS r")
    lines.append("MATCH (a {key: r.fromKey})")
    lines.append("MATCH (b {key: r.toKey})")
    lines.append("CALL {")
    lines.append("  WITH a, b, r")
    lines.append("  // Dynamic relationship type requires APOC")
    lines.append("  CALL apoc.create.relationship(a, r.type, {}, b) YIELD rel")
    lines.append("  RETURN 1 AS ok")
    lines.append("}")
    lines.append("RETURN count(*) AS rels_processed;")
    lines.append("")

    lines.insert(0, "// NOTE: This script expects parameters: projectName, nodes, rels")
    lines.insert(1, "// Run via cypher-shell with --param or from driver. If you want a pure .cypher without params, tell me.")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Read textbook .txt and generate Cypher (with params payload).")
    ap.add_argument("input", type=Path, help="Input .txt file")
    ap.add_argument("--project", default="Geografija", help="projectName value (default: Geografija)")
    ap.add_argument("--out", type=Path, default=Path("out.cypher"), help="Output .cypher file")
    ap.add_argument("--out-json", type=Path, default=Path("payload.json"),
                    help="JSON payload for params (nodes, rels, projectName)")
    ap.add_argument("--max-chunk-chars", type=int, default=1400, help="Max chars per chunk (default 1400)")
    ap.add_argument("--no-chunks", action="store_true", help="Do not create Chunk nodes")
    ap.add_argument("--no-indexes", action="store_true", help="Do not include constraints/indexes")
    args = ap.parse_args()

    content = args.input.read_text(encoding="utf-8")
    headings, sections_text = parse_text(content)

    nodes, rels = build_nodes(
        project=args.project,
        headings=headings,
        sections_text=sections_text,
        make_chunks=not args.no_chunks,
        max_chunk_chars=args.max_chunk_chars
    )

    # Build payload (Neo4j param-friendly)
    import json

    payload_nodes = []
    for n in nodes:
        row = {
            "key": f"{args.project}|{n.name}",
            "name": n.name,
            "sid": n.sid,
            "title": n.title,
            "pageStart": n.page_start,
            "order": n.order,
            "text": n.text,
            "label": n.kind,  # "Chapter" | "Section" | "Chunk"
        }
        payload_nodes.append(row)

    payload_rels = [{"fromKey": f, "type": t, "toKey": to} for (f, t, to) in rels]

    payload = {
        "projectName": args.project,
        "nodes": payload_nodes,
        "rels": payload_rels,
    }

    # Write payload json
    args.out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write cypher (parameterized)
    cypher = generate_cypher(args.project, nodes, rels, create_indexes=not args.no_indexes)
    args.out.write_text(cypher, encoding="utf-8")

    print(f"OK: wrote {args.out} and {args.out_json}")
    print("Requires APOC for dynamic labels + relationships (apoc.create.*).")


if __name__ == "__main__":
    main()

