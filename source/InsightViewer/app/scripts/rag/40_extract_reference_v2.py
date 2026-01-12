""" Ta skripta:
bere text iz Paragraph, Point, IndentItem
poišče sklice na x. člen / x.a člen / x. odstavek
ustvari (:Reference {refId, id_rc, raw, articleNum, paragraphNum, ...})
poveže:
(source)-[:CITES]->(Reference)
(Reference)-[:TARGETS]->(Article) ali (Reference)-[:TARGETS]->(Paragraph) če cilj obstaja
Če cilj ne obstaja, Reference ostane brez TARGETS (to je OK). """

import configparser
import os
from pathlib import Path
import re
import uuid
import hashlib
from typing import Optional, List, Tuple

from neo4j import GraphDatabase

PROJECT = "ZGD1"

# BASE_DIR = os.path.dirname(__file__)
# config = configparser.ConfigParser()
# config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))

# BASE_DIR should point to project root: /home/robert/insightViewer/source/InsightViewer
BASE_DIR = Path(__file__).resolve().parents[3]
CONFIG_PATH = BASE_DIR / "config.ini"

config = configparser.ConfigParser()
config.read(CONFIG_PATH)

HTML_PATH = (
    Path(__file__)
    .resolve()
    .parent              # .../app/scripts/rag
    / "zakon"
    / "data"
    / "ZAKO4291_NPB22.html"
)



NEO4J_URI = config['NEO4J']['URI']
NEO4J_USER = config['NEO4J']['USERNAME']
NEO4J_PASSWORD = config['NEO4J']['PASSWORD']


def rc_id() -> str:
    return str(uuid.uuid4())


# --- Regexi (praktični za ZGD1, lahko jih nadgradimo) ---

# "10. člen", "10.a člen", "70.č člen" + skloni
ARTICLE_RE = re.compile(
    r"\b(?P<num>\d{1,4})\.\s*(?P<suf>[a-zčšž])?\s*člen(?:a|u|om|ih|i)?\b",
    re.IGNORECASE,
)

# "2. odstavek" (številčni)
PAR_NUM_RE = re.compile(r"\b(?P<pn>\d{1,2})\.\s*odstavek\b", re.IGNORECASE)

# "prvi/drugi/..." (besedni)
ORDINALS = {
    "prvi": 1, "drugi": 2, "tretji": 3, "četrti": 4, "peti": 5,
    "šesti": 6, "sedmi": 7, "osmi": 8, "deveti": 9, "deseti": 10,
}
ORD_PAR_RE = re.compile(
    r"\b(?P<ord>prvi|drugi|tretji|četrti|peti|šesti|sedmi|osmi|deveti|deseti)\s+odstavek\b",
    re.IGNORECASE,
)


def normalize_article_num(num: str, suf: Optional[str]) -> str:
    num = num.strip()
    suf = (suf or "").strip()
    if suf:
        return f"{num}.{suf.lower()}"
    return f"{num}."


def find_paragraph_num_near(text: str, start: int, end: int) -> Optional[int]:
    """
    Poišče omenjen odstavek v bližini sklica (±80 znakov).
    Primeri:
      - "v drugem odstavku 10.a člena"
      - "2. odstavek 10. člena"
    """
    left = max(0, start - 80)
    right = min(len(text), end + 80)
    window = text[left:right]

    m = PAR_NUM_RE.search(window)
    if m:
        return int(m.group("pn"))

    m2 = ORD_PAR_RE.search(window)
    if m2:
        ordw = m2.group("ord").lower()
        return ORDINALS.get(ordw)

    return None


def make_ref_id(source_id: str, raw: str) -> str:
    # determinističen refId: isti source+raw -> isti refId (idempotentno)
    h = hashlib.sha1((source_id + "|" + raw).encode("utf-8")).hexdigest()[:12]
    return f"{PROJECT}:REF:{h}"


def extract_references(text: str) -> List[Tuple[str, Optional[int], str]]:
    """
    Vrne seznam (articleNum, paragraphNum, rawMatch)
    """
    refs = []
    for m in ARTICLE_RE.finditer(text):
        article_num = normalize_article_num(m.group("num"), m.group("suf"))
        par_num = find_paragraph_num_near(text, m.start(), m.end())
        raw = m.group(0)
        refs.append((article_num, par_num, raw))
    return refs


# --- Neo4j write ops ---

def upsert_reference(tx, source_label: str, source_key: str, source_id: str,
                    refId: str, raw: str, articleNum: str, paragraphNum: Optional[int]):
    targetType = "Paragraph" if paragraphNum is not None else "Article"
    tx.run(
        f"""
        MATCH (src:{source_label} {{{source_key}: $sourceId, projectName:$projectName}})
        MERGE (r:Reference {{refId:$refId}})
        ON CREATE SET
          r.id_rc = $id_rc,
          r.raw = $raw,
          r.articleNum = $articleNum,
          r.paragraphNum = $paragraphNum,
          r.targetType = $targetType,
          r.confidence = $confidence,
          r.projectName = $projectName
        MERGE (src)-[:CITES]->(r)
        """,
        projectName=PROJECT,
        sourceId=source_id,
        refId=refId,
        id_rc=rc_id(),
        raw=raw,
        articleNum=articleNum,
        paragraphNum=paragraphNum,
        targetType=targetType,
        confidence=0.85
    )


def link_target(tx, refId: str, articleNum: str, paragraphNum: Optional[int]):
    # link na Article ali Paragraph, če obstaja
    if paragraphNum is None:
        tx.run(
            """
            MATCH (r:Reference {refId:$refId, projectName:$projectName})
            MATCH (a:Article {num:$num, projectName:$projectName})
            MERGE (r)-[:TARGETS]->(a)
            """,
            refId=refId, projectName=PROJECT, num=articleNum
        )
    else:
        tx.run(
            """
            MATCH (r:Reference {refId:$refId, projectName:$projectName})
            MATCH (a:Article {num:$num, projectName:$projectName})-[:HAS_PARAGRAPH]->(p:Paragraph {order:$ord, projectName:$projectName})
            MERGE (r)-[:TARGETS]->(p)
            """,
            refId=refId, projectName=PROJECT, num=articleNum, ord=paragraphNum
        )


def iterate_sources(session, label: str, key: str, text_prop: str, batch: int = 5000):
    """
    Generator: vrne (id, text) za node-e danega labela.
    """
    result = session.run(
        f"""
        MATCH (n:{label} {{projectName:$projectName}})
        RETURN n.{key} AS id, n.{text_prop} AS text
        """,
        projectName=PROJECT
    )
    for r in result:
        yield r["id"], (r["text"] or "")


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    total = 0

    try:
        with driver.session() as session:
            # 1) Paragraph – first read all, then write
            paragraph_sources = list(iterate_sources(session, "Paragraph", "parId", "text"))

        with driver.session() as session:
            for sid, text in paragraph_sources:
                for art, par, raw in extract_references(text):
                    refId = make_ref_id(sid, raw)
                    session.execute_write(
                        upsert_reference, "Paragraph", "parId", sid, refId, raw, art, par
                    )
                    session.execute_write(link_target, refId, art, par)
                    total += 1

        with driver.session() as session:
            # 2) Point
            point_sources = list(iterate_sources(session, "Point", "pointId", "text"))

        with driver.session() as session:
            for sid, text in point_sources:
                for art, par, raw in extract_references(text):
                    refId = make_ref_id(sid, raw)
                    session.execute_write(
                        upsert_reference, "Point", "pointId", sid, refId, raw, art, par
                    )
                    session.execute_write(link_target, refId, art, par)
                    total += 1

        with driver.session() as session:
            # 3) IndentItem
            item_sources = list(iterate_sources(session, "IndentItem", "itemId", "text"))

        with driver.session() as session:
            for sid, text in item_sources:
                for art, par, raw in extract_references(text):
                    refId = make_ref_id(sid, raw)
                    session.execute_write(
                        upsert_reference, "IndentItem", "itemId", sid, refId, raw, art, par
                    )
                    session.execute_write(link_target, refId, art, par)
                    total += 1

        print(f"OK: ustvarjenih/posodobljenih referenc = {total}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
