# meeting_graph.py

from flask import Blueprint, request, jsonify
import json
from bs4 import BeautifulSoup
import traceback
from datetime import datetime
import os
import re
import uuid 

meeting_graph_bp = Blueprint("meeting_graph", __name__, url_prefix="/graph")

driver = None


def init_driver(d):
    global driver
    driver = d


def _ensure_driver():
    if driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_driver(driver) on startup.")


def clean_text(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_heading(value: str) -> str:
    """
    Removes emojis and normalizes headings from English and Slovenian templates.
    """
    if not value:
        return ""

    v = clean_text(value)

    # remove emoji and pictographs using the same ranges as sanitizer
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )

    v = emoji_pattern.sub("", v)

    # normalize whitespace and lower-case for comparisons
    return clean_text(v).lower()


def sanitize_node_name(value: str) -> str:
    """
    Remove emoji and stray symbols from node names/titles so they are
    suitable for graph node naming and display.
    """
    if not value:
        return ""

    # normalize whitespace first
    v = clean_text(value)

    # common emoji / pictograph ranges
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs (e.g., 🧩)
        "\U0001FA70-\U0001FAFF"  # additional emoji (symbols)
        "\U00002600-\U000026FF"  # miscellaneous symbols
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002700-\U000027BF"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )

    v = emoji_pattern.sub("", v)

    # remove remaining non-word punctuation but keep spaces, dots, dashes and underscores
    v = re.sub(r"[^\w\s\.\-_]", "", v, flags=re.UNICODE)

    return clean_text(v)


def parse_date(value: str):
    """
    Accepts simple dates like:
    01.10.2023
    01/10/2023
    2023-10-01

    Returns ISO date string or None.
    """
    value = clean_text(value)

    if not value:
        return None

    formats = [
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d.%m.%y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass

    return None


def get_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        return clean_text(h1.get_text(" "))

    title = soup.find("title")
    if title:
        return clean_text(title.get_text(" "))

    return "Meeting summary"


def get_graph_node_name(soup: BeautifulSoup) -> str | None:
    """Extract graph node name from HTML meta or data attributes.

    Looks for (in order):
    - <meta name="graphNodeName" content="...">
    - <body data-graph-node-name="...">
    - any element with data-graph-node-name attribute
    Returns None when not found.
    """
    if not soup:
        return None

    meta = soup.find("meta", attrs={"name": "graphNodeName"})
    if meta:
        val = clean_text(meta.get("content", ""))
        if val:
            return val

    body = soup.find("body")
    if body:
        val = clean_text(body.get("data-graph-node-name", ""))
        if val:
            return val

    any_node = soup.find(attrs={"data-graph-node-name": True})
    if any_node:
        val = clean_text(any_node.get("data-graph-node-name", ""))
        if val:
            return val

    return None


def get_language(soup: BeautifulSoup) -> str:
    html = soup.find("html")
    if html and html.get("lang"):
        return html.get("lang")
    return "unknown"


def get_sections(soup: BeautifulSoup) -> dict:
    """
    Returns a dictionary:
    {
      "attendees": <section>,
      "agenda": <section>,
      "notes": <section>,
      "tasks": <section>,
      ...
    }
    """
    sections = {}

    for section in soup.find_all("section"):
        h2 = section.find("h2")
        if not h2:
            continue

        heading = normalize_heading(h2.get_text(" "))

        if heading in ["date & time", "datum in čas"]:
            sections["date_time"] = section
        elif heading in ["attendees", "udeleženci"]:
            sections["attendees"] = section
        elif heading in ["agenda", "dnevni red"]:
            sections["agenda"] = section
        elif heading in ["notes", "zapiski"]:
            sections["notes"] = section
        elif heading in ["action items", "naloge"]:
            sections["tasks"] = section

    return sections


def parse_attendees(section) -> list[dict]:
    attendees = []

    if not section:
        return attendees

    table = section.find("table")
    if not table:
        return attendees

    rows = table.find_all("tr")

    for row in rows[1:]:
        cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]

        if len(cells) >= 1 and cells[0]:
            attendees.append({
                "name": cells[0],
                "department": cells[1] if len(cells) > 1 else None
            })

    return attendees


def parse_agenda(section) -> list[str]:
    if not section:
        return []

    items = []

    for li in section.find_all("li"):
        text = clean_text(li.get_text(" "))
        if text:
            items.append(text)

    return items


def parse_notes(section) -> str:
    if not section:
        return ""

    content = section.find("div", class_="content") or section
    return clean_text(content.get_text(" "))


def parse_task_details(section) -> dict:
    """
    Parses:
      <p><b>Prepare report</b></p>
      <p>Test</p>

    Returns:
      {"Prepare report": "Test"}
    """
    details = {}

    if not section:
        return details

    details_div = section.find(id="MeetingMinutesTasks") or section.find(id="ZapisnikNaloge")
    if not details_div:
        return details

    current_task = None

    for p in details_div.find_all("p"):
        bold = p.find("b")

        if bold:
            current_task = clean_text(bold.get_text(" "))
            if current_task:
                details[current_task] = ""
        else:
            if current_task:
                text = clean_text(p.get_text(" "))
                if text:
                    if details[current_task]:
                        details[current_task] += "\n" + text
                    else:
                        details[current_task] = text

    return details


def parse_tasks(section) -> list[dict]:
    tasks = []

    if not section:
        return tasks

    details = parse_task_details(section)

    table = section.find("table")
    if not table:
        return tasks

    rows = table.find_all("tr")

    # try to detect header indexes so we correctly pick the finished/status columns
    status_idx = None
    finished_idx = None
    header_cells = []
    if rows:
        header = rows[0]
        header_cells = [clean_text(td.get_text(" ")) for td in header.find_all(["td", "th"])]
        for i, h in enumerate(header_cells):
            if not h:
                continue
            lh = h.lower()
            if "status" in lh:
                status_idx = i
            if "finished" in lh or "Zaključeno" in lh or "done" in lh or "completed" in lh:
                finished_idx = i
        # don't stop early; prefer header-detected indexes over positional defaults

    for row in rows[1:]:
        cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]

        if len(cells) < 1 or not cells[0]:
            continue

        title = cells[0]

        # determine finished and status values using detected header indexes when available
        if finished_idx is not None:
            finished_raw = cells[finished_idx] if len(cells) > finished_idx else None
        else:
            finished_raw = cells[4] if len(cells) > 4 else None

        if status_idx is not None:
            status_val = cells[status_idx] if len(cells) > status_idx else None
        else:
            status_val = cells[5] if len(cells) > 5 else None

        # debug log extracted cells when finished/status are missing or unexpected
        if finished_raw is None or status_val is None:
            print("parse_tasks: header:", header_cells, "row:", cells, "finished_raw:", finished_raw, "status:", status_val, flush=True)

        task = {
            "title": title,
            "owner": cells[1] if len(cells) > 1 else None,
            "description": cells[2] if len(cells) > 2 else None,
            "assignedDate": parse_date(cells[3]) if len(cells) > 3 else None,
            "dueDate": parse_date(cells[4]) if len(cells) > 4 else None,                        
            "finishedDate": parse_date(cells[5]) if len(cells) > 5 else None,            
            # parse finished as date when present
            "finished": parse_date(finished_raw) if finished_raw else None,
            # status is textual
            "status": status_val,
        }

        tasks.append(task)

    return tasks


def build_chunks(meeting_title, sections) -> list[dict]:
    chunks = []

    for key, section in sections.items():
        if not section:
            continue

        text = clean_text(section.get_text(" "))
        if text:
            chunks.append({
                "id": str(uuid.uuid4()),
                "section": key,
                "text": text,
                "title": f"{meeting_title} - {key}"
            })

    return chunks


def parse_meeting_html(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    
    title = get_title(soup)
    graph_node_name = get_graph_node_name(soup) or title
    language = get_language(soup)
    sections = get_sections(soup)

    attendees = parse_attendees(sections.get("attendees"))
    agenda = parse_agenda(sections.get("agenda"))
    notes = parse_notes(sections.get("notes"))
    tasks = parse_tasks(sections.get("tasks"))
    chunks = build_chunks(graph_node_name, sections)

    # graphNodeName may be provided via meta or data attributes in the template
    graph_node_name = get_graph_node_name(soup) or title

    return {
        "meetingId": str(uuid.uuid4()),
        "documentId": str(uuid.uuid4()),
        "title": title,
        "graphNodeName": graph_node_name,
        "language": language,
        "attendees": attendees,
        "agenda": agenda,
        "notes": notes,
        "tasks": tasks,
        "chunks": chunks
    }


def parse_document_html(html: str) -> dict:
    """
    Parse the documentsTemplate.html structure into the parsed dict expected by
    write_document_graph. Extracts title, language, summary, chunks, relatedObjects,
    sources and changes. Returns empty attendees/agenda/notes/tasks to keep shape.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = get_title(soup)
    language = get_language(soup)

    # short summary from header paragraph (if present)
    summary = ""
    header = soup.find("header")
    if header:
        p = header.find("p")
        if p:
            summary = clean_text(p.get_text(" "))

    # collect sections mapping by normalized heading
    sections = {}
    for section in soup.find_all("section"):
        h2 = section.find("h2")
        if not h2:
            continue
        heading = normalize_heading(h2.get_text(" "))

        if "namen" in heading or "purpose" in heading:
            sections["purpose"] = section
        elif "obseg" in heading or "scope" in heading:
            sections["scope"] = section
        elif "opis" in heading:
            sections["solution"] = section
        elif "delovanje" in heading or "operation" in heading:
            sections["operation"] = section
        elif "pravila" in heading or "omejit" in heading:
            sections["rules"] = section
        elif "povezani" in heading or "sistemi" in heading or "objekt" in heading:
            sections["related_objects"] = section
        elif "viri" in heading or "povezav" in heading or "links" in heading:
            sections["sources"] = section
        elif "zgodovina" in heading or "sprememb" in heading or "history" in heading:
            sections["changes"] = section
        else:
            sections[heading] = section

    # parse related objects table
    related_objects = []
    rel_sec = sections.get("related_objects")
    if rel_sec:
        table = rel_sec.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]
                if not cells or not any(cells):
                    continue
                related_objects.append({
                    "type": cells[0] if len(cells) > 0 else None,
                    "name": cells[1] if len(cells) > 1 else None,
                    "description": cells[2] if len(cells) > 2 else None
                })

    # parse sources list
    # sources = []
    # src_sec = sections.get("sources")
    # if src_sec:
    #     for li in src_sec.find_all("li"):
    #         text = clean_text(li.get_text(" "))
    #         if text:
    #             sources.append(text)

    sources = []
    src_sec = sections.get("sources")
    if src_sec:
        for li in src_sec.find_all("li"):
            text = clean_text(li.get_text(" "))
            link = li.find("a")

            if text:
                sources.append({
                    "reference": text,
                    "title": text,
                    "url": link.get("href") if link else None,
                    "type": "reference"
                })    

    # parse changes table
    changes = []
    chg_sec = sections.get("changes")
    if chg_sec:
        table = chg_sec.find("table")
        if table:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]
                if not cells or not any(cells):
                    continue
                changes.append({
                    "date": parse_date(cells[0]) if len(cells) > 0 else None,
                    "author": cells[1] if len(cells) > 1 else None,
                    "change": cells[2] if len(cells) > 2 else None
                })

    # build chunks from the sections we care about (preserve readable titles)
    chunks = []
    for key, section in sections.items():
        if not section:
            continue
        text = clean_text(section.get_text(" "))
        if not text:
            continue
        h2 = section.find("h2")
        section_title = clean_text(h2.get_text(" ")) if h2 else key
        chunks.append({
            "id": str(uuid.uuid4()),
            "section": key,
            "text": text,
            "title": f"{title} - {section_title}"
        })

    # ensure stable ids
    documentation_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())

    # graph node name from template (meta or data-attribute), fall back to title
    graph_node_name = get_graph_node_name(soup) or title

    return {
        "documentationId": documentation_id,
        "documentId": document_id,
        "title": title,
        "graphNodeName": graph_node_name,
        "language": language,
        "summary": summary,
        "chunks": chunks,
        "relatedObjects": related_objects,
        "sources": sources,
        "changes": changes,
        "attendees": [],
        "agenda": [],
        "notes": "",
        "tasks": []
    }


def parse_service_request_html(html: str) -> dict:
    """Extract service request fields and tasks from CKEditor's HTML fragment."""
    soup = BeautifulSoup(html, "html.parser")
    title = get_title(soup)
    sections = {}
    headings = {
        "description": "description",
        "definition of problem": "problem",
        "proposed solution": "solution",
        "notes": "notes",
        "tasks": "tasks",
    }
    for section in soup.find_all("section"):
        heading = section.find("h2")
        if heading:
            key = headings.get(normalize_heading(heading.get_text(" ")))
            if key:
                sections[key] = section

    def section_text(key):
        section = sections.get(key)
        if not section:
            return ""
        heading = section.find("h2")
        content = section.find("div", class_="content") or section
        if content is section and heading:
            return clean_text(" ".join(content.stripped_strings).removeprefix(clean_text(heading.get_text(" "))))
        return clean_text(content.get_text(" "))

    tasks = parse_tasks(sections.get("tasks"))
    return {
        "serviceRequestId": str(uuid.uuid4()),
        "documentId": str(uuid.uuid4()),
        "title": title,
        "graphNodeName": get_graph_node_name(soup) or title,
        "language": get_language(soup),
        "description": section_text("description"),
        "problem": section_text("problem"),
        "solution": section_text("solution"),
        "notes": section_text("notes"),
        "tasks": tasks,
        "chunks": build_chunks(title, sections),
    }


def parse_task_html(html: str) -> dict:
    """Parse the standalone task template into graph-writer fields."""
    soup = BeautifulSoup(html, "html.parser")

    # CKEditor may submit either the complete template or only its body. In
    # the latter case the task name is usually an h2 inside the header.
    header = soup.find("header")
    heading = header.find(["h1", "h2"]) if header else soup.find(["h1", "h2"])
    raw_title = clean_text(heading.get_text(" ")) if heading else get_title(soup)
    title = re.sub(r"^(?:naloga|task)\s*:\s*", "", raw_title, flags=re.IGNORECASE).strip()
    title = title or raw_title or "Task"

    summary = ""
    if header:
        summary_node = header.find("p")
        if summary_node:
            summary = clean_text(summary_node.get_text(" "))

    section_names = {
        "osnovni podatki": "basic_info",
        "basic information": "basic_info",
        "cilj naloge": "goal",
        "task goal": "goal",
        "podroben opis": "description",
        "detailed description": "description",
        "koraki izvedbe": "steps",
        "execution steps": "steps",
        "kriteriji zaključka": "completion_criteria",
        "completion criteria": "completion_criteria",
        "povezave in odvisnosti": "dependencies",
        "links and dependencies": "dependencies",
        "opombe in potek dela": "notes",
        "notes and workflow": "notes",
    }
    sections = {}
    for section in soup.find_all("section"):
        section_heading = section.find("h2")
        if not section_heading:
            continue
        heading_text = clean_text(section_heading.get_text(" "))
        section_key = section_names.get(normalize_heading(heading_text))
        if section_key:
            sections[section_key] = (section, heading_text)

    # Read the label/value table without relying on row positions.
    basic_fields = {}
    basic_section = sections.get("basic_info")
    if basic_section:
        table = basic_section[0].find("table")
        if table:
            field_names = {
                "status": "status",
                "owner": "owner",
                "assignee": "owner",
                "odgovorna oseba": "owner",
                "assigned to": "owner",
                "created by": "createdBy",
                "ustvaril": "createdBy",
                "datum dodelitve": "assignedDate",
                "assigned date": "assignedDate",
                "rok dokončanja": "dueDate",
                "due date": "dueDate",
                "datum zaključka": "finishedDate",
                "finished date": "finishedDate",
                "prioriteta": "priority",
                "priority": "priority",
                "finished": "finished",
            }
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"], recursive=False)
                if len(cells) < 2:
                    continue
                label = normalize_heading(cells[0].get_text(" "))
                field = field_names.get(label)
                if field:
                    basic_fields[field] = clean_text(cells[1].get_text(" "))

    def section_text(key: str) -> str:
        section_info = sections.get(key)
        if not section_info:
            return ""
        section, heading_text = section_info
        # stripped_strings preserves table/list contents while excluding the
        # section heading itself.
        parts = [
            text for text in section.stripped_strings
            if clean_text(text) != clean_text(heading_text)
        ]
        return clean_text(" ".join(parts))

    goal = section_text("goal")
    description = section_text("description")
    steps = []
    if "steps" in sections:
        steps = [
            clean_text(item.get_text(" "))
            for item in sections["steps"][0].find_all("li")
            if clean_text(item.get_text(" "))
        ]
    completion_criteria = []
    if "completion_criteria" in sections:
        completion_criteria = [
            clean_text(item.get_text(" "))
            for item in sections["completion_criteria"][0].find_all("li")
            if clean_text(item.get_text(" "))
        ]

    related_objects = []
    dependencies_section = sections.get("dependencies")
    if dependencies_section:
        table = dependencies_section[0].find("table")
        if table:
            for row in table.find_all("tr")[1:]:
                cells = [clean_text(cell.get_text(" ")) for cell in row.find_all(["td", "th"])]
                if any(cells):
                    related_objects.append({
                        "type": cells[0] if len(cells) > 0 else None,
                        "name": cells[1] if len(cells) > 1 else None,
                        "description": cells[2] if len(cells) > 2 else None,
                    })

    notes = section_text("notes")
    finished = parse_date(basic_fields.get("finished", ""))
    finished_date = parse_date(basic_fields.get("finishedDate", ""))
    task_description_parts = [
        part for part in (
            summary,
            f"Goal: {goal}" if goal else "",
            description,
            "Steps: " + "; ".join(steps) if steps else "",
            "Completion criteria: " + "; ".join(completion_criteria)
            if completion_criteria else "",
            "Dependencies: " + "; ".join(
                ": ".join(filter(None, (item.get("type"), item.get("name"), item.get("description"))))
                for item in related_objects
            ) if related_objects else "",
            notes,
        ) if part
    ]
    task_record = {
        "title": title,
        "owner": basic_fields.get("owner") or None,
        "description": "\n".join(task_description_parts),
        "assignedDate": parse_date(basic_fields.get("assignedDate", "")),
        "dueDate": parse_date(basic_fields.get("dueDate", "")),
        "finishedDate": finished_date,
        "finished": finished,
        "status": basic_fields.get("status") or "OPEN",
        "priority": basic_fields.get("priority") or None,
        "createdBy": basic_fields.get("createdBy") or None,
    }

    chunks = []
    for key, (section, heading_text) in sections.items():
        text = section_text(key)
        if text:
            chunks.append({
                "id": str(uuid.uuid4()),
                "section": key,
                "text": text,
                "title": f"{title} - {heading_text}",
            })

    return {
        "documentId": str(uuid.uuid4()),
        "title": title,
        "graphNodeName": get_graph_node_name(soup) or title,
        "language": get_language(soup),
        "summary": summary,
        "status": task_record["status"],
        "owner": task_record["owner"],
        "createdBy": task_record["createdBy"],
        "assignedDate": task_record["assignedDate"],
        "dueDate": task_record["dueDate"],
        "finishedDate": finished_date,
        "finished": finished,
        "priority": task_record["priority"],
        "goal": goal,
        "description": description,
        "steps": steps,
        "completionCriteria": completion_criteria,
        "relatedObjects": related_objects,
        "notes": notes,
        "attendees": [],
        "agenda": [],
        "tasks": [task_record],
        "chunks": chunks,
    }


def extract_template_type_from_html(html: str) -> str | None:
    """
    Fallback source for template type when it is not provided in request JSON.

    Supported markers inside HTML:
    - <meta name="templateType" content="...">
    - <body data-template-type="...">
    - Any element with data-template-type="..."
    """
    if not html or not html.strip():
        return None

    soup = BeautifulSoup(html, "html.parser")

    meta = soup.find("meta", attrs={"name": "templateType"})
    if meta:
        value = clean_text(meta.get("content", ""))
        if value:
            return value

    body = soup.find("body")
    if body:
        value = clean_text(body.get("data-template-type", ""))
        if value:
            return value

    any_node = soup.find(attrs={"data-template-type": True})
    if any_node:
        value = clean_text(any_node.get("data-template-type", ""))
        if value:
            return value

    return None

def write_document_graph(
    tx,
    project_name: str,
    html: str,
    parsed: dict,
    node_id: str = None,
    template_type: str = "CKEDITOR_DOCUMENTATION"
):
    node_name = parsed.get("graphNodeName") or parsed.get("title")
    if not node_name:
        raise ValueError("Documentation requires a graphNodeName or title")

    title = parsed.get("title") or node_name
    documentation_name = f"{project_name}.Documentation.{node_name}"
    document_name = f"{project_name}.Document.{node_name}"




    # Documentation and complete editable HTML.
    record = tx.run("""
        MERGE (d:Documentation {name: $documentationName})
        ON CREATE SET d.createdAt = datetime()
        SET d.id_rc = coalesce(d.id_rc, randomUUID()),
            d.title = $title,
            d.summary = $summary,
            d.language = $language,
            d.projectName = $projectName,
            d.updatedAt = datetime()

        MERGE (doc:DocumentHTML {name: $documentName})
        ON CREATE SET doc.createdAt = datetime()
        SET doc.id_rc = coalesce(doc.id_rc, randomUUID()),
            doc.title = $title,
            doc.html = $html,
            doc.language = $language,
            doc.projectName = $projectName,
            doc.sourceType = $templateType,
            doc.updatedAt = datetime()

        MERGE (d)-[:DOCUMENTED_BY]->(doc)

        RETURN d.id_rc AS documentationId,
            doc.id_rc AS documentId
    """, {
        "documentationName": documentation_name,
        "documentName": document_name,
        "projectName": project_name,
        "title": title,
        "summary": parsed.get("summary"),
        "language": parsed.get("language") or "sl",
        "html": html,
        "templateType": template_type
    }).single()

    documentation_id = record["documentationId"]
    parsed["documentationId"] = documentation_id
    parsed["documentId"] = record["documentId"]

    # The current parser calls these "chunks", but each entry
    # represents a complete document section.
    seen_sections = set()

    for position, section in enumerate(parsed.get("chunks", [])):
        section_key = section.get("section")
        if not section_key:
            raise ValueError("Each section requires a stable section key")

        if section_key in seen_sections:
            raise ValueError(f"Duplicate section key: {section_key}")
        seen_sections.add(section_key)

        section_title = section.get("title") or f"{title} - {section_key}"
        section_text = section.get("text") or ""

        # Names depend on stable identity, not the displayed heading.
        section_name = f"{documentation_id}.Section.{section_key}"
        chunk_name = f"{section_name}.Chunk.0"

        record = tx.run("""
            MATCH (d:Documentation {id_rc: $documentationId})

            MERGE (s:Section {name: $sectionName})
            ON CREATE SET s.createdAt = datetime()
            SET s.id_rc = coalesce(s.id_rc, randomUUID()),
                s.documentationId = $documentationId,
                s.sectionKey = $sectionKey,
                s.title = $title,
                s.text = $text,
                s.position = $position,
                s.projectName = $projectName,
                s.updatedAt = datetime()

            MERGE (d)-[:HAS_SECTION]->(s)

            // Initially, one retrieval chunk per section.
            MERGE (c:Chunk {name: $chunkName})
            ON CREATE SET c.createdAt = datetime()

            // A vector must correspond to the current chunk text.
            // Keep it when text is unchanged; invalidate it otherwise.
            FOREACH (
                ignored IN CASE
                    WHEN c.text IS NULL OR c.text <> $text
                    THEN [1]
                    ELSE []
                END |
                REMOVE c.embedding,
                    c.embeddingModel,
                    c.embeddedAt
            )

            SET c.id_rc = coalesce(c.id_rc, randomUUID()),
                c.documentationId = $documentationId,
                c.sectionId = s.id_rc,
                c.section = $sectionKey,
                c.title = $title,
                c.text = $text,
                c.position = 0,
                c.projectName = $projectName,
                c.updatedAt = datetime()

            MERGE (s)-[:HAS_CHUNK]->(c)

            RETURN s.id_rc AS sectionId,
                c.id_rc AS chunkId
        """, {
            "documentationId": documentation_id,
            "sectionName": section_name,
            "chunkName": chunk_name,
            "sectionKey": section_key,
            "title": section_title,
            "text": section_text,
            "position": position,
            "projectName": project_name
        }).single()

        section["sectionId"] = record["sectionId"]
        section["id"] = record["chunkId"]

    # Related systems and objects.
    for related_object in parsed.get("relatedObjects", []):
        object_name = related_object.get("name")
        if not object_name:
            continue

        tx.run("""
            MATCH (d:Documentation {id_rc: $documentationId})

            MERGE (o:RelatedObject {
                projectName: $projectName,
                objectType: $objectType,
                name: $objectName
            })
            ON CREATE SET o.createdAt = datetime()
            SET o.id_rc = coalesce(o.id_rc, randomUUID()),
                o.description = $description,
                o.updatedAt = datetime()

            MERGE (d)-[:DOCUMENTS_OBJECT]->(o)
        """, {
            "documentationId": documentation_id,
            "projectName": project_name,
            "objectType": related_object.get("type") or "unknown",
            "objectName": object_name,
            "description": related_object.get("description")
        }).consume()

    # Sources and references.
    for source in parsed.get("sources", []):
        reference = (
            source.get("reference")
            or source.get("url")
            or source.get("title")
        )
        if not reference:
            continue

        tx.run("""
            MATCH (d:Documentation {id_rc: $documentationId})

            MERGE (s:Source {
                projectName: $projectName,
                reference: $reference
            })
            ON CREATE SET s.createdAt = datetime()
            SET s.id_rc = coalesce(s.id_rc, randomUUID()),
                s.title = $title,
                s.url = $url,
                s.sourceType = $sourceType,
                s.updatedAt = datetime()

            MERGE (d)-[:REFERENCES]->(s)
        """, {
            "documentationId": documentation_id,
            "projectName": project_name,
            "reference": reference,
            "title": source.get("title"),
            "url": source.get("url"),
            "sourceType": source.get("type") or "reference"
        }).consume()

    # Change history: reuse identical entries.


        
    for change in parsed.get("changes", []):
        change_date = change.get("date") or ""
        author = change.get("author") or ""
        description = (
            change.get("change")
            or change.get("description")
            or ""
        )

        if not any((change_date, author, description)):
            continue

        changeName = (
            f"{project_name}.DocumentChange."
            f"{documentation_id}.{change_date}.{author}.{description}"
        )

        print("***** Document Change Start *****")
        print(changeName)
        print("***** Document Change End *****")

        tx.run("""
            MATCH (d:Documentation {id_rc: $documentationId})

            MERGE (ch:DocumentChange {
                documentationId: $documentationId,
                changeDate: $changeDate,
                author: $author,
                description: $description
            })
            ON CREATE SET
                ch.id_rc = randomUUID(),
                ch.createdAt = datetime(),
                ch.name = $changeName
            SET ch.projectName = $projectName,
                ch.name = $changeName

            MERGE (d)-[:HAS_CHANGE]->(ch)

            WITH ch
            WHERE $author <> ''

            MERGE (p:Person {name: $author})
            ON CREATE SET p.projectName = $projectName
            SET p.id_rc = coalesce(p.id_rc, randomUUID())

            MERGE (ch)-[:CHANGED_BY]->(p)
        """, {
            "documentationId": documentation_id,
            "changeDate": change_date,
            "author": author,
            "description": description,
            "projectName": project_name,
            "changeName": changeName
        }).consume()

    # Optional parent link.
    if node_id:
        tx.run("""
            MATCH (parent {id_rc: $nodeId})
            MATCH (d:Documentation {id_rc: $documentationId})
            MERGE (parent)-[:HAS_DOCUMENTATION]->(d)
        """, {
            "nodeId": node_id,
            "documentationId": documentation_id
        }).consume()

def write_meeting_graph(
    tx,
    project_name: str,
    html: str,
    parsed: dict,
    node_id: str = None,
    template_type: str = "CKEDITOR_MEETING"
):

    # If the MERGE matched an existing node by name, fetch its id_rc and
    # update parsed['meetingId'] so subsequent MATCH/params use the stored id.
    node_name_for_lookup = parsed.get("graphNodeName") or parsed.get("title")
    full_meeting_name = project_name + ".MeetingSummary." + (node_name_for_lookup or "")
    rec = tx.run(
        """
        MATCH (m:MeetingSummary)
        WHERE m.name = $fullName
        RETURN m.id_rc AS id_rc
        """,
        {"fullName": full_meeting_name}
    ).single()

    if rec and rec.get("id_rc"):
        parsed["meetingId"] = rec.get("id_rc")
    else:
        tx.run("""
            MERGE (m:MeetingSummary {
                name: $projectName + '.MeetingSummary.' + $nodeName
            })
            ON CREATE SET
                m.id_rc = $meetingId,
                m.createdAt = datetime()
            SET m.title = $title,
                m.language = $language,
                m.projectName = $projectName

            MERGE (doc:DocumentHTML {id_rc: $documentId})
            SET doc.name = $meetingId +'.Document.' + $nodeName,
                doc.title = $title,
                doc.html = $html,
                doc.language = $language,
                doc.projectName = $projectName,
                doc.sourceType = $templateType,
                doc.createdAt = datetime()

            MERGE (m)-[:DOCUMENTED_BY]->(doc)
        """, {
            "projectName": project_name,
                "meetingId": parsed["meetingId"],
                "documentId": parsed["documentId"],
                "title": parsed["title"],
                "nodeName": parsed.get("graphNodeName") or parsed.get("title"),
                "language": parsed["language"],
                "html": html,
                "templateType": template_type
        })

    for attendee in parsed["attendees"]:
        print("******************************")
        print(f"Attendee: {attendee}")
        
        print("******************************")
        tx.run("""
            MATCH (m:MeetingSummary {id_rc: $meetingId})

            MERGE (person:Person {name: $personName})
            SET person.id_rc = coalesce(person.id_rc, randomUUID()),
                person.projectName = $projectName

            MERGE (m)-[:HAS_ATTENDEE]->(person)

            WITH person
            WHERE $departmentName IS NOT NULL AND $departmentName <> ''

            MERGE (dept:Department {name: $departmentName})
            SET dept.projectName = $projectName

            MERGE (person)-[:BELONGS_TO]->(dept)
        """, {
            "meetingId": parsed["meetingId"],
            "personName": attendee["name"],
            "departmentName": attendee.get("department"),
            "projectName": project_name
        })

    for agenda_item in parsed["agenda"]:
        tx.run("""
            MATCH (m:MeetingSummary {id_rc: $meetingId})

            MERGE (a:AgendaItem {
                meetingId: $meetingId,
                title: $title
            })
            SET a.id_rc = coalesce(a.id_rc, randomUUID()),
                a.name = $meetingId + '.AgendaItem.' + $title,
                a.projectName = $projectName

            MERGE (m)-[:HAS_AGENDA_ITEM]->(a)
        """, {
            "meetingId": parsed["meetingId"],
            "title": agenda_item,
            "projectName": project_name
        })

    if parsed["notes"]:
        tx.run("""
            MATCH (m:MeetingSummary {id_rc: $meetingId})

            MERGE (n:MeetingNote {meetingId: $meetingId})
            SET n.id_rc = coalesce(n.id_rc, randomUUID()),
                n.name = $meetingId + '.MeetingNote.' + $meetingId,
                n.text = $notes,
                n.projectName = $projectName

            MERGE (m)-[:HAS_NOTE]->(n)
        """, {
            "meetingId": parsed["meetingId"],
            "notes": parsed["notes"],
            "projectName": project_name
        })

    print("srevice request processing" + str(parsed["tasks"]))
    for task in parsed["tasks"]:
        task_id = str(uuid.uuid4())

        tx.run("""
            MATCH (m:MeetingSummary {id_rc: $meetingId})

            MERGE (t:ServiceRequest {name: $meetingId +'.ServiceRequest.' + $title})
            SET t.id_rc = coalesce(t.id_rc, randomUUID()),
                t.name = $meetingId +'.Task.' + $title,
                t.title = $title,
                t.description = $description,
                t.assignedDate = CASE
                    WHEN $assignedDate IS NULL THEN NULL
                    ELSE date($assignedDate)
                END,
                t.dueDate = CASE
                    WHEN $dueDate IS NULL THEN NULL
                    ELSE date($dueDate)
                END,
                t.finishedDate = CASE
                    WHEN $finishedDate IS NULL THEN NULL
                    ELSE date($finishedDate)
                END,
                t.status = $status,
                t.finished = $finished,
                t.source = 'meeting',
                t.projectName = $projectName,
                t.createdAt = datetime()

            MERGE (m)-[:CREATED_SR]->(t)

            WITH t
            WHERE $ownerName IS NOT NULL AND $ownerName <> ''

            MERGE (person:Person {name: $ownerName})
            SET person.id_rc = coalesce(person.id_rc, randomUUID()),
                person.projectName = $projectName

            MERGE (t)-[:ASSIGNED_TO]->(person)
        """, {
            "meetingId": parsed["meetingId"],
            "taskId": task_id,
            "title": task["title"],
            "description": task.get("description"),
            "assignedDate": task.get("assignedDate"),
            "dueDate": task.get("dueDate"),
            "finishedDate": task.get("finishedDate"),
            "finished": task.get("finished"),
            "status": task.get("status", "OPEN"),
            "ownerName": task.get("owner"),
            "projectName": project_name
        })

    for chunk in parsed["chunks"]:
        tx.run("""
            MATCH (doc:DocumentHTML {id_rc: $documentId})

            MERGE (c:Chunk {id_rc: $chunkId})
            SET c.name = $meetingId + '.Chunk.' + $title,
                c.title = $title,
                c.section = $section,
                c.text = $text,
                c.projectName = $projectName,
                c.createdAt = datetime()

            MERGE (doc)-[:HAS_CHUNK]->(c)
        """, {
            "meetingId": parsed["meetingId"],
            "documentId": parsed["documentId"],
            "chunkId": chunk["id"],
            "title": chunk["title"],
            "section": chunk["section"],
            "text": chunk["text"],
            "projectName": project_name
        })

    if node_id:
        tx.run("""
            MATCH (parent {id_rc: $nodeId})
            MATCH (m:MeetingSummary {id_rc: $meetingId})
            MERGE (parent)-[:HAS_MEETING]->(m)
        """, {
            "nodeId": node_id,
            "meetingId": parsed["meetingId"]
        })


def write_service_request_graph(
    tx,
    project_name: str,
    html: str,
    parsed: dict,
    node_id: str = None,
    template_type: str = "CKEDITOR_SERVICE_REQUEST"
):
    """Persist a request, its document, searchable sections and assigned tasks."""
    name = f"{project_name}.ServiceRequest.{parsed['graphNodeName']}"
    doc_name = f"{name}.Document"
    record = tx.run("""
        MERGE (sr:ServiceRequest {name: $name})
        ON CREATE SET sr.id_rc = randomUUID(), sr.createdAt = datetime()
        SET sr.title = $title, sr.description = $description,
            sr.problem = $problem, sr.proposedSolution = $solution,
            sr.notes = $notes, sr.language = $language,
            sr.projectName = $projectName, sr.updatedAt = datetime()
        MERGE (doc:DocumentHTML {name: $docName})
        ON CREATE SET doc.id_rc = randomUUID(), doc.createdAt = datetime()
        SET doc.title = $title, doc.html = $html,
            doc.language = $language, doc.projectName = $projectName,
            doc.sourceType = $templateType, doc.updatedAt = datetime()
        MERGE (sr)-[:DOCUMENTED_BY]->(doc)
        RETURN sr.id_rc AS serviceRequestId, doc.id_rc AS documentId
    """, {
        "name": name, "docName": doc_name, "title": parsed["title"],
        "description": parsed["description"], "problem": parsed["problem"],
        "solution": parsed["solution"], "notes": parsed["notes"],
        "language": parsed["language"], "projectName": project_name,
        "html": html, "templateType": template_type,
    }).single()
    parsed["serviceRequestId"] = record["serviceRequestId"]
    parsed["documentId"] = record["documentId"]

    for chunk in parsed["chunks"]:
        tx.run("""
            MATCH (doc:DocumentHTML {id_rc: $documentId})
            MERGE (c:Chunk {name: $chunkName})
            ON CREATE SET c.id_rc = randomUUID(), c.createdAt = datetime()
            SET c.title = $title, c.section = $section, c.text = $text,
                c.projectName = $projectName, c.updatedAt = datetime()
            MERGE (doc)-[:HAS_CHUNK]->(c)
        """, {
            "documentId": parsed["documentId"],
            "chunkName": f"{doc_name}.Chunk.{chunk['section']}",
            "title": chunk["title"], "section": chunk["section"],
            "text": chunk["text"], "projectName": project_name,
        }).consume()

    for task in parsed["tasks"]:
        tx.run("""
            MATCH (sr:ServiceRequest {id_rc: $serviceRequestId})
            MERGE (t:Task {name: $taskName})
            ON CREATE SET t.id_rc = randomUUID(), t.createdAt = datetime()
            SET t.title = $title, t.description = $description,
                t.assignedDate = CASE WHEN $assignedDate IS NULL THEN NULL ELSE date($assignedDate) END,
                t.dueDate = CASE WHEN $dueDate IS NULL THEN NULL ELSE date($dueDate) END,
                t.finished = $finished, t.status = $status,
                t.source = $templateType, t.projectName = $projectName,
                t.updatedAt = datetime()
            MERGE (sr)-[:CREATED_TASK]->(t)
            WITH t
            WHERE $ownerName IS NOT NULL AND $ownerName <> ''
            MERGE (person:Person {name: $ownerName})
            SET person.id_rc = coalesce(person.id_rc, randomUUID()),
                person.projectName = $projectName
            MERGE (t)-[:ASSIGNED_TO]->(person)
        """, {
            "serviceRequestId": parsed["serviceRequestId"],
            "taskName": f"{name}.Task.{task['title']}",
            "title": task["title"], "description": task.get("description"),
            "assignedDate": task.get("assignedDate"), "dueDate": task.get("dueDate"),
            "finishedDate": task.get("finishedDate"),
            "finished": task.get("finished"), "status": task.get("status") or "OPEN",
            "ownerName": task.get("owner"), "projectName": project_name,
            "templateType": template_type,
        }).consume()

    if node_id:
        tx.run("""
            MATCH (parent {id_rc: $nodeId})
            MATCH (sr:ServiceRequest {id_rc: $serviceRequestId})
            MERGE (parent)-[:HAS_REQUEST]->(sr)
        """, {
            "nodeId": node_id,
            "serviceRequestId": parsed["serviceRequestId"],
        }).consume()


def write_task_graph(
    tx,
    project_name: str,
    html: str,
    parsed: dict,
    node_id: str = None,
    template_type: str = "CKEDITOR_TASK"
):
    """Persist one standalone task and its editable document and sections."""
    node_name = parsed.get("graphNodeName") or parsed.get("title")
    if not node_name:
        raise ValueError("Task requires a graphNodeName or title")

    parent_name = None
    if node_id:
        parent = tx.run("""
            MATCH (parent {id_rc: $nodeId})
            RETURN parent.name AS name
        """, {"nodeId": node_id}).single()
        if not parent or not parent["name"]:
            raise ValueError(f"Parent node {node_id} was not found or has no name")
        parent_name = parent["name"]
        # Stored node names can already include the project prefix.
        if parent_name.startswith(f"{project_name}."):
            parent_name = parent_name[len(project_name) + 1:]

    container_name = (
        f"{project_name}.{parent_name}.TaskContainer.{node_name}"
        if parent_name else f"{project_name}.TaskContainer.{node_name}"
    )
    document_name = f"{container_name}.Document"
    task_name = f"{container_name}.Task"
    task = parsed["tasks"][0]

    record = tx.run("""
        MERGE (container:TaskContainer {name: $containerName})
        ON CREATE SET container.createdAt = datetime()
        SET container.id_rc = coalesce(container.id_rc, randomUUID()),
            container.title = $title,
            container.language = $language,
            container.projectName = $projectName,
            container.updatedAt = datetime()

        MERGE (doc:DocumentHTML {name: $documentName})
        ON CREATE SET doc.createdAt = datetime()
        SET doc.id_rc = coalesce(doc.id_rc, randomUUID()),
            doc.title = $title,
            doc.html = $html,
            doc.language = $language,
            doc.projectName = $projectName,
            doc.sourceType = $templateType,
            doc.updatedAt = datetime()
        MERGE (container)-[:DOCUMENTED_BY]->(doc)

        MERGE (task:Task {name: $taskName})
        ON CREATE SET task.createdAt = datetime()
        SET task.id_rc = coalesce(task.id_rc, randomUUID()),
            task.title = $taskTitle,
            task.description = $description,
            task.status = $status,
            task.priority = $priority,
            task.summary = $summary,
            task.goal = $goal,
            task.assignedDate = CASE WHEN $assignedDate IS NULL THEN NULL ELSE date($assignedDate) END,
            task.dueDate = CASE WHEN $dueDate IS NULL THEN NULL ELSE date($dueDate) END,
            task.finishedDate = CASE WHEN $finishedDate IS NULL THEN NULL ELSE date($finishedDate) END,
            task.finished = CASE WHEN $finished IS NULL THEN NULL ELSE date($finished) END,
            task.source = $templateType,
            task.projectName = $projectName,
            task.updatedAt = datetime()
        MERGE (container)-[:CREATED_TASK]->(task)

        RETURN container.id_rc AS taskContainerId,
               doc.id_rc AS documentId,
               task.id_rc AS taskId
    """, {
        "containerName": container_name,
        "documentName": document_name,
        "taskName": task_name,
        "title": parsed["title"],
        "taskTitle": task["title"],
        "description": task.get("description"),
        "status": task.get("status") or "OPEN",
        "priority": task.get("priority"),
        "summary": parsed.get("summary"),
        "goal": parsed.get("goal"),
        "assignedDate": task.get("assignedDate"),
        "dueDate": task.get("dueDate"),
        "finishedDate": task.get("finishedDate"),
        "finished": task.get("finished"),        
        "projectName": project_name,
        "language": parsed.get("language") or "unknown",
        "html": html,
        "templateType": template_type,
    }).single()
    parsed["taskContainerId"] = record["taskContainerId"]
    parsed["documentId"] = record["documentId"]
    parsed["taskId"] = record["taskId"]

    for position, chunk in enumerate(parsed.get("chunks", [])):
        section = chunk["section"]
        result = tx.run("""
            MATCH (doc:DocumentHTML {id_rc: $documentId})
            MERGE (c:Chunk {name: $chunkName})
            ON CREATE SET c.createdAt = datetime()
            FOREACH (ignored IN CASE WHEN c.text IS NULL OR c.text <> $text THEN [1] ELSE [] END |
                REMOVE c.embedding, c.embeddingModel, c.embeddedAt
            )
            SET c.id_rc = coalesce(c.id_rc, randomUUID()),
                c.title = $title,
                c.section = $section,
                c.text = $text,
                c.position = $position,
                c.projectName = $projectName,
                c.updatedAt = datetime()
            MERGE (doc)-[:HAS_CHUNK]->(c)
            RETURN c.id_rc AS chunkId
        """, {
            "documentId": parsed["documentId"],
            "chunkName": f"{document_name}.Chunk.{section}",
            "title": chunk["title"],
            "section": section,
            "text": chunk["text"],
            "position": position,
            "projectName": project_name,
        }).single()
        chunk["id"] = result["chunkId"]

    for person_name, relationship in (
        (task.get("owner"), "ASSIGNED_TO"),
        (task.get("createdBy"), "CREATED_BY"),
    ):
        if person_name:
            tx.run(f"""
                MATCH (task:Task {{id_rc: $taskId}})
                MERGE (person:Person {{name: $personName}})
                SET person.id_rc = coalesce(person.id_rc, randomUUID()),
                    person.projectName = $projectName
                MERGE (task)-[:{relationship}]->(person)
            """, {
                "taskId": parsed["taskId"],
                "personName": person_name,
                "projectName": project_name,
            }).consume()

    if node_id:
        tx.run("""
            MATCH (parent {id_rc: $nodeId})
            MATCH (container:TaskContainer {id_rc: $taskContainerId})
            MERGE (parent)-[:HAS_DETAILS]->(container)
        """, {
            "nodeId": node_id,
            "taskContainerId": parsed["taskContainerId"],
        }).consume()


def write_generic_graph(
    tx,
    project_name: str,
    html: str,
    parsed: dict,
    node_id: str = None,
    template_type: str = "CKEDITOR_DOCUMENTATION"
):
    """
    Generic writer for non-meeting templates. Creates a primary node with a label
    derived from the template type and a DocumentHTML node linked to it.

    Falls back to creating Task and Person nodes when present in `parsed`.
    """
    # derive a simple label mapping
    mapping = {
        "CKEDITOR_MEETING": "MeetingSummary",
        "CKEDITOR_DOCUMENTATION": "Documentation",
        "CKEDITOR_SERVICE_REQUEST": "ServiceRequest",
        "CKEDITOR_TASK": "TaskContainer",
    }
    primary_label = mapping.get(template_type, template_type.replace("CKEDITOR_", "").title())

    # create primary node
    primary_id = parsed.get("meetingId") or parsed.get("documentId") or str(uuid.uuid4())
    tx.run(f"""
        MERGE (p:{primary_label} {{id_rc: $primaryId}})
        SET p.name = $projectName + '.{primary_label}.' + $nodeName,
            p.title = $title,
            p.language = $language,
            p.projectName = $projectName,
            p.createdAt = datetime()

        MERGE (doc:DocumentHTML {{id_rc: $documentId}})
        SET doc.name = $projectName +'.'+ p.name + '.Document.' + $nodeName,
            doc.title = $title,
            doc.html = $html,
            doc.language = $language,
            doc.projectName = $projectName,
            doc.sourceType = $templateType,
            doc.createdAt = datetime()

        MERGE (p)-[:DOCUMENTED_BY]->(doc)
    """, {
        "projectName": project_name,
        "primaryId": primary_id,
        "documentId": parsed.get("documentId" , str(uuid.uuid4())),
        "title": parsed.get("title", "Document"),
        "nodeName": parsed.get("graphNodeName") or parsed.get("title"),
        "language": parsed.get("language", "unknown"),
        "html": html,
        "templateType": template_type
    })

    # Persist parser-produced sections as searchable chunks linked to the
    # complete editable document. Stable names make repeated saves update them.
    for position, chunk in enumerate(parsed.get("chunks", [])):
        section = chunk.get("section") or f"section_{position}"
        chunk_name = f"{primary_id}.Chunk.{section}"
        tx.run("""
            MATCH (doc:DocumentHTML {id_rc: $documentId})
            MERGE (c:Chunk {name: $chunkName})
            ON CREATE SET c.createdAt = datetime()
            FOREACH (
                ignored IN CASE
                    WHEN c.text IS NULL OR c.text <> $text THEN [1]
                    ELSE []
                END |
                REMOVE c.embedding, c.embeddingModel, c.embeddedAt
            )
            SET c.id_rc = coalesce(c.id_rc, randomUUID()),
                c.title = $title,
                c.section = $section,
                c.text = $text,
                c.position = $position,
                c.projectName = $projectName,
                c.updatedAt = datetime()
            MERGE (doc)-[:HAS_CHUNK]->(c)
        """, {
            "documentId": parsed.get("documentId"),
            "chunkName": chunk_name,
            "title": chunk.get("title") or f"{parsed.get('title', 'Task')} - {section}",
            "section": section,
            "text": chunk.get("text") or "",
            "position": position,
            "projectName": project_name,
        }).consume()

    # create tasks if present (reuse existing Task creation snippet)
    for task in parsed.get("tasks", []):
        task_id = str(uuid.uuid4())
        tx.run("""
            MATCH (p:%s {id_rc: $primaryId})

            MERGE (t:Task {id_rc: $taskId})
            SET t.name = $projectName + '.Task.' + $title,
                t.title = $title,
                t.description = $description,
                t.assignedDate = CASE
                    WHEN $assignedDate IS NULL THEN NULL
                    ELSE date($assignedDate)
                END,
                t.dueDate = CASE
                    WHEN $dueDate IS NULL THEN NULL
                    ELSE date($dueDate)
                END,
                t.finishedDate = CASE
                    WHEN $finishedDate IS NULL THEN NULL
                    ELSE date($finishedDate)
                END,    
                t.status = $status,
                t.finished = $finished,
                t.source = $templateType,
                t.projectName = $projectName,
                t.createdAt = datetime()

            MERGE (p)-[:CREATED_TASK]->(t)

            WITH t
            WHERE $ownerName IS NOT NULL AND $ownerName <> ''

            MERGE (person:Person {name: $ownerName})
            SET person.id_rc = coalesce(person.id_rc, randomUUID()),
                person.projectName = $projectName

            MERGE (t)-[:ASSIGNED_TO]->(person)
        """ % primary_label, {
            "primaryId": primary_id,
            "taskId": task_id,
            "title": task.get("title"),
            "description": task.get("description"),
            "assignedDate": task.get("assignedDate"),
            "dueDate": task.get("dueDate"),
            "finishedDate": task.get("finishedDate"),
            "status": task.get("status", "OPEN"),
            "ownerName": task.get("owner"),
            "projectName": project_name,
            "templateType": template_type,
            "finished": task.get("finished")
        })

    # attach to parent node if requested
    if node_id:
        tx.run(f"""
            MATCH (parent {{id_rc: $nodeId}})
            MATCH (p:{primary_label} {{id_rc: $primaryId}})
            MERGE (parent)-[:HAS_DETAILS]->(p)
        """, {"nodeId": node_id, "primaryId": primary_id})


@meeting_graph_bp.route("/generate-graph", methods=["POST"])
def generate_graph():
    try:
        data = request.get_json(force=True)
        # tolerate cases where request.get_json returns a raw string
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                # treat the entire body as HTML
                data = {"html": data}

        if not isinstance(data, dict):
            # fallback: try raw body
            raw = (request.get_data(as_text=True) or "").strip()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"html": raw}

        html = data.get("html", "")
        template_type = clean_text(data.get("templateType", ""))
        if not template_type:
            template_type = extract_template_type_from_html(html) or "CKEDITOR_MEETING"    
        print("REQUEST templateType:", data.get("templateType"), flush=True)
        print("SELECTED template_type:", template_type, flush=True)            
        return generate_specific_graph(data, template_type)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500

def generate_specific_graph(data,template_type):
    try:                
        project_name = data.get("projectName", "WS_CMRLECR")
        node_id = data.get("nodeId", None)
        html = data.get("html", "")

        # normalize template_type and dispatch parser based on it
        template_type = clean_text(template_type or "").upper()

        parsers = {
            "CKEDITOR_MEETING": parse_meeting_html,
            "CKEDITOR_DOCUMENTATION": parse_document_html,
            "CKEDITOR_SERVICE_REQUEST": parse_service_request_html,
            "CKEDITOR_TASK": parse_task_html,
        }

        parser = parsers.get(template_type)
        if parser is None:
            # helpful error when an unknown templateType is supplied
            available = ", ".join(sorted(parsers.keys()))
            return jsonify({
                "ok": False,
                "error": f"Unknown templateType '{template_type}'. Available: {available}"
            }), 400

        if not html.strip():
            return jsonify({
                "ok": False,
                "error": "No HTML content received."
            }), 400

        # CKEditor submits a body fragment, so head meta tags are not included in `html`.
        # The editor sends graphNodeName separately through the request JSON.
        request_graph_node_name = clean_text(data.get("graphNodeName", ""))
        if template_type == "CKEDITOR_SERVICE_REQUEST" and request_graph_node_name in (
            "MeetingSummary", "Summary"
        ):
            # Older editor documents can retain the meeting template's default.
            # CKEditor sends only the body fragment, so restore the service
            # request template's graph-node default when its head metadata is absent.
            request_graph_node_name = "ServiceRequest"

        # Older saved task documents carry the editor's generic "Summary"
        # value; use the actual task heading as their graph identity instead.
        if template_type == "CKEDITOR_TASK" and request_graph_node_name in (
            "MeetingSummary", "Summary"
        ):
            request_graph_node_name = ""

        parsed = parser(html)
        # apply graphNodeName from request to parsed output so chunk titles use it
        if request_graph_node_name:
            parsed["graphNodeName"] = request_graph_node_name
            if template_type not in ("CKEDITOR_SERVICE_REQUEST", "CKEDITOR_TASK"):
                parsed["title"] = request_graph_node_name
            for chunk in parsed.get("chunks", []):
                orig = chunk.get("title", "")
                parts = orig.split(" - ", 1)
                suffix = parts[1] if len(parts) > 1 else parts[0]
                chunk["title"] = f"{request_graph_node_name} - {suffix}"        

        print("TEMPLATE TYPE:", template_type, flush=True)

        soup_debug = BeautifulSoup(html, "html.parser")
        print("SECTION COUNT:", len(soup_debug.find_all("section")), flush=True)
        print(
            "H2 HEADINGS:",
            [h.get_text(" ", strip=True) for h in soup_debug.find_all("h2")],
            flush=True
        )

        for key in ("chunks", "attendees", "agenda", "tasks", "relatedObjects"):
            print(f"{key}: {len(parsed.get(key) or [])}", flush=True)

        # CKEditor submits a body fragment, so head meta tags are not included in `html`.
        # The editor sends graphNodeName separately through the request JSON.
        # request_graph_node_name = clean_text(data.get("graphNodeName", ""))

        if request_graph_node_name:
            parsed["graphNodeName"] = request_graph_node_name        

        # normalize parsed output to ensure writer receives expected structure
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                return jsonify({"ok": False, "error": "Parser returned a string that is not valid JSON."}), 500

        if not isinstance(parsed, dict):
            return jsonify({"ok": False, "error": f"Parser returned unexpected type: {type(parsed)}"}), 500

        # ensure common identifiers and collection keys exist
        parsed.setdefault("meetingId", str(uuid.uuid4()))
        parsed.setdefault("documentId", str(uuid.uuid4()))
        parsed.setdefault("title", parsed.get("title") or "")
        parsed.setdefault("language", parsed.get("language") or "unknown")
        parsed.setdefault("attendees", parsed.get("attendees") or [])
        parsed.setdefault("agenda", parsed.get("agenda") or [])
        parsed.setdefault("notes", parsed.get("notes") or "")
        parsed.setdefault("tasks", parsed.get("tasks") or [])
        parsed.setdefault("chunks", parsed.get("chunks") or [])
        if template_type == "CKEDITOR_DOCUMENTATION":
            parsed.setdefault("documentationId", parsed.get("documentationId") or str(uuid.uuid4()))

        # sanitize user-visible graph node names and titles (remove emojis etc.)
        if parsed.get("graphNodeName"):
            parsed["graphNodeName"] = sanitize_node_name(parsed.get("graphNodeName"))
        if parsed.get("title"):
            parsed["title"] = sanitize_node_name(parsed.get("title"))

        # also update chunk titles so they match cleaned graph node name
        for chunk in parsed.get("chunks", []):
            if chunk.get("title"):
                parts = chunk["title"].split(" - ", 1)
                suffix = parts[1] if len(parts) > 1 else parts[0]
                node_name = parsed.get("graphNodeName") or parsed.get("title") or suffix
                node_name = sanitize_node_name(node_name)
                chunk["title"] = f"{node_name} - {suffix}"

        _ensure_driver()
        # choose writer
        if template_type == "CKEDITOR_MEETING":
            writer = write_meeting_graph
        elif template_type == "CKEDITOR_DOCUMENTATION":
            writer = write_document_graph
        elif template_type == "CKEDITOR_SERVICE_REQUEST":
            writer = write_service_request_graph
        elif template_type == "CKEDITOR_TASK":
            writer = write_task_graph
        else:
            return jsonify({"ok": False, "error": f"Unknown templateType '{template_type}'"}), 400

        # debug check before Neo4j write
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                return jsonify({"ok": False, "error": "parsed is string but not valid JSON", "preview": parsed[:200]}), 500
        if not isinstance(parsed, dict):
            return jsonify({"ok": False, "error": f"parsed has wrong type: {type(parsed)}"}), 500

        # then open session and write as before
        try:
            with driver.session() as session:
                session.execute_write(writer, project_name, html, parsed, node_id, template_type)
        except Exception as exc:
            tb = traceback.format_exc()
            return jsonify({
                "ok": False,
                "error": str(exc),
                "traceback": tb,
                "parsed_preview": (parsed[:1000] if isinstance(parsed, str) else repr(parsed)[:2000])
            }), 500
            

        

        
        # tailor response to template type
        if template_type == "CKEDITOR_DOCUMENTATION":            
            return jsonify({
                "ok": True,
                "documentationId": parsed.get("documentationId"),
                "documentId": parsed.get("documentId"),
                "title": parsed.get("title"),
                "chunksCount": len(parsed.get("chunks", [])),
                "relatedObjectsCount": len(parsed.get("relatedObjects", [])),
                "sourcesCount": len(parsed.get("sources", [])),
                "changesCount": len(parsed.get("changes", []))
            })
        elif template_type == "CKEDITOR_SERVICE_REQUEST":
            return jsonify({
                "ok": True,
                "serviceRequestId": parsed["serviceRequestId"],
                "documentId": parsed["documentId"],
                "title": parsed["title"],
                "tasksCount": len(parsed["tasks"]),
                "chunksCount": len(parsed["chunks"]),
            })
        elif template_type == "CKEDITOR_TASK":
            return jsonify({
                "ok": True,
            "taskContainerId": parsed["taskContainerId"],
            "taskId": parsed["taskId"],
                "documentId": parsed["documentId"],
                "title": parsed["title"],
                "tasksCount": len(parsed["tasks"]),
                "chunksCount": len(parsed["chunks"]),
            })        
        else:
            return jsonify({
                "ok": True,
                "meetingId": parsed.get("meetingId"),
                "meetingTitle": parsed.get("title"),
                "attendeesCount": len(parsed.get("attendees", [])),
                "tasksCount": len(parsed.get("tasks", [])),
                "chunksCount": len(parsed.get("chunks", []))
            })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500
