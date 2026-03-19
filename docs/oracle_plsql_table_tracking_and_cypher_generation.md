# Oracle PL/SQL Table Tracking and Cypher Generation Guide

Last updated: 2026-03-10

This guide focuses on two practical questions:

1. **How do I find which PL/SQL procedure/package/trigger inserts, updates, or deletes data in a given table?**
2. **Can an LLM such as GitHub Copilot generate Cypher for Oracle interactions from PL/SQL source, and how reliable is that?**

It also includes starter SQL for static analysis, runtime tracing, and auditing.

---

## 1. Which procedure changes a given table?

There is no single perfect source in Oracle. In practice, use a layered approach:

1. **Static dependency search** to find candidate objects.
2. **Source or PL/Scope analysis** to find likely DML statements.
3. **Runtime tracing or auditing** when you need proof of actual execution.

These techniques answer different questions:

- **Dependencies** = what an object *may* depend on.
- **PL/Scope / source search** = what the source code *appears* to do.
- **Trace / audit** = what *actually happened* at runtime.

Oracle documents that `ALL_DEPENDENCIES` and related views describe dependencies between procedures, packages, package bodies, functions, triggers, and other schema objects. citeturn0search0

### 1.1 Fast static starting point: dependencies

This finds PL/SQL objects that reference a table directly.

```sql
select owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
from   dba_dependencies
where  referenced_owner = upper('HR')
and    referenced_name  = upper('EMPLOYEES')
and    type in ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY','TRIGGER')
order by owner, type, name;
```

Use `ALL_DEPENDENCIES` if you do not have DBA access.

### What this gives you

A candidate list of objects that Oracle knows are related to the table.

### What it misses

- dynamic SQL
- SQL assembled in strings
- some indirect access patterns
- runtime-only paths
- synonym-based indirection in some scenarios

So this is a **candidate finder**, not proof.

---

## 1.2 Search the source for DML

After you get candidate objects, inspect the source for `INSERT`, `UPDATE`, `DELETE`, and `MERGE` against the target table.

```sql
select owner,
       name,
       type,
       line,
       text
from   dba_source
where  owner = upper('HR_APP')
and    type in ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY','TRIGGER')
and    upper(text) like '%EMPLOYEES%'
and   (
         upper(text) like '%INSERT%'
      or upper(text) like '%UPDATE%'
      or upper(text) like '%DELETE%'
      or upper(text) like '%MERGE%'
      )
order by owner, name, type, line;
```

This is simple and often useful, but it is still only text search.

### Better version: look for the table plus action words

```sql
select owner,
       name,
       type,
       line,
       text
from   dba_source
where  type in ('PROCEDURE','FUNCTION','PACKAGE','PACKAGE BODY','TRIGGER')
and    regexp_like(upper(text), '(INSERT|UPDATE|DELETE|MERGE)')
and    upper(text) like '%EMPLOYEES%'
order by owner, name, type, line;
```

### Limitations

- multi-line SQL may be split across lines
- aliases and line breaks complicate parsing
- false positives are possible
- dynamic SQL may not mention the table directly on the same line

---

## 1.3 Better static analysis: PL/Scope

PL/Scope is more structured than regex. Oracle documents that with `PLSCOPE_SETTINGS='STATEMENTS:ALL'`, PL/Scope collects SQL statement metadata for statement types including `SELECT`, `UPDATE`, `INSERT`, `DELETE`, `MERGE`, and `EXECUTE_IMMEDIATE`, exposed through views such as `USER_STATEMENTS` / `ALL_STATEMENTS` / `DBA_STATEMENTS`. citeturn0search0turn0search3

### Enable PL/Scope

For a session:

```sql
alter session set plscope_settings = 'IDENTIFIERS:ALL,STATEMENTS:ALL';
```

Then recompile the relevant package/procedure/trigger.

```sql
alter package hr_app.emp_pkg compile body;
alter procedure hr_app.load_employees compile;
```

### Inspect collected statements

```sql
select owner,
       object_name,
       object_type,
       line,
       col,
       type,
       sql_id,
       text
from   all_statements
where  owner = upper('HR_APP')
and    object_type in ('PROCEDURE','FUNCTION','PACKAGE BODY','TRIGGER')
and    type in ('INSERT','UPDATE','DELETE','MERGE','EXECUTE_IMMEDIATE')
order by owner, object_name, line, col;
```

Depending on Oracle version and privileges, column availability may differ slightly, so check your exact data dictionary definition first.

### Why PL/Scope is valuable

It gives you structured statement metadata instead of plain text search. It is especially useful for building Neo4j edges such as:

- `(:Procedure)-[:INSERTS_INTO]->(:Table)`
- `(:Procedure)-[:UPDATES]->(:Table)`
- `(:Procedure)-[:DELETES_FROM]->(:Table)`
- `(:Procedure)-[:USES_DYNAMIC_SQL]->(:Table)`

### Limitation

PL/Scope still does not prove that a statement actually ran in production.

---

## 1.4 Runtime proof: DBMS_TRACE / DBMS_HPROF

If your question is not just “which procedure might modify this table?” but “which procedure actually ran in this business flow?”, use runtime tracing.

Oracle documents that `DBMS_TRACE` starts and stops PL/SQL tracing in a session and writes collected trace data to database tables. citeturn0search1

Oracle documents that `DBMS_HPROF` profiles the execution of PL/SQL applications and collects hierarchical profiling data. citeturn0search10

### Practical meaning

- `DBMS_TRACE` is good for **call sequence**.
- `DBMS_HPROF` is good for **who called whom and where time was spent**.

### Sketch example with `DBMS_TRACE`

```sql
exec dbms_trace.set_plsql_trace(dbms_trace.trace_all_calls);

begin
  hr_app.run_end_of_day;
end;
/

exec dbms_trace.clear_plsql_trace;
```

Then query the trace tables installed for tracing in your environment.

### When to use this

Use it when:

- you need the true runtime call chain
- package bodies are complex
- dynamic SQL is involved
- the static analysis is ambiguous

---

## 1.5 “Put a watch on the table”: Unified Auditing

If you want to know **who touched the table**, that is an audit problem.

Oracle documents that `UNIFIED_AUDIT_TRAIL` contains unified audit records when unified auditing is enabled, and that unified audit policies can audit object actions. citeturn0search2turn0search5turn0search11

### Example policy

```sql
create audit policy pol_watch_employees
  actions insert, update, delete on hr.employees;

 audit policy pol_watch_employees;
```

### Read the audit trail

```sql
select event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       sql_text,
       return_code
from   unified_audit_trail
where  object_schema = 'HR'
and    object_name   = 'EMPLOYEES'
order by event_timestamp desc;
```

### What this answers well

- who changed the table
- when they changed it
- whether it succeeded or failed

### What it does **not** always answer cleanly

- the full PL/SQL call stack that led to the DML
- every internal subprogram hop

For that, combine auditing with tracing.

---

## 1.6 Best practical workflow for your first question

If you have a table and want to know which procedure changes it, the most dependable sequence is:

### Development / analysis workflow

1. Query `DBA_DEPENDENCIES` or `ALL_DEPENDENCIES` for candidate objects.
2. Search `DBA_SOURCE` or `ALL_SOURCE` for likely DML.
3. Enable PL/Scope and recompile important units.
4. Build a structured object-to-table interaction map.
5. Validate critical flows with `DBMS_TRACE` or `DBMS_HPROF`.

### Production / accountability workflow

1. Create a unified audit policy for the table.
2. Query `UNIFIED_AUDIT_TRAIL`.
3. Use trace/profiler in controlled test runs to reconstruct call chains.

### Conclusion for question 1

- **Static analysis** is good for building your graph.
- **PL/Scope** is better than raw regex.
- **Audit** tells you who touched the table.
- **Trace/profiler** tells you what actually ran.

No single one replaces the others.

---

## 2. Can GitHub Copilot or another LLM generate Cypher for PL/SQL interactions fairly well?

Yes, but only within limits.

## 2.1 Where an LLM usually does reasonably well

An LLM can often produce acceptable first-pass Cypher when the PL/SQL is:

- using straightforward static SQL
- consistently named
- organized into clear packages/procedures
- not heavily dynamic
- not spread across many layers of indirection

For example, it can often infer things like:

- package contains procedure
- procedure updates table
- procedure calls another procedure
- trigger writes to audit table

That is often good enough for an initial graph import.

---

## 2.2 Where LLM-only extraction becomes unreliable

An LLM becomes much less reliable when the PL/SQL uses:

- `EXECUTE IMMEDIATE`
- SQL assembled by string concatenation
- synonyms
- generated package names or owner indirection
- conditional logic that changes target tables
- overloaded subprograms
- triggers, jobs, queues, scheduler chains
- code spread across package spec, package body, triggers, and external jobs

In those cases, the model can still generate plausible Cypher, but plausibility is not the same as correctness.

---

## 2.3 Best workflow: do not ask the LLM to infer everything from raw code

The strongest approach is:

1. Extract facts from Oracle metadata and source first.
2. Normalize them into rows.
3. Ask the LLM to convert those rows into Cypher.

This is much more reliable than asking the LLM:

> “Here is a 5,000-line package body. Figure out all interactions.”

Instead, give it data like:

```text
OBJECT_OWNER | OBJECT_NAME     | OBJECT_TYPE   | ACTION | TARGET_OWNER | TARGET_NAME | TARGET_TYPE
HR_APP       | EMP_PKG         | PACKAGE BODY  | UPDATE | HR           | EMPLOYEES   | TABLE
HR_APP       | LOAD_EMP        | PROCEDURE     | INSERT | HR           | EMP_LOG     | TABLE
HR_APP       | EMP_TRG         | TRIGGER       | CALLS  | HR_APP       | EMP_AUDIT   | PROCEDURE
```

Then ask the LLM to generate Cypher. That usually works much better.

---

## 2.4 Recommended graph model for Oracle interactions

A useful starting Neo4j model is:

### Nodes

- `:Schema`
- `:Package`
- `:Procedure`
- `:Function`
- `:Trigger`
- `:Table`
- `:View`
- `:Sequence`
- `:Job`

### Relationships

- `(:Package)-[:CONTAINS]->(:Procedure)`
- `(:Procedure)-[:CALLS]->(:Procedure)`
- `(:Procedure)-[:SELECTS_FROM]->(:Table)`
- `(:Procedure)-[:INSERTS_INTO]->(:Table)`
- `(:Procedure)-[:UPDATES]->(:Table)`
- `(:Procedure)-[:DELETES_FROM]->(:Table)`
- `(:Trigger)-[:FIRES_ON]->(:Table)`
- `(:Trigger)-[:CALLS]->(:Procedure)`
- `(:Procedure)-[:USES_DYNAMIC_SQL]->(:Table)`
- `(:Procedure)-[:DEPENDS_ON]->(:View)`

For ambiguous cases, add a confidence or source property:

- `source: 'dependency' | 'plscope' | 'regex' | 'trace' | 'audit'`
- `confidence: 'high' | 'medium' | 'low'`

This is important because not all extracted interactions are equally strong.

---

## 2.5 Example: fact rows to Cypher

Suppose you extracted this row:

```text
owner=HR_APP
object_name=LOAD_EMPLOYEES
object_type=PROCEDURE
action=INSERT
target_owner=HR
target_name=EMPLOYEES
source=plscope
```

A suitable Cypher pattern is:

```cypher
MERGE (p:Procedure {owner:'HR_APP', name:'LOAD_EMPLOYEES'})
MERGE (t:Table {owner:'HR', name:'EMPLOYEES'})
MERGE (p)-[r:INSERTS_INTO]->(t)
SET r.source = 'plscope',
    r.confidence = 'high';
```

For runtime-confirmed facts:

```cypher
MERGE (p:Procedure {owner:'HR_APP', name:'RUN_END_OF_DAY'})
MERGE (q:Procedure {owner:'HR_APP', name:'LOAD_EMPLOYEES'})
MERGE (p)-[r:CALLS]->(q)
SET r.source = 'dbms_trace',
    r.confidence = 'high';
```

For regex-only guesses:

```cypher
MERGE (p:Procedure {owner:'HR_APP', name:'LOAD_EMPLOYEES'})
MERGE (t:Table {owner:'HR', name:'EMPLOYEES'})
MERGE (p)-[r:UPDATES]->(t)
SET r.source = 'regex',
    r.confidence = 'low';
```

---

## 2.6 Direct answer to question 2

**Will Copilot do a fair job?**

- **Yes**, for a first draft and for relatively clean static SQL.
- **No**, not as a sole source of truth for complex Oracle systems.

So the realistic answer is:

> Use the LLM as a Cypher generator and graph-model helper, not as your only extractor.

That is especially true in your case, where you want dependable Oracle-to-Neo4j interaction mapping.

---

## 3. Suggested extraction pipeline for your Oracle → Neo4j use case

A robust workflow looks like this:

### Phase A: static extraction

- object inventory from `ALL_OBJECTS` / `DBA_OBJECTS`
- dependencies from `ALL_DEPENDENCIES` / `DBA_DEPENDENCIES`
- source from `ALL_SOURCE` / `DBA_SOURCE`
- PL/Scope statements from `ALL_STATEMENTS` / `DBA_STATEMENTS`

### Phase B: optional runtime validation

- trace important flows with `DBMS_TRACE`
- profile call trees with `DBMS_HPROF`
- audit critical tables with Unified Auditing

### Phase C: normalization layer

Normalize everything into rows like:

```text
source_system | owner | object_name | object_type | action | target_owner | target_name | target_type | evidence_source | confidence
```

### Phase D: Cypher generation

Generate Cypher from normalized facts, not from raw code.

### Phase E: graph enrichment

Store metadata such as:

- line number
- statement type
- SQL text snippet
- audit timestamp
- traced session id
- job id / extraction run id

This will fit well with your existing graph-oriented approach.

---

## 4. Recommended answer in one paragraph

If you want to know which PL/SQL object changes a table, start with dependencies and source search, then use PL/Scope for structured static evidence, and use tracing or auditing when you need runtime proof. If you want an LLM to generate Cypher, it can do a fair first-pass job, but it becomes unreliable when dynamic SQL and indirection are involved. The safest design is to extract structured facts from Oracle first and only then let the LLM transform those facts into Cypher.

---

## 5. Official Oracle references used

- `ALL_STATEMENTS` / `USER_STATEMENTS`: PL/Scope statement metadata and supported statement types. citeturn0search0turn0search3
- `DBMS_TRACE`: start/stop PL/SQL tracing, trace written to database tables. citeturn0search1
- `UNIFIED_AUDIT_TRAIL`: unified audit records view. citeturn0search2
- `AUDIT` for unified auditing and audit policies. citeturn0search5turn0search11
- `DBMS_HPROF`: hierarchical profiler for PL/SQL execution. citeturn0search10

