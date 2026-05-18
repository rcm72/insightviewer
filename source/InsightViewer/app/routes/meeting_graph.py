# meeting_graph.py

from flask import Blueprint, request, jsonify
from bs4 import BeautifulSoup
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
    value = clean_text(value).lower()

    replacements = {
        "📅": "",
        "👥": "",
        "📝": "",
        "🗣️": "",
        "📌": "",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return clean_text(value)


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

    for row in rows[1:]:
        cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]

        if len(cells) < 1 or not cells[0]:
            continue

        title = cells[0]

        task = {
            "title": title,
            "owner": cells[1] if len(cells) > 1 else None,
            "assignedDate": parse_date(cells[2]) if len(cells) > 2 else None,
            "dueDate": parse_date(cells[3]) if len(cells) > 3 else None,
            "description": details.get(title, ""),
            "status": "OPEN"
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
    language = get_language(soup)
    sections = get_sections(soup)

    attendees = parse_attendees(sections.get("attendees"))
    agenda = parse_agenda(sections.get("agenda"))
    notes = parse_notes(sections.get("notes"))
    tasks = parse_tasks(sections.get("tasks"))
    chunks = build_chunks(title, sections)

    return {
        "meetingId": str(uuid.uuid4()),
        "documentId": str(uuid.uuid4()),
        "title": title,
        "language": language,
        "attendees": attendees,
        "agenda": agenda,
        "notes": notes,
        "tasks": tasks,
        "chunks": chunks
    }


def write_meeting_graph(tx, project_name: str, html: str, parsed: dict, node_id: str = None):
    tx.run("""
        MERGE (m:Meeting {id_rc: $meetingId})
        SET m.name = $projectName + '.Meeting.' + $title,
            m.title = $title,
            m.language = $language,
            m.projectName = $projectName,
            m.createdAt = datetime()

        MERGE (doc:DocumentHTML {id_rc: $documentId})
        SET doc.name = $projectName + '.Document.' + $title,
            doc.title = $title,
            doc.html = $html,
            doc.language = $language,
            doc.projectName = $projectName,
            doc.sourceType = 'CKEDITOR_MEETING',
            doc.createdAt = datetime()

        MERGE (m)-[:DOCUMENTED_BY]->(doc)
    """, {
        "projectName": project_name,
        "meetingId": parsed["meetingId"],
        "documentId": parsed["documentId"],
        "title": parsed["title"],
        "language": parsed["language"],
        "html": html
    })

    for attendee in parsed["attendees"]:
        tx.run("""
            MATCH (m:Meeting {id_rc: $meetingId})

            MERGE (person:Person {name: $personName})
            SET person.projectName = $projectName

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
            MATCH (m:Meeting {id_rc: $meetingId})

            MERGE (a:AgendaItem {
                meetingId: $meetingId,
                title: $title
            })
            SET a.id_rc = coalesce(a.id_rc, randomUUID()),
                a.name = $projectName + '.AgendaItem.' + $title,
                a.projectName = $projectName

            MERGE (m)-[:HAS_AGENDA_ITEM]->(a)
        """, {
            "meetingId": parsed["meetingId"],
            "title": agenda_item,
            "projectName": project_name
        })

    if parsed["notes"]:
        tx.run("""
            MATCH (m:Meeting {id_rc: $meetingId})

            MERGE (n:MeetingNote {meetingId: $meetingId})
            SET n.id_rc = coalesce(n.id_rc, randomUUID()),
                n.name = $projectName + '.MeetingNote.' + $meetingId,
                n.text = $notes,
                n.projectName = $projectName

            MERGE (m)-[:HAS_NOTE]->(n)
        """, {
            "meetingId": parsed["meetingId"],
            "notes": parsed["notes"],
            "projectName": project_name
        })

    for task in parsed["tasks"]:
        task_id = str(uuid.uuid4())

        tx.run("""
            MATCH (m:Meeting {id_rc: $meetingId})

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
                t.status = $status,
                t.source = 'meeting',
                t.projectName = $projectName,
                t.createdAt = datetime()

            MERGE (m)-[:CREATED_TASK]->(t)

            WITH t
            WHERE $ownerName IS NOT NULL AND $ownerName <> ''

            MERGE (person:Person {name: $ownerName})
            SET person.projectName = $projectName

            MERGE (t)-[:ASSIGNED_TO]->(person)
        """, {
            "meetingId": parsed["meetingId"],
            "taskId": task_id,
            "title": task["title"],
            "description": task.get("description"),
            "assignedDate": task.get("assignedDate"),
            "dueDate": task.get("dueDate"),
            "status": task.get("status", "OPEN"),
            "ownerName": task.get("owner"),
            "projectName": project_name
        })

    for chunk in parsed["chunks"]:
        tx.run("""
            MATCH (doc:DocumentHTML {id_rc: $documentId})

            MERGE (c:Chunk {id_rc: $chunkId})
            SET c.name = $projectName + '.Chunk.' + $title,
                c.title = $title,
                c.section = $section,
                c.text = $text,
                c.projectName = $projectName,
                c.createdAt = datetime()

            MERGE (doc)-[:HAS_CHUNK]->(c)
        """, {
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
            MATCH (m:Meeting {id_rc: $meetingId})
            MERGE (parent)-[:HAS_MEETING]->(m)
        """, {
            "nodeId": node_id,
            "meetingId": parsed["meetingId"]
        })


@meeting_graph_bp.route("/generate-meeting-graph", methods=["POST"])
def generate_meeting_graph():
    try:
        data = request.get_json(force=True)

        html = data.get("html", "")
        project_name = data.get("projectName", "WS_CMRLECR")
        node_id = data.get("nodeId", None)

        if not html.strip():
            return jsonify({
                "ok": False,
                "error": "No HTML content received."
            }), 400

        parsed = parse_meeting_html(html)

        _ensure_driver()
        with driver.session() as session:
            session.execute_write(write_meeting_graph, project_name, html, parsed, node_id)

        return jsonify({
            "ok": True,
            "meetingId": parsed["meetingId"],
            "meetingTitle": parsed["title"],
            "attendeesCount": len(parsed["attendees"]),
            "tasksCount": len(parsed["tasks"]),
            "chunksCount": len(parsed["chunks"])
        })

    except Exception as exc:
        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500
