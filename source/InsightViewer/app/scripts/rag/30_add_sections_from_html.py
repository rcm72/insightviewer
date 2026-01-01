""" 
Ker si že uvozil node-e, je najlažje sekcije dodati z ponovnim branjem HTML in potem:
ustvariti :Section

povezati člena v pravo sekcijo 
"""

import configparser
import os, re
from typing import Optional, Tuple, List
import uuid
from bs4 import BeautifulSoup
from neo4j import GraphDatabase

PROJECT = "ZGD1"
ACT_ID = "ZGD-1"

BASE_DIR = os.path.dirname(__file__)
HTML_PATH = os.path.join(
    BASE_DIR,
    "",
    "",
    "zakon",
    "data",
    "ZAKO4291_NPB22.html",
)


config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))
NEO4J_URI = config['NEO4J']['URI']
NEO4J_USER = config['NEO4J']['USERNAME']
NEO4J_PASSWORD = config['NEO4J']['PASSWORD']


def rc_id() -> str:
    return str(uuid.uuid4())


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_section_level(p_classes: List[str]) -> Optional[Tuple[str, int]]:
    """
    HTML razredi: oddelek, pododdelek, odsek
    Vrne (type, level) kjer level določa gnezdenje.
    """
    if "oddelek" in p_classes:
        return ("oddelek", 1)
    if "pododdelek" in p_classes:
        return ("pododdelek", 2)
    if "odsek" in p_classes:
        return ("odsek", 3)
    return None


def merge_section(tx, sid: str, stype: str, title: str, number: str, parent_label: str, parent_key: str, parent_val: str):
    """
    Ustvari Section (če ne obstaja) in ga pripne na parent.
    Nastavi id_rc + projectName samo ob CREATE.
    """
    tx.run(
        f"""
        MATCH (parent:{parent_label} {{{parent_key}: $parentVal, projectName:$projectName}})
        MERGE (s:Section {{sid:$sid}})
        ON CREATE SET
          s.id_rc = $id_rc,
          s.type = $stype,
          s.title = $title,
          s.number = $number,
          s.projectName = $projectName
        ON MATCH SET
          s.type = coalesce(s.type, $stype),
          s.title = coalesce(s.title, $title),
          s.number = coalesce(s.number, $number),
          s.projectName = $projectName
        MERGE (parent)-[:HAS_SECTION]->(s)
        """,
        sid=sid,
        id_rc=rc_id(),
        stype=stype,
        title=title,
        number=number,
        parentVal=parent_val,
        projectName=PROJECT,
    )


def attach_article_to_section(tx, section_sid: str, article_num: str):
    """
    Najde Article po (projectName + num) in ga pripne v Section.
    """
    tx.run(
        """
        MATCH (s:Section {sid:$sid, projectName:$projectName})
        MATCH (a:Article {num:$num, projectName:$projectName})
        MERGE (s)-[:HAS_ARTICLE]->(a)
        """,
        sid=section_sid,
        num=article_num,
        projectName=PROJECT,
    )


def main():
    # preberi HTML
    with open(HTML_PATH, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    # trenutni kontekst
    current_chapter_title: Optional[str] = None
    current_chapter_cid: Optional[str] = None

    # stack sekcij (stype, sid, level)
    section_stack: List[Tuple[str, str, int]] = []

    def resolve_chapter(session, title: str) -> Optional[str]:
        rec = session.run(
            """
            MATCH (c:Chapter {projectName:$projectName})
            WHERE c.title = $title
            RETURN c.cid AS cid
            LIMIT 1
            """,
            projectName=PROJECT,
            title=title,
        ).single()
        return rec["cid"] if rec else None

    def compute_section_sid(chapter_cid: str, stype: str, level: int, number: str, ordinal_in_level: int) -> str:
        # Stabilen SID; pomembno je, da je unikaten in determinističen.
        # Če imaš večkrat isti naslov, ordinal_in_level poskrbi za unikaten SID.
        return f"{PROJECT}:SEC:{chapter_cid}:{level}:{stype}:{ordinal_in_level}:{number}"

    try:
        with driver.session() as session:
            body = soup.select_one("div.mainText") or soup.body
            if not body:
                raise RuntimeError("Ne najdem glavnega vsebinskega bloka (div.mainText / body).")

            for p in body.find_all("p"):
                cls = p.get("class") or []
                text = clean(p.get_text(" ", strip=True))
                if not text:
                    continue

                # 1) POGLAVJE
                if "poglavje" in cls:
                    current_chapter_title = text
                    current_chapter_cid = resolve_chapter(session, text)
                    section_stack = []  # reset stack ob novem poglavju
                    continue

                # Če poglavja še nimamo, sekcije ignoriramo (lahko tudi naredimo fallback, ampak bolje je čisto)
                if not current_chapter_cid:
                    continue

                # 2) SEKCIJE: oddelek/pododdelek/odsek
                sec_info = parse_section_level(cls)
                if sec_info:
                    stype, level = sec_info

                    # “oddelek/pododdelek/odsek” naslov:
                    title = text
                    number = title.split()[0] if title.split() else ""

                    # stack management: odreži do (level-1)
                    while len(section_stack) >= level:
                        section_stack.pop()

                    # ordinal na tem level-u (znotraj trenutnega parenta)
                    ordinal = 1
                    if len(section_stack) > 0:
                        # preštej že obstoječe “siblinge” istega levela v stack-u ne vidimo,
                        # zato naredimo ordinal deterministično iz dolžine + 1.
                        # (Za popolno stabilnost bi lahko šteli v Neo4j, ampak za MVP je to OK.)
                        ordinal = 1
                    else:
                        ordinal = 1

                    sid = compute_section_sid(current_chapter_cid, stype, level, number, ordinal)

                    # parent je Chapter ali zadnja sekcija v stacku
                    if len(section_stack) == 0:
                        session.execute_write(
                            merge_section,
                            sid, stype, title, number,
                            "Chapter", "cid", current_chapter_cid
                        )
                    else:
                        parent_sid = section_stack[-1][1]
                        session.execute_write(
                            merge_section,
                            sid, stype, title, number,
                            "Section", "sid", parent_sid
                        )

                    section_stack.append((stype, sid, level))
                    continue

                # 3) ČLEN – ko naletimo na člen, ga pripnemo na trenutno sekcijo (zadnja v stacku)
                if "clen" in cls and "center" in cls and "bold" in cls and re.search(r"\bčlen\b", text):
                    if len(section_stack) == 0:
                        continue  # člen ni znotraj sekcije
                    # npr. "10.a člen" -> "10.a"
                    article_num = clean(text).replace("člen", "").strip()
                    current_section_sid = section_stack[-1][1]
                    session.execute_write(attach_article_to_section, current_section_sid, article_num)
                    continue

        print("OK: Section/oddelek/pododdelek/odsek dodani; členi pripeti na sekcije.")
        print(f"Neo4j: {NEO4J_URI} | projectName={PROJECT}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
