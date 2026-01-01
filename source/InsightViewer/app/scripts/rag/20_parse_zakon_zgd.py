import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from bs4 import BeautifulSoup
from neo4j import GraphDatabase


PROJECT_NAME = "ZGD1"
ACT_ID = "ZGD-1"
ACT_TITLE = "Zakon o gospodarskih družbah"
SOURCE = "PISRS"

# BASE_DIR should be project root: .../source/InsightViewer
BASE_DIR = os.path.dirname(__file__)
HTML_PATH = os.path.join(
    BASE_DIR,
    "",
    "",
    "zakon",
    "data",
    "ZAKO4291_NPB22.html",
)

# read Neo4j connection details from config.ini
import configparser
config = configparser.ConfigParser()
config.read(os.path.join(BASE_DIR, "..", "..", "..", "config.ini"))
NEO4J_URI = config['NEO4J']['URI']
NEO4J_USER = config['NEO4J']['USERNAME']
NEO4J_PASSWORD = config['NEO4J']['PASSWORD']


        #config.read('config.ini')




def clean_text(text: str) -> str:
    """Normalize whitespace and strip text."""
    return re.sub(r"\s+", " ", text or "").strip()


def parse_effective_date(soup: BeautifulSoup) -> Optional[str]:
    """
    V HTML je običajno blok:
    <p class="navezava-npb"><strong>Datum začetka uporabe:</strong>08.10.2025<br></p>
    """
    p = soup.select_one("p.navezava-npb")
    if not p:
        return None
    txt = clean_text(p.get_text(" ", strip=True))
    m = re.search(r"Datum začetka uporabe:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", txt)
    if not m:
        return None
    # vrnemo ISO datum
    d = datetime.strptime(m.group(1), "%d.%m.%Y").date()
    return d.isoformat()


def parse_npb_number(soup: BeautifulSoup) -> Optional[int]:
    """
    V HTML je npr:
    <p class="center bold npb">(neuradno prečiščeno besedilo št. 22)</p>
    """
    p = soup.select_one("p.npb")
    if not p:
        return None
    txt = clean_text(p.get_text(" ", strip=True))
    m = re.search(r"št\.\s*([0-9]+)", txt)
    return int(m.group(1)) if m else None


def norm_article_num(raw: str) -> str:
    """
    raw tipično: "10.a člen" ali "1. člen"
    mi shranimo samo "10.a" ali "1"
    """
    raw = clean_text(raw)
    raw = raw.replace("člen", "").strip()
    return raw


def article_key(article_num: str) -> str:
    # "10.a" -> "10a", "1." -> "1"
    k = article_num.replace(".", "").replace(" ", "")
    return k


@dataclass
class Context:
    version_id: str
    part_pid: Optional[str] = None
    chapter_cid: Optional[str] = None
    article_aid: Optional[str] = None
    article_num: Optional[str] = None
    paragraph_idx: int = 0
    last_par_id: Optional[str] = None
    point_idx: int = 0
    item_idx: int = 0


def merge_core(tx, act: Dict[str, Any], version: Dict[str, Any]):
    # merge dictionaries but ensure projectName only once
    params = {**act, **version}
    tx.run(
        """
        MERGE (a:Act {actId: $actId})
        ON CREATE SET a.id_rc = randomUUID()
        SET a.title=$title, a.shortTitle=$shortTitle, a.jurisdiction=$jurisdiction,
            a.language=$language, a.source=$source, a.projectName=$projectName

        MERGE (v:ActVersion {versionId: $versionId})
        ON CREATE SET v.id_rc = randomUUID()
        SET v.npbNumber=$npbNumber, v.effectiveFrom=$effectiveFrom,
            v.retrievedAt=$retrievedAt, v.projectName=$projectName

        MERGE (a)-[:HAS_VERSION]->(v)
        """,
        **params,
    )


def merge_part(tx, part: Dict[str, Any]):
    tx.run(
        """
        MERGE (p:Part {pid:$pid})
        ON CREATE SET p.id_rc = randomUUID()
        SET p.number=$number, p.title=$title, p.projectName=$projectName

        WITH p, $versionId AS versionId
        MATCH (v:ActVersion {versionId:versionId})
        MERGE (v)-[:HAS_PART]->(p)
        """,
        **part,
    )


def merge_chapter(tx, chapter: Dict[str, Any]):
    tx.run(
        """
        MERGE (c:Chapter {cid:$cid})
        ON CREATE SET c.id_rc = randomUUID()
        SET c.number=$number, c.title=$title, c.projectName=$projectName

        WITH c, $pid AS pid
        MATCH (p:Part {pid:pid})
        MERGE (p)-[:HAS_CHAPTER]->(c)
        """,
        **chapter,
    )


def merge_article(tx, article: Dict[str, Any]):
    tx.run(
        """
        MERGE (a:Article {aid:$aid})
        ON CREATE SET a.id_rc = randomUUID()
        SET a.num=$num, a.heading=$heading, a.projectName=$projectName

        WITH a, $cid AS cid
        MATCH (c:Chapter {cid:cid})
        MERGE (c)-[:HAS_ARTICLE]->(a)
        """,
        **article,
    )


def merge_paragraph(tx, par: Dict[str, Any]):
    tx.run(
        """
        MERGE (p:Paragraph {parId:$parId})
        ON CREATE SET p.id_rc = randomUUID()
        SET p.order=$order, p.text=$text, p.projectName=$projectName

        WITH p, $aid AS aid, $prevParId AS prevParId
        MATCH (a:Article {aid:aid})
        MERGE (a)-[:HAS_PARAGRAPH]->(p)

        WITH p, prevParId
        MATCH (prev:Paragraph {parId:prevParId})
        WHERE prevParId IS NOT NULL
        MERGE (prev)-[:NEXT]->(p)
        """,
        **par,
    )


def merge_point(tx, point: Dict[str, Any]):
    tx.run(
        """
        MERGE (p:Point {pointId:$pointId})
        ON CREATE SET p.id_rc = randomUUID()
        SET p.marker=$marker, p.order=$order, p.text=$text, p.projectName=$projectName

        WITH p, $parId AS parId, $prevPointId AS prevPointId
        MATCH (par:Paragraph {parId:parId})
        MERGE (par)-[:HAS_POINT]->(p)

        WITH p, prevPointId
        MATCH (prev:Point {pointId:prevPointId})
        WHERE prevPointId IS NOT NULL
        MERGE (prev)-[:NEXT]->(p)
        """,
        **point,
    )


def merge_item(tx, item: Dict[str, Any]):
    tx.run(
        """
        MERGE (i:IndentItem {itemId:$itemId})
        ON CREATE SET i.id_rc = randomUUID()
        SET i.order=$order, i.text=$text, i.projectName=$projectName

        WITH i, $parId AS parId
        MATCH (par:Paragraph {parId:parId})
        MERGE (par)-[:HAS_ITEM]->(i)
        """,
        **item,
    )


def parse_and_load(html_path: str):
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    npb = parse_npb_number(soup)
    effective = parse_effective_date(soup)

    version_id = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb or 'X'}"
    retrieved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    act = dict(
        actId=f"{PROJECT_NAME}:{ACT_ID}",
        title=ACT_TITLE,
        shortTitle=ACT_ID,
        jurisdiction="SI",
        language="sl",
        source=SOURCE,
        projectName=PROJECT_NAME,
    )
    version = dict(
        versionId=version_id,
        npbNumber=npb,
        effectiveFrom=effective,
        retrievedAt=retrieved_at,
        projectName=PROJECT_NAME,
    )

    ctx = Context(version_id=version_id)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            session.execute_write(merge_core, act, version)

            body = soup.select_one("div.mainText") or soup.body
            if not body:
                raise RuntimeError("Ne najdem glavnega vsebinskega bloka.")

            # Grezmo čez <p> elemente v zaporedju
            for p in body.find_all("p"):
                cls = p.get("class") or []
                text = clean_text(p.get_text(" ", strip=True))
                if not text:
                    continue

                # DEL
                if "del" in cls:
                    # primer: "I. DEL SKUPNE DOLOČBE"
                    part_title = text
                    part_num = part_title.split()[0]  # "I."
                    pid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:{part_num}".replace(" ", "")
                    ctx.part_pid = pid
                    ctx.chapter_cid = None
                    ctx.article_aid = None
                    ctx.paragraph_idx = 0
                    session.execute_write(
                        merge_part,
                        dict(
                            pid=pid,
                            number=part_num,
                            title=part_title,
                            versionId=version_id,
                            projectName=PROJECT_NAME,
                        ),
                    )
                    continue

                # POGLAVJE
                if "poglavje" in cls:
                    if not ctx.part_pid:
                        # če se zgodi, naredimo fallback part
                        fallback_pid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:NO_PART"
                        ctx.part_pid = fallback_pid
                        session.execute_write(
                            merge_part,
                            dict(
                                pid=fallback_pid,
                                number="",
                                title="(brez dela)",
                                versionId=version_id,
                                projectName=PROJECT_NAME,
                            ),
                        )
                    chap_title = text
                    # primer: "Prvo poglavje SPLOŠNO" -> number="Prvo"
                    chap_num = chap_title.split()[0]
                    cid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:{ctx.part_pid.split(':')[-1]}:{chap_num}"
                    ctx.chapter_cid = cid
                    ctx.article_aid = None
                    ctx.paragraph_idx = 0
                    session.execute_write(
                        merge_chapter,
                        dict(
                            cid=cid,
                            number=chap_num,
                            title=chap_title,
                            pid=ctx.part_pid,
                            projectName=PROJECT_NAME,
                        ),
                    )
                    continue

                # ČLEN (Article): p.center.bold.clen vsebuje npr "10.a člen"
                if "clen" in cls and "center" in cls and "bold" in cls:
                    # izločimo samo tiste, ki izgledajo kot številka člena
                    if re.search(r"\bčlen\b", text):
                        if not ctx.chapter_cid:
                            # fallback chapter
                            if not ctx.part_pid:
                                fallback_pid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:NO_PART"
                                ctx.part_pid = fallback_pid
                                session.execute_write(
                                    merge_part,
                                    dict(
                                        pid=fallback_pid,
                                        number="",
                                        title="(brez dela)",
                                        versionId=version_id,
                                        projectName=PROJECT_NAME,
                                    ),
                                )
                            fallback_cid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:{ctx.part_pid.split(':')[-1]}:NO_CHAPTER"
                            ctx.chapter_cid = fallback_cid
                            session.execute_write(
                                merge_chapter,
                                dict(
                                    cid=fallback_cid,
                                    number="",
                                    title="(brez poglavja)",
                                    pid=ctx.part_pid,
                                    projectName=PROJECT_NAME,
                                ),
                            )

                        num = norm_article_num(text)
                        aid = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:{article_key(num)}"
                        ctx.article_aid = aid
                        ctx.article_num = num
                        ctx.paragraph_idx = 0
                        ctx.last_par_id = None

                        # heading je pogosto naslednji <p class="center bold clen">(naslov)</p>
                        # zato ga tukaj nastavimo na None, in ga napolnimo, ko ga najdemo spodaj.
                        session.execute_write(
                            merge_article,
                            dict(
                                aid=aid,
                                num=num,
                                heading=None,
                                cid=ctx.chapter_cid,
                                projectName=PROJECT_NAME,
                            ),
                        )
                    continue

                # Naslov člena (heading): p.center.bold.clen z oklepaji, brez “člen”
                if "clen" in cls and "center" in cls and "bold" in cls and ctx.article_aid:
                    # primer: "(vsebina zakona)" ali "(pojmi)" – to ni “člen”
                    if text.startswith("(") and not re.search(r"\bčlen\b", text):
                        # update article heading
                        heading = text.strip()
                        session.run(
                            """
                            MATCH (a:Article {aid:$aid})
                            SET a.heading = $heading
                            """,
                            aid=ctx.article_aid,
                            heading=heading,
                        )
                    continue

                # ODSTAVEK
                if "odstavek" in cls and ctx.article_aid:
                    ctx.paragraph_idx += 1
                    par_id = f"{PROJECT_NAME}:{ACT_ID}_NPB{npb}:{article_key(ctx.article_num)}({ctx.paragraph_idx})"
                    prev = ctx.last_par_id
                    ctx.last_par_id = par_id

                    # reset točke/alinee znotraj odstavka
                    ctx.point_idx = 0
                    ctx.item_idx = 0

                    session.execute_write(
                        merge_paragraph,
                        dict(
                            parId=par_id,
                            order=ctx.paragraph_idx,
                            text=text,
                            aid=ctx.article_aid,
                            prevParId=prev,
                            projectName=PROJECT_NAME,
                        ),
                    )
                    continue

                # ŠTEVILČNA TOČKA (1.,2.,3...)
                if "stevilcna_tocka" in cls and ctx.last_par_id:
                    ctx.point_idx += 1
                    marker = str(ctx.point_idx) + "."
                    point_id = f"{ctx.last_par_id}.{ctx.point_idx}"
                    prev_point_id = f"{ctx.last_par_id}.{ctx.point_idx - 1}" if ctx.point_idx > 1 else None

                    session.execute_write(
                        merge_point,
                        dict(
                            pointId=point_id,
                            marker=marker,
                            order=ctx.point_idx,
                            text=text,
                            parId=ctx.last_par_id,
                            prevPointId=prev_point_id,
                            projectName=PROJECT_NAME,
                        ),
                    )
                    continue

                # ALINEJE (v HTML so razredi alinea/alinea_za_odstavkom ipd.)
                if (("alinea" in " ".join(cls)) or ("alinea_za_odstavkom" in cls)) and ctx.last_par_id:
                    ctx.item_idx += 1
                    item_id = f"{ctx.last_par_id}-alinea-{ctx.item_idx}"
                    session.execute_write(
                        merge_item,
                        dict(
                            itemId=item_id,
                            order=ctx.item_idx,
                            text=text.lstrip("-").strip(),
                            parId=ctx.last_par_id,
                            projectName=PROJECT_NAME,
                        ),
                    )
                    continue

            print(f"OK: uvoženo v Neo4j. versionId={version_id}, npb={npb}, effectiveFrom={effective}")

    finally:
        driver.close()


if __name__ == "__main__":
    parse_and_load(HTML_PATH)
