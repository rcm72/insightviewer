# Parser-based package analysis for call graph and CRUD graph generation

## Short answer

Yes, using a parser makes sense.

For your use case, an ANTLR-based parser is a strong next step because your goal is not only to list dependencies, but to generate a reusable structural model for:

- relationship extraction
- call graph generation
- CRUD graph generation
- later impact analysis
- migration support
- graph import into Neo4j / InsightViewer

Your current Oracle-dictionary-based approach is still useful, but it has clear structural limits. The best long-term solution is not **parser instead of metadata**, but **parser plus metadata**.

---

## Why the current approach is useful but limited

Today you are combining views such as:

- `ALL_IDENTIFIERS`
- `ALL_SOURCE`
- `ALL_DEPENDENCIES`
- `ALL_PROCEDURES`
- `ALL_SYNONYMS`

That is a valid starting point and it is still worth keeping. It gives you:

- inventory of packages and procedures
- declared object names
- owner and package information
- synonym information
- source text lines
- a first pass for calls and CRUD references

But it also has important limits.

### Main limitations

#### 1. Line-based matching is fragile

A lot of SQL and PL/SQL is spread across multiple lines.  
If detection depends on:

- object name appearing on the same line
- DML keyword appearing on the same line
- simple regex matching

then you will miss or misclassify cases such as:

- multiline `SELECT`
- multiline `MERGE`
- `INSERT INTO ... SELECT ...`
- joins written across many lines
- aliases
- nested queries

#### 2. Dictionary metadata is not the same as code structure

The dictionary tells you that identifiers and dependencies exist, but not always:

- which exact procedure contains the statement
- whether a reference is a call or just a symbol occurrence
- what kind of statement a line belongs to
- what the enclosing syntax tree is

#### 3. It is hard to distinguish syntax roles

With line matching and metadata only, it is difficult to reliably distinguish:

- procedure call vs identifier reference
- table name vs variable name
- local procedure vs package procedure
- CRUD action vs passive mention of object name

#### 4. Dynamic and complex constructs become messy

Some constructs are hard to model using only Oracle metadata and line scanning:

- nested blocks
- cursor definitions
- package-qualified calls
- record and collection usage
- `EXECUTE IMMEDIATE`
- generated SQL
- strings that contain SQL fragments

---

## Why a parser helps

A parser gives you the actual code structure.

That means you no longer ask only:

> “Does this object name appear on this line?”

You can instead ask:

> “Inside which procedure am I? What statement is this? What objects does this statement reference? Is this a call, a select, an update, or something else?”

That is the key advantage.

### What a parser gives you

A parser can give you:

- procedure and function boundaries
- nested block structure
- exact statement types
- call expressions
- SQL statement structure
- better source location ranges
- better extraction confidence

### Why ANTLR is a good fit

ANTLR is suitable because it lets you:

- define or reuse a grammar
- produce parse trees / AST-like structures
- walk the parse tree with listeners or visitors
- build a normalized extraction model
- keep the parsing pipeline separate from Oracle and Neo4j concerns

That separation is useful for maintainability.

---

## Why this makes sense specifically for your project

Your goal is not just static analysis for its own sake.  
Your goal is to support migration understanding and graph-based exploration.

That is exactly where parser-based extraction becomes valuable.

You want to answer questions like:

- Which package procedure calls which other procedure?
- Which procedures update a given object?
- Which procedures only read from an object?
- Which DB objects are touched by a migration case?
- Which APEX process or button ultimately leads to which package and which CRUD operations?
- What is the dependency chain from UI element to database object?

These are graph questions.  
A parser gives you a much better source model for building those graphs.

---

## Where a parser is better than the current approach

## 1. Call graph generation

A parser is a strong fit for call graph generation.

You can extract:

- package-level procedures/functions
- local procedures/functions
- direct procedure calls
- package-qualified calls
- owner.package.procedure patterns
- source ranges for calls
- the enclosing procedure of each call

This is much more reliable than reconstructing calls from `ALL_IDENTIFIERS` alone.

## 2. CRUD graph generation

A parser is also a strong fit for CRUD extraction.

You can detect and classify:

- `SELECT`
- `INSERT`
- `UPDATE`
- `DELETE`
- `MERGE`

and tie each statement to:

- the enclosing procedure
- the referenced database object
- the source location
- possibly the exact SQL statement text

This is much stronger than line-based heuristics.

## 3. Statement-level model

A parser lets you build not only a procedure-level graph but also, if useful, a statement-level graph.

For example:

```cypher
(:OraclePackage)-[:HAS_PROCEDURE]->(:OracleProcedure)
(:OracleProcedure)-[:CALLS]->(:OracleProcedure)
(:OracleProcedure)-[:SELECTS_FROM]->(:ORADbObject)
(:OracleProcedure)-[:INSERTS_INTO]->(:ORADbObject)
(:OracleProcedure)-[:UPDATES]->(:ORADbObject)
(:OracleProcedure)-[:DELETES_FROM]->(:ORADbObject)
(:OracleProcedure)-[:MERGES_INTO]->(:ORADbObject)
(:OracleProcedure)-[:CONTAINS_STATEMENT]->(:SQLStatement)
(:SQLStatement)-[:USES_OBJECT]->(:ORADbObject)
```

That gives you two layers:

- a compact procedure-level dependency model
- a deeper statement-level explanation model

This fits very well with InsightViewer.

---

## Where a parser still has limits

Using a parser does not mean perfect semantic understanding.

There are still hard cases.

### 1. Dynamic SQL

Examples:

- `EXECUTE IMMEDIATE`
- SQL built by string concatenation
- runtime table names
- runtime predicates
- indirect code generation

A parser can usually detect that dynamic SQL exists, but not always resolve the actual runtime target.

### 2. Environment resolution is still needed

A parser sees syntax. It does not inherently know:

- whether an object is a table or view
- synonym resolution in your actual schema setup
- whether a referenced object really exists in the target environment
- cross-schema runtime behavior

This is why Oracle metadata should remain part of the pipeline.

### 3. Full PL/SQL is large

Trying to support all PL/SQL constructs from day one will make the project much bigger than needed.

That is why an incremental approach is better.

---

## Recommended strategy

The best approach is:

- use the parser for structure
- use Oracle metadata for enrichment and validation
- import normalized results into Neo4j

So the target architecture is:

**Parser + metadata + graph import**

not:

**Parser only**

---

## Recommended concrete architecture

## Layer 1. Source acquisition

### Purpose
Extract package body text and package metadata from Oracle.

### Inputs
- package owner
- package name
- package body source

### Sources
- `ALL_SOURCE`
- `ALL_OBJECTS`
- `ALL_PROCEDURES`
- other dictionary views as needed

### Output
Normalized source payload for parsing, for example:

```json
{
  "dbName": "MYDB",
  "packageOwner": "Y055490",
  "packageName": "PACK_RISKS_DUMMY",
  "objectType": "PACKAGE BODY",
  "sourceText": "create or replace package body ..."
}
```

### Notes
Keep this layer simple. Its job is just to extract the code and minimal metadata.

---

## Layer 2. Parsing

### Purpose
Parse PL/SQL source into a structured model.

### Technology
- ANTLR grammar for PL/SQL
- visitor or listener implementation
- your own extraction layer on top of parse tree events

### Core outputs
From each package body, extract:

- package name
- procedure/function declarations
- start/end line of each procedure
- calls between procedures
- SQL statements
- CRUD operations
- unresolved / ambiguous constructs
- dynamic SQL markers

### Example internal model

```json
{
  "packageOwner": "Y055490",
  "packageName": "PACK_RISKS_DUMMY",
  "procedures": [
    {
      "procedureName": "LOAD_DATA",
      "startLine": 120,
      "endLine": 210,
      "calls": [
        {
          "calledOwner": null,
          "calledPackage": "PKG_UTIL",
          "calledProcedure": "LOG_MESSAGE",
          "line": 145,
          "callText": "PKG_UTIL.LOG_MESSAGE(...)",
          "confidence": "HIGH"
        }
      ],
      "crud": [
        {
          "operation": "SELECT",
          "objectName": "RISKS",
          "line": 160,
          "statementText": "SELECT ... FROM RISKS ...",
          "confidence": "HIGH"
        },
        {
          "operation": "UPDATE",
          "objectName": "RISKS",
          "line": 175,
          "statementText": "UPDATE RISKS SET ...",
          "confidence": "HIGH"
        }
      ],
      "dynamicSql": [
        {
          "line": 190,
          "text": "EXECUTE IMMEDIATE lv_sql",
          "confidence": "LOW"
        }
      ]
    }
  ]
}
```

### Notes
Keep the parser output independent of Neo4j.  
It should describe code facts, not graph import details.

---

## Layer 3. Semantic enrichment

### Purpose
Resolve and enrich parser output using Oracle metadata.

### Inputs
- parser output
- Oracle dictionary metadata

### What this layer does
- resolve object owner where possible
- resolve synonyms where possible
- confirm that called procedure exists
- distinguish known object vs unresolved object
- optionally classify object type later
- add confidence or resolution status

### Example enrichment tasks
- `PKG_UTIL.LOG_MESSAGE` -> resolved to actual owner/package/procedure
- `RISKS` -> resolved to owner/object in schema
- synonym references -> replaced with base owner/object where possible
- unresolved objects -> flagged, not discarded

### Suggested fields
- `resolvedOwner`
- `resolvedPackage`
- `resolvedProcedure`
- `resolvedObjectName`
- `resolutionStatus`
- `confidence`

### Notes
This layer is where parser results become environment-aware.

---

## Layer 4. Normalized export

### Purpose
Produce stable JSON that is easy to import into Neo4j and easy to test.

### Suggested output groups
- packages
- procedures
- call relationships
- CRUD relationships
- unresolved references
- optional statement nodes

### Example export shape

```json
{
  "packages": [
    {
      "dbName": "MYDB",
      "owner": "Y055490",
      "packageName": "PACK_RISKS_DUMMY",
      "fullName": "MYDB.Y055490.PACK_RISKS_DUMMY"
    }
  ],
  "procedures": [
    {
      "dbName": "MYDB",
      "owner": "Y055490",
      "packageName": "PACK_RISKS_DUMMY",
      "procedureName": "LOAD_DATA",
      "fullName": "MYDB.Y055490.PACK_RISKS_DUMMY.LOAD_DATA",
      "startLine": 120,
      "endLine": 210
    }
  ],
  "calls": [
    {
      "sourceProcedure": "MYDB.Y055490.PACK_RISKS_DUMMY.LOAD_DATA",
      "targetProcedure": "MYDB.Y055490.PKG_UTIL.LOG_MESSAGE",
      "line": 145,
      "confidence": "HIGH"
    }
  ],
  "crud": [
    {
      "sourceProcedure": "MYDB.Y055490.PACK_RISKS_DUMMY.LOAD_DATA",
      "operation": "SELECT",
      "objectFullName": "MYDB.Y055490.RISKS",
      "line": 160,
      "confidence": "HIGH"
    },
    {
      "sourceProcedure": "MYDB.Y055490.PACK_RISKS_DUMMY.LOAD_DATA",
      "operation": "UPDATE",
      "objectFullName": "MYDB.Y055490.RISKS",
      "line": 175,
      "confidence": "HIGH"
    }
  ]
}
```

### Notes
This becomes your long-term contract between analysis and graph import.

---

## Layer 5. Neo4j import

### Purpose
Load normalized JSON into the graph.

### Suggested core node labels
- `OraclePackage`
- `OracleProcedure`
- `ORADbObject`

### Suggested core relationships
- `(:OraclePackage)-[:HAS_PROCEDURE]->(:OracleProcedure)`
- `(:OracleProcedure)-[:CALLS]->(:OracleProcedure)`
- `(:OracleProcedure)-[:SELECTS_FROM]->(:ORADbObject)`
- `(:OracleProcedure)-[:INSERTS_INTO]->(:ORADbObject)`
- `(:OracleProcedure)-[:UPDATES]->(:ORADbObject)`
- `(:OracleProcedure)-[:DELETES_FROM]->(:ORADbObject)`
- `(:OracleProcedure)-[:MERGES_INTO]->(:ORADbObject)`
- fallback: `(:OracleProcedure)-[:ACCESSES_DB_OBJECT]->(:ORADbObject)`

### Important implementation detail
When importing CRUD relationships, include a distinguishing property in the `MERGE`, for example:

```cypher
MERGE (srcPrc)-[r:UPDATES {sourceLine: row.sourceLine}]->(obj)
```

Otherwise multiple updates from the same procedure to the same object may collapse into a single relationship.

### Optional statement-level extension
If later you want explainability, add:

- `SQLStatement`
- `PLSQLCall`

and connect them to procedures and objects.

---

## Suggested end-to-end flow

```text
Oracle package source
    ->
Source extraction layer
    ->
ANTLR parser
    ->
Normalized code facts
    ->
Oracle metadata enrichment
    ->
Export JSON
    ->
Neo4j import
    ->
InsightViewer exploration
```

---

## Practical development phases

## Phase 1 — Minimal useful parser

Start with a narrow goal:

### Extract
- package name
- procedure/function boundaries
- direct procedure calls
- SQL statements:
  - SELECT
  - INSERT
  - UPDATE
  - DELETE
  - MERGE

### Ignore for now
- full dynamic SQL resolution
- every PL/SQL edge case
- statement-level graph explosion
- exact semantic resolution of every identifier

### Result
You get a first practical parser that already improves both:

- call graph
- CRUD graph

without making the project too big.

---

## Phase 2 — Better SQL and procedure resolution

Add:

- local procedure resolution
- package-qualified calls
- joins and subqueries
- cursor definitions
- sequence usage
- better source range capture
- confidence levels

### Result
Higher-quality graph and fewer false positives.

---

## Phase 3 — Ambiguous and dynamic constructs

Add heuristics for:

- `EXECUTE IMMEDIATE`
- SQL assembled from variables
- wrappers and helper procedures
- unresolved references
- confidence scoring and fallback relationships

### Result
More realistic handling of enterprise PL/SQL.

---

## Why this is a good fit for InsightViewer

This approach supports what InsightViewer is strongest at:

- dependency navigation
- visual graph exploration
- impact analysis
- combining code and business structure
- linking technical implementation to migration targets

It also fits your broader modernization scenario:

- Oracle Forms logic
- APEX targets
- package procedures
- database objects
- documentation
- migration cases

With this architecture, you can later connect:

- APEX buttons / processes
- package procedures
- CRUD operations
- DB objects
- migration cases
- documentation nodes

into one coherent graph.

---

## Recommendation summary

## I recommend this direction

Use ANTLR-based parsing, but do it incrementally.

### Keep Oracle metadata for:
- enrichment
- owner resolution
- synonym resolution
- validation
- object inventory

### Use the parser for:
- structure
- procedure boundaries
- call extraction
- CRUD extraction
- statement classification

### Export normalized JSON
This gives you a stable interface between analysis and import.

### Import into Neo4j with semantic relationships
Use:
- `CALLS`
- `SELECTS_FROM`
- `INSERTS_INTO`
- `UPDATES`
- `DELETES_FROM`
- `MERGES_INTO`
- fallback `ACCESSES_DB_OBJECT`

---

## Final conclusion

Yes, using a parser makes sense.

For your use case, it is probably the right long-term foundation because it moves you from:

- line matching
- dictionary heuristics
- partial reconstruction

toward:

- structural code understanding
- cleaner graph generation
- better explainability
- more reliable migration analysis

The strongest architecture is:

**Oracle source extraction -> ANTLR parse -> normalized JSON -> metadata enrichment -> Neo4j import**

That gives you a practical path forward without throwing away the work you have already done.



## Runtime tracing and profiling (execution-based approach)

There is also a fundamentally different approach to analyzing PL/SQL code that does **not rely on static parsing at all**.

Instead of analyzing what the code *could* do, you observe what the code *actually does during execution*.

Oracle provides built-in mechanisms for this, which can produce a call sequence or hierarchical execution trace when enabled before running a procedure.

This is likely what you previously saw.

---

### Relevant Oracle tools

Oracle includes several PL/SQL tracing and profiling packages.

#### DBMS_HPROF — PL/SQL Hierarchical Profiler

This is the most useful modern tool for understanding execution flow.

It collects a hierarchical execution profile showing:

- which subprograms were called  
- call relationships (caller → callee)  
- number of calls  
- execution time per subprogram  
- nested call structure  
- total and self time  

It effectively reconstructs a runtime call tree for one execution.

This is especially useful for:

- understanding real execution paths  
- performance analysis  
- identifying hotspots  
- validating static call graphs  

---

#### DBMS_TRACE — PL/SQL execution tracing

This package enables detailed tracing of PL/SQL execution, including:

- entry and exit of procedures/functions  
- exceptions  
- execution flow events  

It produces a detailed trace log rather than an aggregated profile.

This can be useful when you need fine-grained event sequencing.

---

#### DBMS_PROFILER — legacy profiler

An older profiler focused mainly on performance and coverage metrics.

It is generally less informative for structural analysis than DBMS_HPROF.

---

## Why this approach is fundamentally different

Runtime tracing answers a different question.

**Static analysis:**  
“What can this code possibly do?”

**Runtime tracing:**  
“What did this code actually do in this execution?”

Neither replaces the other.

---

## Strengths of runtime tracing

Runtime profiling and tracing are very strong for:

- real call sequences through nested procedures  
- dynamic SQL paths (which static analysis struggles with)  
- conditional branches actually taken  
- wrapper chains  
- indirect calls  
- performance hotspots  
- validation of assumptions about behavior  

It can reveal behavior that static analysis cannot reliably infer.

For example:

- dynamic SQL target objects  
- runtime parameter effects  
- feature toggles or configuration paths  
- exception-driven flow  
- calls through abstraction layers  

---

## Limitations of runtime tracing

The main limitation is coverage.

Tracing shows only what happened in a specific run.

It does **not produce a complete dependency graph** unless:

- many scenarios are executed  
- inputs cover all branches  
- rare paths are triggered intentionally  

Other limitations include:

- overhead during execution  
- need for controlled test scenarios  
- possible restrictions in production environments  
- difficulty aggregating traces across runs without additional processing  

---

## Best use for graph-based analysis

Runtime tracing is best used as a complement to static analysis, not a replacement.

A powerful combined approach is:

1. Build a **static graph** of all possible dependencies using parsing or heuristics.  
2. Execute selected scenarios with tracing enabled.  
3. Import runtime traces into the graph as evidence of actual behavior.  
4. Compare static possibilities with observed reality.  

This allows you to distinguish:

- potential dependencies  
- actual runtime usage  
- unused or dead code paths  
- scenario-specific flows  

---

## Suggested graph integration

Runtime traces can be modeled as separate relationship types, for example:

```cypher
(:OracleProcedure)-[:RUNTIME_CALLED]->(:OracleProcedure)
(:OracleProcedure)-[:RUNTIME_SELECTED_FROM]->(:ORADbObject)
(:OracleProcedure)-[:RUNTIME_UPDATED]->(:ORADbObject)