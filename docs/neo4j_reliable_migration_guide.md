# Neo4j Reliable Migration Guide (Schema + Data)

## Goal

Perform safe migrations between Neo4j environments while avoiding:

-   duplicate node errors
-   constraint conflicts
-   partial imports

------------------------------------------------------------------------

# Step 1 Export Constraints

    SHOW CONSTRAINTS;

Save results and recreate them later.

Example:

    CREATE CONSTRAINT FOR (n:Person) REQUIRE n.id IS UNIQUE;

------------------------------------------------------------------------

# Step 2 Export Indexes

    SHOW INDEXES;

Example:

    CREATE INDEX person_name FOR (n:Person) ON (n.name);

------------------------------------------------------------------------

# Step 3 Export Data

    CALL apoc.export.cypher.all(
    "data.cypher",
    {
    format:"cypher-shell",
    useOptimizations:{type:"UNWIND_BATCH", unwindBatchSize:1000}
    });

------------------------------------------------------------------------

# Step 4 Create New Database

Example (Neo4j Admin):

    CREATE DATABASE newdb;

------------------------------------------------------------------------

# Step 5 Create Constraints First

Run saved schema statements.

This prevents duplicate node creation.

------------------------------------------------------------------------

# Step 6 Import Data

    cypher-shell -u neo4j -p password -f data.cypher

------------------------------------------------------------------------

# Step 7 Verify Graph

    MATCH (n)
    RETURN labels(n), count(*)
    ORDER BY count(*) DESC;

Check relationships:

    MATCH ()-[r]->()
    RETURN type(r), count(*);

------------------------------------------------------------------------

# Recommended Migration Workflow

1 Export constraints\
2 Export indexes\
3 Export data\
4 Create new DB\
5 Create constraints\
6 Import data

------------------------------------------------------------------------

# Tips

-   Always export **schema first**
-   Always import **constraints before data**
-   Use **UNWIND batching** for large graphs
-   Test migration on staging before production
