#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate "Vsebina" HTML from a template (structure_Vsebina.html) and a data file (data.txt).

Input data format (preferred):
  <<2. Vsak organizem je zgrajen vsaj iz ene celice>>
  ... body ...
  <<2.0 Uvod>>
  ... body ...
  <<2.1 Prokariontska celica>>
  ... body ...

Fallback (if markers are missing and fallback is allowed):
  2. Vsak organizem ...
  2.0 Uvod
  2.1 Prokariontska celica
  ...

Output:
  An HTML file keeping the template structure and replacing the main content area
  with generated <details>/<summary> nested sections.

Usage:
  python generate_content.py --template structure_Vsebina.html --data data.txt --out out.html
  python generate_content.py --template structure_Vsebina.html --data data.txt --out out.html --marked-only
  python generate_content.py --template structure_Vsebina.html --data data.txt --out out.html --no-fallback
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Dict, List, Tuple


def is_false_heading(title: str) -> bool:
    """Heuristic: skip typical false headings like equations or references."""
    if any(ch in title for ch in ["→", "=", "+"]):
        return True
    t = title.strip().lower()
    if t == "poglavju." or t.endswith(" poglavju.") or t.endswith("poglavju."):
        return True
    return False


def split_sid_title(heading_text: str) -> Tuple[str, str]:
    """Extract numeric sid and title from a heading string (without << >>)."""
    ht = heading_text.replace("<<", "").replace(">>", "").strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\s*(?:\.)?\s*(.*)$", ht)
    if m:
        sid = m.group(1)
        title = m.group(2).strip().lstrip(".").strip()
        return sid, title
    return "", ht


def sid_key(s: str) -> List[int]:
    return [int(x) for x in s.split(".") if x.isdigit()]


def parent_sid(sid: str) -> str | None:
    parts = sid.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else None


def parse_entries(data: str, marked_only: bool = False) -> List[dict]:
    """
    Parse data into entries:
      [{heading_text, sid, title, level, body}, ...]
    Prefer explicit <<...>> headings; if none and fallback allowed, fallback to numeric headings.
    If marked_only=True and no markers exist -> raise ValueError.
    """
    marked_heading_line = re.compile(r"^\s*<<\s*(.+?)\s*>>\s*$")
    plain_heading_line = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")

    lines = data.splitlines()
    has_markers = any(marked_heading_line.match(ln) for ln in lines)

    if marked_only and not has_markers:
        raise ValueError("marked-only mode enabled, but no <<...>> headings were found in data.txt")

    entries: List[dict] = []
    current = None

    def flush():
        nonlocal current
        if current is None:
            return
        current["body"] = "\n".join(current["body_lines"]).strip()
        entries.append(current)
        current = None

    # Marker mode
    if has_markers:
        for ln in lines:
            mm = marked_heading_line.match(ln)
            if mm:
                flush()
                heading_text = mm.group(1).strip()  # already without << >>
                sid, title = split_sid_title(heading_text)
                level = sid.count(".") if sid else 0
                current = {
                    "heading_text": heading_text,
                    "sid": sid,
                    "title": title,
                    "level": level,
                    "body_lines": [],
                }
            else:
                if current is not None:
                    current["body_lines"].append(ln)

        flush()
        return entries

    # If marked_only, we stop here (should not reach due to the earlier error)
    if marked_only:
        return []

    # Fallback: numeric headings only
    entries_fb: List[dict] = []
    current_heading = None
    buf: List[str] = []

    for ln in lines:
        m = plain_heading_line.match(ln)
        if m:
            sid, title = m.group(1).strip(), m.group(2).strip()
            if not is_false_heading(title):
                if current_heading is not None:
                    csid, ctitle = split_sid_title(current_heading)
                    entries_fb.append(
                        {
                            "heading_text": current_heading,
                            "sid": csid,
                            "title": ctitle,
                            "level": csid.count(".") if csid else 0,
                            "body": "\n".join(buf).strip(),
                        }
                    )
                current_heading = f"{sid} {title}".strip()
                buf = []
                continue

        if current_heading is not None:
            buf.append(ln)

    if current_heading is not None:
        csid, ctitle = split_sid_title(current_heading)
        entries_fb.append(
            {
                "heading_text": current_heading,
                "sid": csid,
                "title": ctitle,
                "level": csid.count(".") if csid else 0,
                "body": "\n".join(buf).strip(),
            }
        )

    # Normalize fallback entries to same schema (no body_lines)
    normalized: List[dict] = []
    for e in entries_fb:
        normalized.append(
            {
                "heading_text": e["heading_text"],
                "sid": e["sid"],
                "title": e["title"],
                "level": e["level"],
                "body": e.get("body", ""),
            }
        )
    return normalized


def body_to_html(text: str) -> str:
    """Convert body text into simple HTML blocks, preserving lists and captions."""
    if not text.strip():
        return ""

    lines = text.splitlines()
    out: List[str] = []
    i = 0

    while i < len(lines):
        ln = lines[i].rstrip()
        if not ln.strip():
            i += 1
            continue

        # bullet lists ("-" or "–")
        if re.match(r"^\s*[–-]\s+\S", ln):
            ul = []
            while i < len(lines) and re.match(r"^\s*[–-]\s+\S", lines[i]):
                item = re.sub(r"^\s*[–-]\s+", "", lines[i].strip())
                ul.append(f"<li>{html.escape(item)}</li>")
                i += 1
            out.append("<ul>\n" + "\n".join(ul) + "\n</ul>")
            continue

        # captions for "Slika"
        if re.match(r"^\s*Slika\s+\d", ln):
            out.append(f'<p class="caption">{html.escape(ln.strip())}</p>')
            i += 1
            continue

        # paragraph until blank (and not list/caption)
        para = [ln.strip()]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^\s*[–-]\s+\S", lines[i])
            and not re.match(r"^\s*Slika\s+\d", lines[i])
        ):
            para.append(lines[i].strip())
            i += 1

        out.append(f"<p>{html.escape(' '.join(para))}</p>")

    return "\n".join(out)


def chip(level: int, title: str) -> str:
    t = title.strip().lower()
    if t in {"vprašanja", "samoevalvacija"}:
        return '<span class="chip q">vprašanja</span>'
    if level == 0:
        return '<span class="chip sec">poglavje</span>'
    if level == 1:
        return '<span class="chip sec">section</span>'
    return '<span class="chip sub">subsection</span>'


def build_details_tree(entries: List[dict]) -> Tuple[str, str]:
    """
    Build nested <details> HTML.
    Returns: (chapter_display, generated_html_block)
    """
    nodes = []
    for e in entries:
        sid = e.get("sid", "")
        if not sid:
            continue
        nodes.append(
            {
                "sid": sid,
                "title": e.get("title", "") or e.get("heading_text", ""),
                "heading_text": e.get("heading_text", ""),
                "level": e.get("level", 0),
                "body": e.get("body", ""),
            }
        )

    if not nodes:
        return ("Vsebina", "<!-- No nodes parsed -->")

    by_sid: Dict[str, dict] = {n["sid"]: n for n in nodes}
    children: Dict[str, List[str]] = {n["sid"]: [] for n in nodes}

    for n in nodes:
        sid = n["sid"]
        p = parent_sid(sid)
        if p and p in children:
            children[p].append(sid)

    for k in children:
        children[k].sort(key=sid_key)

    chapter_sid = next((n["sid"] for n in nodes if n["level"] == 0), nodes[0]["sid"])
    chapter_title = by_sid[chapter_sid]["title"]
    chapter_display = f"{chapter_sid}. {chapter_title}".strip(". ")

    root_sections = children.get(chapter_sid, [])
    root_sections.sort(key=sid_key)

    def details_for(sid: str, open_attr: bool) -> str:
        n = by_sid[sid]
        level = n["level"]
        title = n["title"] or n["heading_text"]
        summary_text = f"{sid} {title}".strip()
        open_str = " open" if open_attr else ""

        parts = [
            f"<details{open_str}>",
            f"  <summary>{html.escape(summary_text)} {chip(level, title)}</summary>",
        ]

        body_html = body_to_html(n["body"])
        if body_html:
            parts.append('  <div class="content">')
            parts.append(body_html)
            parts.append("  </div>")

        for child in children.get(sid, []):
            child_open = (by_sid[child]["level"] == 1)
            parts.append(details_for(child, child_open))

        parts.append("</details>")
        return "\n".join(parts)

    chapter_block = [
        f"  <!-- {chapter_sid} (glavno poglavje) -->",
        "<details open>",
        f"  <summary>{html.escape(chapter_display)} {chip(0, chapter_title)}</summary>",
    ]

    # add chapter body (if any)
    ch_body_html = body_to_html(by_sid[chapter_sid]["body"])
    if ch_body_html:
        chapter_block.append('  <div class="content">')
        chapter_block.append(ch_body_html)
        chapter_block.append("  </div>")

    for sec in root_sections:
        chapter_block.append(details_for(sec, open_attr=True))

    chapter_block.append("</details>")

    return chapter_display, "\n" + "\n".join(chapter_block) + "\n"


def apply_to_template(template_html: str, chapter_display: str, generated_block: str) -> str:
    """Replace title/h1/label and the main content block in the template."""
    out = re.sub(
        r"<title>.*?</title>",
        f"<title>{html.escape('Poglavje: ' + chapter_display)}</title>",
        template_html,
        flags=re.DOTALL,
    )
    out = re.sub(r"<h1>.*?</h1>", f"<h1>{html.escape(chapter_display)}</h1>", out, count=1, flags=re.DOTALL)
    out = re.sub(r"<label>.*?</label>", f"<label>{html.escape(chapter_display)}</label>", out, count=1, flags=re.DOTALL)

    # Replace content between </header> and closing container + <script> (template style)
    m = re.search(r"(</header>\s*)(.*?)(\s*</div>\s*\n\n<script>)", out, flags=re.DOTALL | re.IGNORECASE)
    if m:
        out = out[:m.start(2)] + generated_block + out[m.end(2) :]
    else:
        # fallback: insert before script tag
        out = out.replace("</div>\n\n<script>", generated_block + "\n</div>\n\n<script>")

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True, help="Path to structure_Vsebina.html")
    ap.add_argument("--data", required=True, help="Path to data.txt")
    ap.add_argument("--out", required=True, help="Output HTML path")

    ap.add_argument(
        "--marked-only",
        "--no-fallback",
        dest="marked_only",
        action="store_true",
        help="Use ONLY <<...>> headings; do not fall back to numeric headings",
    )

    args = ap.parse_args()

    template_html = Path(args.template).read_text(encoding="utf-8", errors="ignore")
    data_text = Path(args.data).read_text(encoding="utf-8", errors="ignore")

    entries = parse_entries(data_text, marked_only=args.marked_only)
    chapter_display, generated_block = build_details_tree(entries)
    out_html = apply_to_template(template_html, chapter_display, generated_block)

    Path(args.out).write_text(out_html, encoding="utf-8")
    print(f"OK: wrote {args.out}")


if __name__ == "__main__":
    main()
