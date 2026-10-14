"""Neo4j operations for maintaining graph node-type metadata."""


def create_node_types(
    driver,
    *,
    project_name=None,
    created_by=None,
    color="#808080",
    shape="ellipse",
    size=25,
    url="url",
    global_scope=False,
):
    """Create or update NodeType metadata for labels used by a project or graph.

    Pass an initialized Neo4j driver from the calling application. The function
    returns the names of the node types found/created and does not own the
    driver's lifecycle. Set ``global_scope=True`` (or leave ``project_name``
    unset) to discover labels across projects and store them under a dedicated
    global scope, without using a null property in a MERGE pattern.
    """
    if driver is None:
        raise ValueError("A Neo4j driver is required")

    global_scope = global_scope or project_name is None
    node_filter = "TRUE" if global_scope else "n.projectName = $projectName"
    merge_properties = (
        "{name: label, scope: 'GLOBAL'}"
        if global_scope
        else "{name: label, projectName: $projectName}"
    )
    project_property = "" if global_scope else "nt.projectName = coalesce(nt.projectName, $projectName),"

    query = f"""
    MATCH (n)
    WHERE {node_filter}
      AND NOT n:NodeType
    UNWIND labels(n) AS label
    WITH DISTINCT label
    MERGE (nt:NodeType {merge_properties})
    SET {project_property}
        nt.id_rc = coalesce(nt.id_rc, randomUUID()),
        nt.shape = coalesce(nt.shape, $shape),
        nt.color = coalesce(nt.color, $color),
        nt.size = coalesce(nt.size, $size),
        nt.url = coalesce(nt.url, $url)
    FOREACH (_ IN CASE WHEN $createdBy IS NOT NULL THEN [1] ELSE [] END |
      SET nt.createdBy = coalesce(nt.createdBy, $createdBy)
    )
    RETURN nt.name;
    """
    with driver.session() as session:
        result = session.run(
            query,
            projectName=project_name,
            createdBy=created_by,
            color=color,
            shape=shape,
            size=size,
            url=url,
        )
        return [record["nt.name"] for record in result]
