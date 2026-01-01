CREATE CONSTRAINT act_id IF NOT EXISTS
FOR (a:Act) REQUIRE a.actId IS UNIQUE;

CREATE CONSTRAINT version_id IF NOT EXISTS
FOR (v:ActVersion) REQUIRE v.versionId IS UNIQUE;

CREATE CONSTRAINT part_id IF NOT EXISTS
FOR (p:Part) REQUIRE p.pid IS UNIQUE;

CREATE CONSTRAINT chapter_id IF NOT EXISTS
FOR (c:Chapter) REQUIRE c.cid IS UNIQUE;

CREATE CONSTRAINT article_id IF NOT EXISTS
FOR (a:Article) REQUIRE a.aid IS UNIQUE;

CREATE CONSTRAINT paragraph_id IF NOT EXISTS
FOR (p:Paragraph) REQUIRE p.parId IS UNIQUE;

CREATE CONSTRAINT point_id IF NOT EXISTS
FOR (p:Point) REQUIRE p.pointId IS UNIQUE;

CREATE CONSTRAINT item_id IF NOT EXISTS
FOR (i:IndentItem) REQUIRE i.itemId IS UNIQUE;

CREATE CONSTRAINT section_id IF NOT EXISTS
FOR (s:Section) REQUIRE s.sid IS UNIQUE;

###################################

CREATE CONSTRAINT samplenode_id_rc_unique IF NOT EXISTS
FOR (n:SampleNode)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT act_id_rc_unique IF NOT EXISTS
FOR (n:Act)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT actversion_id_rc_unique IF NOT EXISTS
FOR (n:ActVersion)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT part_id_rc_unique IF NOT EXISTS
FOR (n:Part)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT chapter_id_rc_unique IF NOT EXISTS
FOR (n:Chapter)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT article_id_rc_unique IF NOT EXISTS
FOR (n:Article)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT paragraph_id_rc_unique IF NOT EXISTS
FOR (n:Paragraph)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT point_id_rc_unique IF NOT EXISTS
FOR (n:Point)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT indentitem_id_rc_unique IF NOT EXISTS
FOR (n:IndentItem)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT section_id_rc_unique IF NOT EXISTS
FOR (n:Section)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT rc_id_rc_unique IF NOT EXISTS
FOR (n:RC)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT reference_id_rc_unique IF NOT EXISTS
FOR (n:Reference)
REQUIRE n.id_rc IS UNIQUE;

CREATE CONSTRAINT chunk_id_rc_unique IF NOT EXISTS
FOR (n:Chunk)
REQUIRE n.id_rc IS UNIQUE;




CALL apoc.trigger.add(
  'requireProjectName',
  '
  UNWIND $createdNodes AS n
  WITH n WHERE n.projectName IS NULL
  CALL apoc.util.validate(true, "projectName is required", [])
  RETURN n
  ',
  {phase:"before"}
);


CREATE CONSTRAINT reference_refId IF NOT EXISTS
FOR (r:Reference) REQUIRE r.refId IS UNIQUE;


CREATE FULLTEXT INDEX text_search_index IF NOT EXISTS
FOR (n:Article|Paragraph|Chunk)
ON EACH [n.text];


CREATE FULLTEXT INDEX chunk_text_fts IF NOT EXISTS
FOR (c:Chunk) ON EACH [c.text];
