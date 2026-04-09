# Neo4j Indexes – Practical Guide

## Overview

Neo4j provides several types of indexes, each optimized for different kinds of queries.

Understanding when to use each type is critical for performance and for building GraphRAG systems.

---

## 0) Usefull commands
```cypher
SHOW INDEXES;
SHOW CONSTRAINTS;

PROFILE MATCH (u:User)-[r:RATED]->(m:Movie)
WHERE r.rating >= 4
RETURN u.name, r.rating, m.title
```


## 1) Range Indexes (Default)

These are the most important and commonly used indexes.

### What they support
- Equality: `=`
- Comparisons: `<`, `>`, `<=`, `>=`
- Prefix search: `STARTS WITH`
- Sorting

### Example
```cypher
CREATE INDEX idx_page_id FOR (p:APEXPage) ON (p.pageId);
```

### When to use
- Exact lookups
- Joins (`MERGE`)
- Filtering by IDs, names, codes

### Typical usage in projects
- `LegacyApplication.name`
- `MigrationCase.name`
- `APEXPage.pageId`
- `OraclePackage.name`

---

## 2) Text Indexes

Used for simple string operations.

### What they support
- `CONTAINS`
- `STARTS WITH`
- `ENDS WITH`

### Example
```cypher
CREATE TEXT INDEX idx_proc_name FOR (p:OracleProcedure) ON (p.name);

CREATE TEXT INDEX Company_name_text IF NOT EXISTS FOR (x:Company) ON (x.name)
```

### When to use
- Partial name matching
- Simple string filtering

### Notes
- Faster than full-text for simple operations
- Does not provide ranking or linguistic analysis

---

## 3) Full-Text Indexes (Lucene-based)

Acts like a search engine inside Neo4j.

### Features
- Tokenization (splits text into words)
- Relevance scoring
- Works on large text fields

### Example
```cypher
CALL db.index.fulltext.createNodeIndex(
  "docIndex",
  ["DocumentChunk"],
  ["text"]
);

CREATE FULLTEXT INDEX ft_apex_ui IF NOT EXISTS
FOR (n:APEXPage|APEXRegion|APEXButton)
ON EACH [n.name, n.pageName, n.pageTitle, n.regionName, n.buttonName];
```

### Query
```cypher
CALL db.index.fulltext.queryNodes("docIndex", "reinsurance premium")
YIELD node, score
RETURN node, score;
```

### When to use
- Documentation search
- Code search
- Notes and descriptions

### Typical usage
- `PROCESS_SOURCE`
- Documentation nodes
- Meeting notes

---

## 4) Vector Indexes (AI / Embeddings)

Used for semantic similarity search.

### What they do
- Store embeddings (arrays of numbers)
- Find similar meaning using distance metrics

### Example
```cypher
CREATE VECTOR INDEX doc_embedding_index
FOR (n:DocumentChunk)
ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};
```

### Query
```cypher
CALL db.index.vector.queryNodes(
  'doc_embedding_index',
  5,
  $embedding
)
YIELD node, score
RETURN node, score;
```

### When to use
- Natural language queries
- Semantic similarity search
- RAG systems

### Example use cases
- "Which pages relate to reinsurance calculation?"
- Finding similar documentation with different wording

---

## 5) Lookup Indexes (Automatic)

Created automatically by Neo4j.

### Purpose
- Fast lookup of labels and relationship types

### Example
```cypher
SHOW INDEXES;
```

### Notes
- You do not manage these manually

---

## 6) Constraints (Related Concept)

Constraints enforce rules and automatically create indexes.

### Example
```cypher
CREATE CONSTRAINT unique_app_name
FOR (n:LegacyApplication)
REQUIRE n.name IS UNIQUE;
```

```cypher
CREATE CONSTRAINT <constraint_name> IF NOT EXISTS
FOR (x:<node_label>)
REQUIRE (x.<property_key1>, x.<property_key2>)  IS UNIQUE
```

### Purpose
- Ensure uniqueness
- Improve lookup performance

---

## How Index Types Fit Together

| Type        | Purpose                         |
|-------------|----------------------------------|
| Range       | Exact lookup                    |
| Text        | Simple string matching          |
| Full-text   | Keyword search + ranking        |
| Vector      | Semantic similarity             |
| Graph       | Relationships (not an index)    |

---

## Key Insight

Vector indexes do not replace other index types.

Best practice is to combine:

- Range indexes → fast graph navigation
- Full-text indexes → precise technical search
- Vector indexes → semantic entry point
- Graph traversal → actual answer construction

---

## Simple Decision Rule

Use:

- Exact value → Range index
- Substring → Text index
- Keywords in text → Full-text index
- Meaning / similarity → Vector index

---

## Recommended Approach

1. Start with constraints and range indexes
2. Add full-text indexes for documentation and code
3. Add vector indexes for embeddings
4. Combine all with graph traversal for GraphRAG

---

## Final Note

For complex systems (like APEX + PL/SQL graphs),
real value comes from combining:

- Structured graph relationships
- Text search
- Semantic similarity

Not from using any single index type alone.

