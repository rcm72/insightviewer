# InsightViewer as a Knowledge OS

## Purpose

This document describes a reference architecture for using InsightViewer not only as a graph viewer,
but as a Knowledge OS for Forms → APEX migration, onboarding, maintenance, and AI-assisted reasoning.

The architecture has five connected layers:

1. Source systems
2. Knowledge graph
3. Documentation and semantic layer
4. Retrieval and AI layer
5. Human workflows

---

## 1. What Knowledge OS means here

A Knowledge OS is not just a database of nodes and edges.

It is a working environment that lets you:

- capture technical structure
- capture migration decisions
- connect documentation to real system objects
- navigate legacy → target mappings
- support onboarding
- support impact analysis
- support AI question answering
- continuously enrich knowledge over time

InsightViewer becomes the place where system reality, migration work, and documentation meet.

---

## 2. Architectural layers

### 2.1 Source systems layer

This is where the raw truth comes from.

Legacy sources:
- Oracle Forms metadata
- PL/SQL packages and procedures
- Oracle tables and codebooks
- menu structures
- manual analysis by developers

Target sources:
- APEX metadata export
- button/process/DA analysis
- region/table mappings
- page definitions

Documentation sources:
- manually written HTML
- manually written Markdown
- meeting notes
- migration decisions
- troubleshooting notes

---

### 2.2 Core graph layer

This is the durable backbone of the system.

Legacy model:
- LegacyApplication
- OraForm
- OraBlock
- ORATable
- OraclePackage
- OracleProcedure

Migration model:
- MigrationCase

Target model:
- APEXApp
- APEXPage
- APEXRegion
- APEXButton
- APEXDynamicAction
- APEXDynamicActionStep

Documentation model:
- DocumentationHTML
- DocumentationMD
- Section
- Chunk

This graph is the long-term memory of the project.

---

### 2.3 Semantic documentation layer

This is where human-readable documentation becomes AI-usable knowledge.

HTML is best for:
- humans
- onboarding
- visual explanation
- rich structured documentation in InsightViewer

Markdown is best for:
- versioning
- chunking
- embeddings
- full-text search
- AI retrieval

Key principle:
HTML is the presentation layer.
Markdown is the semantic layer.

---

### 2.4 Retrieval and AI layer

This layer turns the graph and documentation into an intelligent assistant.

Full-text retrieval is best for:
- exact names
- package names
- page IDs
- button names
- table names
- codebook names

Vector retrieval is best for:
- semantic questions
- onboarding
- how does this work?
- where is similar logic?

Graph traversal is best for:
- impact analysis
- dependency expansion
- legacy to target navigation
- relationship-aware context building

GraphRAG flow:
1. Find candidates through full-text
2. Find candidates through vector search
3. Expand graph neighborhood
4. Rerank relevant chunks and nodes
5. Send focused context to the LLM

This produces better answers than plain vector search.

---

### 2.5 Human workflow layer

InsightViewer should support real work, not only storage.

Typical workflows:

Migration planning:
- identify forms inside an application
- create MigrationCase
- link source form
- track status and risk

Implementation tracking:
- connect MigrationCase to APEX pages/regions
- link to procedures and tables
- track missing pieces

Documentation authoring:
- store HTML doc for humans
- store MD doc for AI
- enrich as migration progresses

Onboarding:
- start from MigrationCase
- discover source form
- discover target page
- read explanations
- inspect dependencies

Maintenance:
- inspect shared tables
- inspect shared procedures
- find which pages depend on a process or codebook
- understand why something was implemented a certain way

---

## 3. Why MigrationCase is the center

MigrationCase is the most useful context node because it connects:

- business/domain application
- legacy form
- target APEX objects
- documentation
- technical dependencies
- progress and status

It is not the system artifact itself.
It is the context container for the work.

In practice, it acts as:
- work unit
- documentation anchor
- onboarding anchor
- AI query entry point

Default practice may be one form = one MigrationCase,
but the model should remain flexible.

---

## 4. Why id_rc matters

For InsightViewer, id_rc is the real technical primary identifier.

Why:
- stable in UI
- stable in exports/imports
- safe across environments
- independent of business meaning

Recommendation:
Every node should have:
- id_rc = randomUUID()
- projectName = 'APEX'

This makes the graph consistent and application-safe.

---

## 5. Why key still matters

Even though id_rc is primary for the app, key is still valuable.

Role of key:
- deterministic merge key
- logical identifier
- easier debugging
- easier import scripts
- stable cross-reference in docs

Practical rule:
- required / recommended for technical imported nodes
- optional for manual nodes created through vis.network

Examples:
- ORATable:REI_DB:RCM72:SIF_STATUS
- APEXPage:100:45
- APEXRegion:100:45:20

This is especially important for idempotent imports.

---

## 6. Shared codebooks and shared technical objects

Some objects belong to more than one application.

Examples:
- common status codebooks
- currencies
- common reference lists
- shared PL/SQL procedures

These should not be duplicated.

Recommended pattern:
Use the same node and connect multiple applications / forms / migration cases to it.

For tables:
- isCodebook = true means the table is reference data
- sharedAcrossApps = true means more than one application uses it

This enables true dependency analysis.

---

## 7. Recommended operating model

### 7.1 Manual first, enrichment later

Because the UI creates nodes generically through vis.network,
the architecture should support lightweight initial creation.

On initial manual create store at least:
- id_rc
- projectName
- name
- created_on
- updated_on

Later enrichment adds:
- key
- technical attributes
- links to target objects
- docs
- sections/chunks
- AI metadata

This fits the real workflow better than requiring all metadata up front.

---

### 7.2 Import pipelines

There should be import pipelines for:

APEX metadata:
- APEXApp
- APEXPage
- APEXRegion
- APEXButton
- APEXDynamicAction
- APEXDynamicActionStep

Oracle DB structure:
- ORATable
- OraclePackage
- OracleProcedure

Documentation parsing:
- DocumentationMD
- Section
- Chunk

Mapping pipelines:
- OraForm → APEXPage
- OraBlock → APEXRegion
- button → procedure
- region → table
- migrationcase → targets

---

## 8. Query patterns InsightViewer should support

Legacy to target:
- Which APEX page replaced this form?
- Which region corresponds to this block?

Impact analysis:
- Which applications use this shared table?
- Which migration cases call this procedure?

Documentation:
- Which docs belong to this MigrationCase?
- Which chunks describe this APEX page?

Onboarding:
- What is this migration about?
- What changed from Forms to APEX?
- Which business rules matter here?

AI:
- Find context around a page, procedure, or table
- Explain how a flow works
- Show related documentation and dependencies

---

## 9. Suggested roadmap

Phase 1:
- stabilize base schema
- enforce id_rc
- enforce projectName
- add indexes and constraints

Phase 2:
- enrich MigrationCase usage
- connect legacy to target mappings
- add HTML + MD documentation

Phase 3:
- parse Markdown into Section / Chunk
- add full-text indexes
- prepare vector storage

Phase 4:
- add GraphRAG retrieval
- add onboarding assistant
- add impact analysis views

Phase 5:
- evolve into multi-domain Knowledge OS
- Reinsurance, Commissions, and future applications share one architecture

---

## 10. Final recommendation

Treat InsightViewer as:
- a system map
- a migration workspace
- a documentation platform
- a dependency graph
- an AI context engine

The strongest long-term pattern is:

manual capture + automated imports + structured documentation + graph-based retrieval

That gives you a practical, maintainable, and AI-ready Knowledge OS.
