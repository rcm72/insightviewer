# InsightViewer Search Architecture

## Overview

InsightViewer uses a **dual search model**:

- **Global Graph Search (Discovery Mode)**
- **Node Context Search (Analysis Mode)**

This separates two different goals:

- **finding relevant parts of the graph**
- **understanding and exploring those parts**

---

## Core Concept

```text
Global Search → Result Graph → Node Selection → Node Search → Exploration
```

- Global search builds a **subgraph**
- User selects a node from that graph
- Node search provides **focused analysis**
- User expands graph visually in InsightViewer

---

## 1. Search Modes

## 1.1 Global Graph Search (Discovery Mode)

### Purpose
- Discover relevant nodes across the entire graph
- Build a **meaningful result subgraph**
- Provide entry points into the knowledge graph

### Output
- **Graph (subnetwork)**, not a list

### Typical Use Cases
- Find objects related to invoice generation
- Show procedures that write to table `NEOJ_INVOICES`
- Show path between node A and node B
- Find pages related to a package or table

### Recommended V1 Input Style
Use guided input instead of unrestricted chat:

- **question template**
- **node type**
- **node name**
- optional **target node type**
- optional **target node name**

Example templates:

- What is connected to this node?
- Which nodes of type X are connected to this node?
- Is there a direct link between A and B?
- What is the path between A and B?
- Which procedures write to table X?
- Which procedures call procedure Y?

---

## 1.2 Node Context Search (Analysis Mode)

### Purpose
- Deep analysis of a **selected node**
- Explain a node using graph structure and chunks
- Support focused LLM interaction

### Output
- explanation
- local subgraph expansion
- chunk summaries
- node-specific follow-up questions

### Typical Use Cases
- What does this procedure do?
- Which tables does this procedure write to?
- Explain this package
- Summarize this migration case
- What nearby nodes are important?

---

## 2. Design Principles

## 2.1 Separate Discovery and Analysis
- **Global mode** finds or builds a graph
- **Node mode** explains one selected part of the graph

## 2.2 Graph First, LLM Second
- Graph = source of truth
- LLM = explanation and orchestration layer

## 2.3 Use Controlled Queries
- Prefer **templates**
- Avoid unrestricted Cypher generation in early versions

## 2.4 Progressive Complexity
Start with:
- guided templates
- exact matching
- fulltext
- graph + chunk enrichment

Add later:
- vectors
- hybrid ranking
- LLM-assisted routing

## 2.5 User Guidance Improves Quality
Use:
- sample questions
- guided templates
- node type filters
- optional search mode override

---

## 3. Recommended Retrieval Strategy

## 3.1 Structural Questions
Use **Cypher templates**

Examples:
- Which procedures update table X?
- What calls procedure Y?
- Which pages use object Z?

## 3.2 Semantic Questions
Use **chunks linked to the selected object**

Examples:
- What does this procedure do?
- Explain this package
- Summarize this migration case

## 3.3 Mixed Questions
Use **Cypher first**, then enrich results with **chunks**

Examples:
- Which procedures update invoice tables and what do they do?
- Which pages are related to this package and what is their purpose?




## 4. Suggested Global Search Templates

These templates are suitable for a dropdown or guided form.

## 4.1 Single-Node Global Questions
- What is connected to this node?
- Show direct relationships of this node
- Show related nodes of type X
- Show procedure ↔ table relations for this node
- Summarize this node and its immediate neighbors

## 4.2 Two-Node Global Questions
- Is there a direct connection between A and B?
- Is there any path between A and B?
- How are A and B related?
- Show shortest path between A and B

## 4.3 Domain-Specific Global Questions
- Which procedures write to table X?
- Which procedures read from table X?
- Which procedures call procedure Y?
- Which pages are linked to package Z?
- Which pages are linked to table T?

---

## 5. Suggested Node Search Questions

These are good prompts when user is already on a node.

### For `OracleProcedure`
- What does this procedure do?
- Which tables does this procedure read?
- Which tables does this procedure write?
- What procedures call this one?
- What procedures are called by this one?
- Show chunks for this procedure

### For `OraclePackage`
- Summarize this package
- Which procedures belong to this package?
- Which pages are related to this package?
- Which tables are touched by procedures in this package?

### For `ORATable`
- Which procedures read from this table?
- Which procedures write to this table?
- Which pages are related to this table?
- What is the likely business role of this table?

### For `APEXPage`
- What is this page related to?
- Which tables are connected to this page?
- Which packages or procedures are related to this page?
- Summarize this page in business terms

---



## 6. Implementation Roadmap

### Phase 1
- guided global search with templates
- node search
- graph result rendering
- chunk retrieval for selected nodes
- feedback logging

### Phase 2
- fulltext search on node names
- fulltext search on chunk text
- result ranking
- better node summaries in result graph

### Phase 3
- vector search over chunks
- hybrid graph + semantic retrieval
- fuzzy thematic discovery

### Phase 4
- LLM-assisted routing
- natural language to template mapping
- adaptive suggestions based on past searches

---

## 7. Final Summary

InsightViewer search should be built around two complementary modes.

### Global Graph Search
- graph-wide discovery
- output is a **result subgraph**
- user finds relevant entry points visually

### Node Context Search
- focused analysis of a selected node
- uses graph relations and chunks
- supports LLM explanation

### Recommended Rule
- Use **global mode** to find or build the graph
- Use **node mode** to explain and expand a selected part of the graph

This gives a practical workflow:

```text
Search → Result Graph → Click Node → Explain / Expand / Ask
```

This architecture:
- uses Neo4j as the structural truth layer
- uses chunks as the semantic explanation layer
- avoids depending too early on unrestricted LLM Cypher generation
- allows gradual evolution toward fulltext, vectors, and hybrid retrieval
