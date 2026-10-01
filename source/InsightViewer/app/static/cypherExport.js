/* Export the last successful Cypher response without re-executing it. */
(function () {
    "use strict";

    let lastResult = null;
    let lastQuery = null;
    const nodeColumns = ["id", "label", "nodeType", "labels"];
    const edgeColumns = ["id", "from", "to", "type", "label"];

    function safeCell(value) {
        if (value === null || value === undefined) return "";
        if (typeof value === "number" || typeof value === "boolean") return value;
        const text = typeof value === "object" ? JSON.stringify(value) : String(value);
        // Do not let spreadsheet applications evaluate user-controlled values.
        return /^[\s\u0000-\u001f]*[=+\-@]/.test(text) ? "'" + text : text;
    }

    function nodeRows(items) {
        const properties = new Set();
        items.forEach(node => Object.keys(node.properties || {}).forEach(key => properties.add(key)));
        const columns = nodeColumns.concat(Array.from(properties).sort().map(key => "property." + key));
        const rows = items.map(node => columns.map(column => {
            if (column.startsWith("property.")) {
                return safeCell((node.properties || {})[column.slice(9)]);
            }
            return safeCell(node[column]);
        }));
        return [columns, ...rows];
    }

    function edgeRows(items) {
        return [edgeColumns, ...items.map(edge => edgeColumns.map(column => safeCell(edge[column])))];
    }

    function tableRows(result) {
        return [result.columns.map(safeCell),
            ...result.rows.map(row => result.columns.map((_, index) => safeCell(row[index])))];
    }

    function hasTable(result) {
        return Array.isArray(result.columns) && result.columns.length > 0 &&
            Array.isArray(result.rows) &&
            (result.hasScalarColumns || (!result.nodes.length && !result.edges.length));
    }

    function downloadCsv(name, sheet) {
        const csv = "\ufeff" + XLSX.utils.sheet_to_csv(sheet);
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = name;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    function setStatus(message) {
        const status = document.getElementById("cypher-export-status");
        if (status) status.textContent = message;
    }

    window.setCypherExportStatus = setStatus;

    window.setCypherExportResult = function (result, query) {
        lastResult = result && result.success !== false && Array.isArray(result.nodes) && Array.isArray(result.edges)
            ? result : null;
        lastQuery = lastResult && typeof query === "string" ? query : null;
        if (lastResult) setStatus(hasTable(lastResult)
            ? "Query columns ready to export as Rows. CSV downloads one file."
            : lastResult.nodes.length || lastResult.edges.length
                ? "Graph ready to export. CSV downloads two files (Nodes and Edges)."
                : "Query returned no exportable rows or graph data.");
    };

    window.exportCypherGraph = function (format) {
        if (format !== "csv" && format !== "xlsx") return;
        const currentInput = document.getElementById("cypher-input");
        if (lastResult && lastQuery !== null && currentInput && currentInput.value.trim() !== lastQuery) {
            lastResult = null;
            lastQuery = null;
        }
        if (!lastResult) {
            if (typeof window.runCypherQuery === "function") {
                setStatus("Running Cypher to prepare " + format.toUpperCase() + " export…");
                window.runCypherQuery(format);
            } else {
                alert("Cypher query runner is unavailable. Reload the page and try again.");
            }
            return;
        }
        const table = hasTable(lastResult);
        if (!table && !lastResult.nodes.length && !lastResult.edges.length) {
            alert("No data to export. Run a Cypher query returning properties, nodes, or relationships first.");
            return;
        }
        if (typeof XLSX === "undefined") {
            alert("Spreadsheet export library is unavailable.");
            return;
        }
        const now = new Date();
        const pad = n => String(n).padStart(2, "0");

        const basename = "cypher-result-" +
            now.getFullYear() +
            pad(now.getMonth() + 1) +
            pad(now.getDate()) +
            pad(now.getHours()) +
            pad(now.getMinutes()) +
            pad(now.getSeconds());
        if (table) {
            const rowsSheet = XLSX.utils.aoa_to_sheet(tableRows(lastResult));
            if (format === "csv") {
                downloadCsv(basename + "-rows.csv", rowsSheet);
                setStatus("Downloaded Rows CSV with the returned Cypher columns.");
            } else {
                const book = XLSX.utils.book_new();
                XLSX.utils.book_append_sheet(book, rowsSheet, "Rows");
                if (lastResult.nodes.length || lastResult.edges.length) {
                    XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet(nodeRows(lastResult.nodes)), "Nodes");
                    XLSX.utils.book_append_sheet(book, XLSX.utils.aoa_to_sheet(edgeRows(lastResult.edges)), "Edges");
                }
                XLSX.writeFile(book, basename + ".xlsx");
                setStatus("Downloaded XLSX with the returned Cypher columns.");
            }
            return;
        }
        const nodesSheet = XLSX.utils.aoa_to_sheet(nodeRows(lastResult.nodes));
        const edgesSheet = XLSX.utils.aoa_to_sheet(edgeRows(lastResult.edges));
        if (format === "csv") {
            downloadCsv(basename + "-nodes.csv", nodesSheet);
            downloadCsv(basename + "-edges.csv", edgesSheet);
            setStatus("Downloaded Nodes and Edges CSV files. If only one appeared, allow multiple downloads for this site.");
        } else if (format === "xlsx") {
            const book = XLSX.utils.book_new();
            XLSX.utils.book_append_sheet(book, nodesSheet, "Nodes");
            XLSX.utils.book_append_sheet(book, edgesSheet, "Edges");
            XLSX.writeFile(book, basename + ".xlsx");
            setStatus("Downloaded graph XLSX workbook.");
        }
    };

    const input = document.getElementById("cypher-input");
    if (input) input.addEventListener("input", () => {
        lastResult = null;
        lastQuery = null;
        setStatus("Query changed. Export will run the current Cypher.");
    });
})();
