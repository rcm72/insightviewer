#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Generate flip card questions from data.txt using rules from rules.json
# Usage:
# python generate_flipcards_rules.py \
#   --template structure_flipCard.html \
#   --data data.txt \
#   --rules rules.json \
#   --out flipCard.html \
#   --marked-only

# python generate_flipcards_rules.py \
#   --template structure_flipCard.html \
#   --data data.txt \
#   --rules rules.json \
#   --out flipCard.html \
#   --no-rules

# field: "title" ali "heading" (lahko dodaš še "body", če želiš)
# contains_any: seznam ključnih besed (case-insensitive)
# qa: seznam vprašanj/odgovorov, ki se dodajo, ko se rule sproži

# DA – pravila v rules.json so dodatna vprašanja,
# ki se samodejno dodajo, če se v poglavju pojavi določena tema.

# Ne nadomeščajo osnovnih vprašanj.
# So dodatek za globlje razumevanje.

# Kako generator razmišlja (mentalni model)

# Predstavljaj si učitelja, ki dela takole:

# Vedno vpraša:

# »Kaj je bistvo tega razdelka?«

# »Naštej glavne točke.«

# Včasih, če vidi določeno temo, doda:

# »Primerjaj …«

# »Pojasni pot …«

# »Zakaj …«

# 👉 rules.json opisuje to drugo vrsto vprašanj.

# Kaj se zgodi pri enem razdelku (korak za korakom)
# Primer razdelka v data.txt
# <<2.2.4 Golgijev aparat sprejema snovi>>

# 1️⃣ Generator vedno naredi osnovna vprašanja

# (iz besedila, ne glede na pravila):

# Pojasni bistvo razdelka …

# Naštej ključne točke … (če so alineje)

# To deluje za vsako poglavje, vsak predmet.

# 2️⃣ Generator pogleda rules.json in si reče:

# “Aha — naslov vsebuje besedo golgijev.”

# In v rules.json vidi pravilo:

# {
#   "match": {
#     "field": "title",
#     "contains_any": ["golgijev"]
#   },
#   "qa": [
#     {
#       "q": "Opiši pot beljakovine od sinteze do izločanja...",
#       "a": "Beljakovine nastanejo na ribosomih GER..."
#     }
#   ]
# }

# 3️⃣ Zato doda še eno dodatno vprašanje

# 👉 poleg osnovnih

# Zelo pomembno: česa pravila NE delajo

# ❌ Ne spreminjajo besedila
# ❌ Ne odstranjujejo osnovnih vprašanj
# ❌ Ne “ugibajo” iz vsebine
# ❌ Ne delujejo, če se tema ne pojavi



from __future__ import annotations

import argparse
import json
import re
import html
from pathlib import Path
from typing import Dict, List, Tuple, Any


MARKED_HEADING_RE = re.compile(r"^\s*<<\s*(.+?)\s*>>\s*$")
PLAIN_HEADING_RE  = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")


def is_false_heading(title: str) -> bool:
    if any(ch in title for ch in ["→", "=", "+"]):
        return True
    t = title.strip().lower()
    if t == "poglavju." or t.endswith(" poglavju.") or t.endswith("poglavju."):
        return True
    return False


def parse_sid_title(heading: str) -> Tuple[str, str]:
    ht = heading.replace("<<", "").replace(">>", "").strip()
    m = re.match(r"^\s*(\d+(?:\.\d+)*)\s*(?:\.)?\s*(.*)$", ht)
    if not m:
        return "", ht
    sid = m.group(1)
    title = m.group(2).strip().lstrip(".").strip()
    return sid, title


def chapter_prefix(sid: str) -> str:
    # 2.2.4 -> 2.2 ; 2.0 -> 2.0 ; 2 -> 2
    if not sid:
        return ""
    parts = sid.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return sid


def parse_sections(data_text: str, marked_only: bool) -> List[Dict[str, str]]:
    lines = data_text.splitlines()
    has_markers = any(MARKED_HEADING_RE.match(ln) for ln in lines)

    if marked_only and not has_markers:
        raise ValueError("marked-only mode: v data.txt ni nobene vrstice oblike <<...>>")

    sections: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    def flush():
        nonlocal current
        if current is None:
            return
        body = "\n".join(current["body_lines"]).strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        sections.append({
            "heading": current["heading"],
            "sid": current["sid"],
            "title": current["title"],
            "body": body,
        })
        current = None

    if has_markers:
        for ln in lines:
            m = MARKED_HEADING_RE.match(ln)
            if m:
                flush()
                heading = m.group(1).strip()
                sid, title = parse_sid_title(heading)
                current = {"heading": heading, "sid": sid, "title": title, "body_lines": []}
            else:
                if current is not None:
                    current["body_lines"].append(ln)
        flush()
        return sections

    # fallback headings
    if marked_only:
        return sections

    for ln in lines:
        m = PLAIN_HEADING_RE.match(ln)
        if m:
            sid = m.group(1).strip()
            title = m.group(2).strip()
            if not is_false_heading(title):
                flush()
                current = {"heading": f"{sid} {title}".strip(), "sid": sid, "title": title, "body_lines": []}
                continue
        if current is not None:
            current["body_lines"].append(ln)
    flush()
    return sections


def first_sentences(text: str, n: int = 2) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    if not t:
        return ""
    parts = re.split(r"(?<=[\.\!\?])\s+", t)
    parts = [p.strip() for p in parts if p.strip()]
    return " ".join(parts[:n])


def bullets(text: str) -> List[str]:
    out = []
    for ln in text.splitlines():
        if re.match(r"^\s*[–-]\s+\S", ln):
            out.append(re.sub(r"^\s*[–-]\s+", "", ln.strip()))
    return out


def make_generic_qa(section: Dict[str, str]) -> List[Dict[str, str]]:
    sid = section.get("sid", "")
    title = section.get("title", "") or section.get("heading", "")
    body = (section.get("body", "") or "").strip()
    if not body:
        return []

    chap = chapter_prefix(sid) or sid
    base = f"{sid} {title}".strip()

    qa: List[Dict[str, str]] = []

    bl = bullets(body)
    if len(bl) >= 3:
        qa.append({
            "q": f"[{base}] Naštej ključne točke in za vsako na kratko pojasni pomen.",
            "a": "\n".join(f"- {x}" for x in bl[:12]),
            "chap": chap,
            "srcSid": sid or chap
        })

    intro = first_sentences(body, 2)
    qa.append({
        "q": f"[{base}] Pojasni bistvo in utemelji z vsaj dvema dejstvoma iz besedila.",
        "a": intro if intro else (body[:350] + ("…" if len(body) > 350 else "")),
        "chap": chap,
        "srcSid": sid or chap
    })

    return qa


def load_rules(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("rules", [])


def rule_matches(rule: Dict[str, Any], section: Dict[str, str]) -> bool:
    match = rule.get("match", {})
    field = match.get("field", "title")
    hay = (section.get(field, "") or "").lower()

    contains_any = [s.lower() for s in match.get("contains_any", [])]
    if contains_any:
        return any(k in hay for k in contains_any)

    contains_all = [s.lower() for s in match.get("contains_all", [])]
    if contains_all:
        return all(k in hay for k in contains_all)

    regex_pat = match.get("regex")
    if regex_pat:
        return re.search(regex_pat, section.get(field, ""), flags=re.IGNORECASE) is not None

    # if no criteria provided, do not match
    return False


def apply_rules(rules: List[Dict[str, Any]], section: Dict[str, str]) -> List[Dict[str, str]]:
    sid = section.get("sid", "")
    chap = chapter_prefix(sid) or sid
    out: List[Dict[str, str]] = []

    for rule in rules:
        if not rule_matches(rule, section):
            continue
        for qa in rule.get("qa", []):
            q = qa.get("q", "").strip()
            a = qa.get("a", "").strip()
            if not q or not a:
                continue
            out.append({
                "q": q,
                "a": a,
                "chap": chap,
                "srcSid": sid or chap
            })
    return out


def js_escape_double(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def js_escape_tpl(s: str) -> str:
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def build_qa_js(qa: List[Dict[str, str]]) -> str:
    entries = []
    for it in qa:
        entries.append(
            '{ q:"' + js_escape_double(it["q"]) + '",\n'
            '      chap:"' + js_escape_double(it.get("chap", "")) + '",\n'
            '      srcSid:"' + js_escape_double(it.get("srcSid", "")) + '",\n'
            '      a:`' + js_escape_tpl(it["a"]) + '` }'
        )
    return "const qa = [\n  " + (",\n\n  ".join(entries)) + "\n];"


def ensure_chapter_select(html_text: str) -> str:
    if 'id="chap"' in html_text:
        return html_text

    needle = (
        '<div class="searchBox">\n'
        '      <label for="q">Iskalnik</label>\n'
        '      <input id="q" type="search" placeholder="Vpiši iskani pojem ..." autocomplete="off" />\n'
        '    </div>'
    )
    insert = (
        needle
        + '\n    <div class="searchBox">\n'
          '      <label for="chap">Poglavje</label>\n'
          '      <select id="chap">\n'
          '        <option value="">Vsa</option>\n'
          '      </select>\n'
          '    </div>'
    )
    return html_text.replace(needle, insert)


def harden_script(html_text: str) -> str:
    m = re.search(r"<script>(.*?)</script>", html_text, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return html_text
    script = m.group(1)

    # Ensure chapSel
    if "const chapSel" not in script:
        script = script.replace(
            'const input = document.getElementById("q");',
            'const input = document.getElementById("q");\n    const chapSel = document.getElementById("chap");'
        )

    # Ensure formatText
    script = re.sub(
        r"function\s+formatText\s*\(\s*text\s*\)\s*\{.*?\}",
        r'function formatText(text){ return escapeHtml(text).replace(/\n/g, "<br>"); }',
        script,
        flags=re.DOTALL
    )

    # Ensure highlight
    script = re.sub(
        r"function\s+highlight\s*\(\s*text\s*,\s*query\s*\)\s*\{.*?\}",
        r'''function highlight(text, query){
      if (!query) return escapeHtml(text);
      const q = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const re = new RegExp(q, "ig");
      return escapeHtml(text).replace(re, (m) => `<mark>${m}</mark>`);
    }''',
        script,
        flags=re.DOTALL
    )

    # Populate chapters helper (if missing)
    if "function populateChapters" not in script:
        helper = r'''
    function populateChapters(){
      if (!chapSel) return;
      const set = new Set();
      qa.forEach(it => { if (it.chap) set.add(it.chap); });
      const chapters = Array.from(set).sort((a,b) => {
        const pa = a.split('.').map(x => parseInt(x,10));
        const pb = b.split('.').map(x => parseInt(x,10));
        for (let i=0;i<Math.max(pa.length,pb.length);i++){
          const va = pa[i] ?? -1;
          const vb = pb[i] ?? -1;
          if (va !== vb) return va - vb;
        }
        return 0;
      });
      chapSel.innerHTML = '<option value="">Vsa</option>' +
        chapters.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    }
'''
        pos = script.find("function renderAll")
        script = (script[:pos] + helper + script[pos:]) if pos != -1 else (script + "\n" + helper)

    # Extend plain search to include chap/srcSid
    script = script.replace(
        'plain: (item.q + " " + item.a).toLowerCase()',
        'plain: (item.q + " " + item.a + " " + (item.chap||"") + " " + (item.srcSid||"")).toLowerCase()'
    )

    # Ensure chap in applyFilter
    if "const chap =" not in script:
        script = script.replace(
            "const query = input.value.trim().toLowerCase();",
            'const query = input.value.trim().toLowerCase();\n      const chap = (chapSel && chapSel.value) ? chapSel.value.trim() : "";'
        )

    script = script.replace("if (!query){", "if (!query && !chap){")

    if "if (!query && chap)" not in script:
        insert = r'''
      if (!query && chap){
        let visible = 0;
        cards.forEach((c, idx) => {
          const matchChap = (qa[idx].chap || "").startsWith(chap);
          c.el.style.display = matchChap ? "" : "none";
          if (matchChap){
            visible++;
            c.el.classList.remove("is-flipped");
            c.el.querySelector(".q").innerHTML = escapeHtml(qa[idx].q);
            c.el.querySelector(".a").innerHTML = formatText(qa[idx].a);
          }
        });
        updateCount(visible);
        return;
      }
'''
        script = script.replace("let visible = 0;", insert + "\n      let visible = 0;")

    script = script.replace(
        "const match = c.plain.includes(query);",
        'const matchQuery = c.plain.includes(query);\n        const matchChap = !chap || ((qa[idx].chap || "").startsWith(chap));\n        const match = matchQuery && matchChap;'
    )

    # Fix answer line
    script = re.sub(
        r'c\.el\.querySelector\("\.a"\)\.innerHTML\s*=\s*highlight\(qa\[idx\]\.a,\s*query\)\.replace\([^;]*\);',
        r'c.el.querySelector(".a").innerHTML = highlight(qa[idx].a, query).replace(/\n/g, "<br>");',
        script,
        flags=re.DOTALL
    )

    if "chapSel.addEventListener" not in script:
        script = script.replace(
            'input.addEventListener("input", applyFilter);',
            'input.addEventListener("input", applyFilter);\n    if (chapSel) chapSel.addEventListener("change", applyFilter);'
        )

    script = script.replace(
        'input.value = "";',
        'input.value = "";\n      if (chapSel) chapSel.value = "";'
    )

    if "populateChapters();" not in script:
        script = script.replace("renderAll();", "renderAll();\n    populateChapters();")

    new_html = html_text[:m.start(1)] + "\n" + script + "\n" + html_text[m.end(1):]
    return new_html


def add_chips_to_card(html_text: str) -> str:
    html_text = html_text.replace(
        '<span class="chip">Vprašanje ${index+1}</span>',
        '<span class="chip">Vprašanje ${index+1}</span>\n'
        '              <span class="chip" style="opacity:.85;">Poglavje ${escapeHtml(item.chap || "")}</span>'
    )
    html_text = html_text.replace(
        '<span class="chip">Odgovor</span>',
        '<span class="chip">Odgovor</span>\n'
        '              <span class="chip" style="opacity:.85;">Vir ${escapeHtml(item.srcSid || item.chap || "")}</span>'
    )
    return html_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True, help="structure_flipCard.html")
    ap.add_argument("--data", required=True, help="data.txt")
    ap.add_argument("--rules", required=True, help="rules.json")
    ap.add_argument("--out", required=True, help="output HTML, npr flipCard.html")

    ap.add_argument("--marked-only", "--no-fallback", dest="marked_only", action="store_true",
                    help="Uporabi samo <<...>> naslove (brez fallbacka).")
    ap.add_argument("--no-rules", action="store_true",
                    help="Ne uporabi rules.json (samo generična vprašanja).")

    args = ap.parse_args()

    tpl = Path(args.template).read_text(encoding="utf-8", errors="ignore")
    data = Path(args.data).read_text(encoding="utf-8", errors="ignore")

    sections = parse_sections(data, marked_only=args.marked_only)
    if not sections:
        raise SystemExit("Ni najdenih razdelkov. Preveri markerje <<...>> ali fallback.")

    rules = [] if args.no_rules else load_rules(Path(args.rules))

    qa_all: List[Dict[str, str]] = []
    for sec in sections:
        qa_all.extend(make_generic_qa(sec))
        if rules:
            qa_all.extend(apply_rules(rules, sec))

    # Dedupe by question text
    seen = set()
    qa = []
    for it in qa_all:
        if it["q"] in seen:
            continue
        seen.add(it["q"])
        qa.append(it)

    qa_js = build_qa_js(qa)

    out = re.sub(r"const\s+qa\s*=\s*\[\s*.*?\n\];", qa_js, tpl, flags=re.DOTALL)
    out = ensure_chapter_select(out)
    out = add_chips_to_card(out)
    out = harden_script(out)

    chapter_title = sections[0].get("heading", "Flip kartice")
    out = re.sub(r"<h1>.*?</h1>", f"<h1>{html.escape(chapter_title)} — Flip kartice + iskalnik</h1>", out, count=1, flags=re.DOTALL)
    out = re.sub(r"<title>.*?</title>", f"<title>Flip Cards + Iskalnik — {html.escape(chapter_title)}</title>", out, flags=re.DOTALL)

    Path(args.out).write_text(out, encoding="utf-8")
    print(f"OK: wrote {args.out} ({len(qa)} vprašanj)")


if __name__ == "__main__":
    main()
