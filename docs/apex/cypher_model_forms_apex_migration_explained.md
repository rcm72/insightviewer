# Cypher Model — Forms → APEX Migration (InsightViewer, Explained)

## Purpose

This document defines the recommended Neo4j schema (labels, relationships, constraints)
for managing Oracle Forms → APEX migrations in InsightViewer.

It also explains WHY each part exists, not only HOW to implement it.

The model supports:

- Multiple legacy applications
- Form‑by‑form migration
- Flexible mapping scenarios
- Shared codebooks (lookup tables)
- Documentation for humans and AI
- Future GraphRAG integration

---

## Design Philosophy

The schema separates three concerns:

1. System reality (legacy + target)
2. Migration process
3. Knowledge & documentation

MigrationCase is the central bridge between them.

---

## Constraints

Constraints guarantee identity and prevent duplicates.

```cypher
CREATE CONSTRAINT legacy_app_name_unique IF NOT EXISTS
FOR (n:LegacyApplication)
REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT migrationcase_key_unique IF NOT EXISTS
FOR (n:MigrationCase)
REQUIRE n.key IS UNIQUE;

CREATE CONSTRAINT documentation_html_key_unique IF NOT EXISTS
FOR (n:DocumentationHTML)
REQUIRE n.key IS UNIQUE;

CREATE CONSTRAINT documentation_md_key_unique IF NOT EXISTS
FOR (n:DocumentationMD)
REQUIRE n.key IS UNIQUE;

CREATE CONSTRAINT section_key_unique IF NOT EXISTS
FOR (n:Section)
REQUIRE n.key IS UNIQUE;

CREATE CONSTRAINT chunk_key_unique IF NOT EXISTS
FOR (n:Chunk)
REQUIRE n.key IS UNIQUE;
```

### Why these constraints matter

- Prevent duplicate nodes during imports
- Enable MERGE‑based idempotent scripts
- Support stable references for AI indexing

---

## Core Legacy Structure

```cypher
(:LegacyApplication {name})
(:OraForm {name})
(:OraBlock {name})
(:ORATable {name})
```

### Meaning

- LegacyApplication — business domain (Reinsurance, Commissions…)
- OraForm — individual Oracle Forms form
- OraBlock — UI/data block inside a form
- ORATable — database table (including lookup tables)

---

## Example — Create Application and Form

```cypher
MERGE (app:LegacyApplication {name:'Reinsurance'})

MERGE (f:OraForm {name:'Vmesniki_pozavarovanja'})
MERGE (app)-[:HAS_FORM]->(f);
```

### Explanation

- MERGE ensures repeatable execution
- HAS_FORM expresses structural ownership
- Forms belong to exactly one legacy application

---

## MigrationCase — Migration Unit

```cypher
(:MigrationCase {key})
```

MigrationCase represents the migration work itself.

Typical rule:

> One form → one migration case (but not enforced).

---

## Example — Create MigrationCase

```cypher
MATCH (app:LegacyApplication {name:'Reinsurance'})
MATCH (f:OraForm {name:'Vmesniki_pozavarovanja'})

MERGE (mc:MigrationCase {key:'MC:Vmesniki_pozavarovanja'})
ON CREATE SET
  mc.name = 'Migration Vmesniki_pozavarovanja',
  mc.status = 'in_progress',
  mc.module = 'Reinsurance',
  mc.started_on = date(),
  mc.updated_on = datetime()

MERGE (mc)-[:BELONGS_TO_APP]->(app)
MERGE (mc)-[:SOURCE_FORM]->(f);
```

### Explanation

- BELONGS_TO_APP → contextual grouping
- SOURCE_FORM → what is being migrated
- Properties store process metadata

MigrationCase is NOT a system artifact — it represents work.

---

## Target Mapping (APEX)

```cypher
(:APEXApp)
(:APEXPage)
(:APEXRegion)
```

These nodes usually come from automated APEX metadata extraction.

### Permanent Mapping

```cypher
(OraForm)-[:MIGRATED_TO]->(APEXPage)
(OraBlock)-[:MIGRATED_TO]->(APEXRegion)
```

This expresses system evolution, not migration process.

---

## Mapping MigrationCase → Target

```cypher
MATCH (mc:MigrationCase {key:'MC:Vmesniki_pozavarovanja'})
MATCH (pg:APEXPage {applicationId:100, pageId:45})

MERGE (mc)-[:TARGETS]->(pg);
```

### Why this exists

- Tracks scope of the migration work
- Enables progress reporting
- Supports impact analysis

---

## Documentation Nodes

```cypher
(:DocumentationHTML {key})
(:DocumentationMD {key})
```

Two complementary formats:

- HTML → human‑friendly
- Markdown → AI‑friendly

### Example

```cypher
MATCH (mc:MigrationCase {key:'MC:Vmesniki_pozavarovanja'})

MERGE (html:DocumentationHTML {key:'HTML:Vmesniki_pozavarovanja'})
MERGE (md:DocumentationMD {key:'MD:Vmesniki_pozavarovanja'})

MERGE (mc)-[:HAS_HTML_DOC]->(html)
MERGE (mc)-[:HAS_MD_DOC]->(md);
```

---

## Shared Codebook Tables

Codebooks are lookup/reference tables.

Modeled as ORATable with flags.

```cypher
MERGE (t:ORATable {name:'SIF_STATUS'})
SET t.isCodebook = true,
    t.sharedAcrossApps = true;
```

### Why flags instead of new label

- Simpler schema
- Same entity type (table)
- Flexible querying
- Avoids schema explosion

---

## Linking Shared Tables

```cypher
MATCH (app:LegacyApplication {name:'Reinsurance'})
MERGE (app)-[:USES_TABLE]->(t);

MATCH (mc:MigrationCase {key:'MC:Vmesniki_pozavarovanja'})
MERGE (mc)-[:USES_TABLE]->(t);
```

This enables cross‑application impact analysis.

---

## AI Layer — Section & Chunk

```cypher
(:Section {key})
(:Chunk {key})
```

Derived from Markdown documentation.

### Create Section

```cypher
MATCH (md:DocumentationMD {key:'MD:Vmesniki_pozavarovanja'})

MERGE (s:Section {key:'SEC:Overview'})
SET s.title = 'Overview'

MERGE (md)-[:HAS_SECTION]->(s);
```

### Create Chunk

```cypher
MERGE (c:Chunk {key:'CHK:Overview:001'})
SET c.content = 'Description of the form...'

MERGE (s)-[:HAS_CHUNK]->(c);
```

---

## Linking Chunks to System Objects

```cypher
MATCH (f:OraForm {name:'Vmesniki_pozavarovanja'})
MERGE (c)-[:REFERS_TO]->(f);
```

Optional links:

- DESCRIBES → target objects
- REFERS_TO → legacy objects

---

## Relationship Summary

LegacyApplication —HAS_FORM→ OraForm  
MigrationCase —BELONGS_TO_APP→ LegacyApplication  
MigrationCase —SOURCE_FORM→ OraForm  
MigrationCase —HAS_HTML_DOC→ DocumentationHTML  
MigrationCase —HAS_MD_DOC→ DocumentationMD  
MigrationCase —TARGETS→ APEXPage / APEXRegion  
OraForm —MIGRATED_TO→ APEXPage  
OraBlock —MIGRATED_TO→ APEXRegion  
LegacyApplication —USES_TABLE→ ORATable  
MigrationCase —USES_TABLE→ ORATable  
DocumentationMD —HAS_SECTION→ Section  
Section —HAS_CHUNK→ Chunk  
Chunk —REFERS_TO→ OraForm  
Chunk —DESCRIBES→ APEX objects  

---

## Recommended Query Entry Point

MigrationCase is the best starting node for:

- migration status queries
- onboarding explanations
- AI retrieval context
- documentation navigation

