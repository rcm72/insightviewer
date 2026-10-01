const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const XLSX = require('../app/static/js/xlsx.full.min.js');

const source = fs.readFileSync(path.join(__dirname, '../app/static/cypherExport.js'), 'utf8');

function setup() {
    const downloads = [];
    const blobs = [];
    const status = { textContent: '' };
    const input = { value: 'MATCH (n) RETURN n', addEventListener(name, handler) { if (name === 'input') this.onInput = handler; } };
    const workbookFiles = [];
    const window = {};
    const context = {
        window,
        document: {
            getElementById: id => ({ 'cypher-export-status': status, 'cypher-input': input })[id],
            createElement: () => ({ click() { downloads.push(this.download); }, remove() {} }),
            body: { appendChild() {} },
        },
        XLSX: {
            utils: {
                aoa_to_sheet: rows => rows,
                sheet_to_csv: rows => rows.map(row => row.join(',')).join('\n'),
                book_new: () => ({ sheets: {} }),
                book_append_sheet: (book, sheet, name) => { book.sheets[name] = sheet; },
            },
            writeFile: (book, name) => workbookFiles.push({ book, name }),
        },
        URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
        Blob: class { constructor(content) { this.content = content; blobs.push(this); } },
        Date,
        setTimeout: () => {},
        alert: () => {},
    };
    vm.runInNewContext(source, context);
    return { window, input, status, downloads, blobs, workbookFiles };
}

test('exports only the latest Cypher result with property columns and safe text', () => {
    const { window, input, workbookFiles } = setup();
    window.setCypherExportResult({
        nodes: [{ id: 'n1', label: 'Task', nodeType: 'Task', labels: ['Task'],
            properties: { name: '=SUM(1,1)', dueDate: '2026-10-01', score: -3 } }],
        edges: [{ id: 'e1', from: 'n1', to: 'n2', type: 'ASSIGNED_TO', label: 'ASSIGNED_TO' }],
    });
    window.exportCypherGraph('xlsx');
    assert.match(workbookFiles[0].name, /\.xlsx$/);
    assert.deepEqual(Array.from(workbookFiles[0].book.sheets.Nodes[0]),
        ['id', 'label', 'nodeType', 'labels', 'property.dueDate', 'property.name', 'property.score']);
    assert.equal(workbookFiles[0].book.sheets.Nodes[1][5], "'=SUM(1,1)");
    assert.equal(workbookFiles[0].book.sheets.Nodes[1][6], -3);
    assert.equal(workbookFiles[0].book.sheets.Edges[1][3], 'ASSIGNED_TO');
    input.onInput();
    let rerun;
    window.runCypherQuery = format => { rerun = format; };
    window.exportCypherGraph('xlsx');
    assert.equal(rerun, 'xlsx');
    assert.equal(workbookFiles.length, 1);
});

test('CSV export downloads separate node and edge files', () => {
    const { window, downloads, blobs } = setup();
    window.setCypherExportResult({ nodes: [{ id: 'n1', properties: { title: '+cmd' } }], edges: [] });
    window.exportCypherGraph('csv');
    assert.equal(downloads.length, 2);
    assert.match(downloads[0], /-nodes\.csv$/);
    assert.match(downloads[1], /-edges\.csv$/);
    assert.match(blobs[0].content[0], /^\ufeff/);
    assert.match(blobs[0].content[0], /'\+cmd/);
});

test('explicit Cypher RETURN columns export as one table CSV even without graph entities', () => {
    const { window, input, downloads, blobs } = setup();
    input.value = 'MATCH (n) RETURN n.name AS name, n.amount AS amount, n.due AS due';
    window.setCypherExportResult({ success: true, nodes: [], edges: [],
        columns: ['name', 'amount', 'due'],
        rows: [['Alice, Jr.', 12, null], ['=EVIL()', 0, '2026-10-01']],
    }, input.value);
    window.exportCypherGraph('csv');
    assert.equal(downloads.length, 1);
    assert.match(downloads[0], /-rows\.csv$/);
    assert.match(blobs[0].content[0], /'=EVIL\(\)/);
});

test('explicit columns with no matches still export headers', () => {
    const { window, downloads, blobs } = setup();
    window.setCypherExportResult({ success: true, nodes: [], edges: [], columns: ['name'], rows: [] });
    window.exportCypherGraph('csv');
    assert.equal(downloads.length, 1);
    assert.match(blobs[0].content[0], /name/);
});

test('mixed node and projected-property results export Rows plus graph sheets in XLSX', () => {
    const { window, workbookFiles, downloads } = setup();
    window.setCypherExportResult({ success: true,
        columns: ['node', 'quantity', 'meta'],
        rows: [[{ id: 'n1', properties: { name: 'Alice' } }, 7, { category: 'A' }]],
        hasScalarColumns: true,
        nodes: [{ id: 'n1' }], edges: [],
    });
    window.exportCypherGraph('xlsx');
    assert.deepEqual(Object.keys(workbookFiles[0].book.sheets), ['Rows', 'Nodes', 'Edges']);
    assert.equal(workbookFiles[0].book.sheets.Rows[1][1], 7);
    assert.equal(workbookFiles[0].book.sheets.Rows[1][2], '{"category":"A"}');
    assert.equal(downloads.length, 0);
});

test('programmatically changed Cypher reruns before exporting old results', () => {
    const { window, input, downloads } = setup();
    window.setCypherExportResult({ nodes: [{ id: 'old' }], edges: [] }, input.value);
    input.value = 'MATCH (new) RETURN new';
    let requested;
    window.runCypherQuery = format => { requested = format; };
    window.exportCypherGraph('csv');
    assert.equal(requested, 'csv');
    assert.equal(downloads.length, 0);
});

test('empty and failed query results cannot be exported', () => {
    const { window, status, downloads, workbookFiles } = setup();
    window.setCypherExportResult({ success: true, nodes: [], edges: [] });
    assert.match(status.textContent, /no exportable rows or graph data/);
    window.exportCypherGraph('csv');
    assert.equal(downloads.length, 0);
    window.setCypherExportResult({ success: false, nodes: [{ id: 'n1' }], edges: [] });
    let requested;
    window.runCypherQuery = format => { requested = format; };
    window.exportCypherGraph('xlsx');
    assert.equal(requested, 'xlsx');
    assert.equal(workbookFiles.length, 0);
});

test('bundled SheetJS preserves safe cells and quoting in CSV output', () => {
    const captured = [];
    const context = {
        window: {},
        document: { getElementById: () => null },
        XLSX: { ...XLSX, writeFile: book => captured.push(book) },
        Date,
        alert: () => {},
    };
    vm.runInNewContext(source, context);
    context.window.setCypherExportResult({ nodes: [
        { id: 'n1', properties: { text: '=1+2, hello', count: 4 } },
    ], edges: [] });
    context.window.exportCypherGraph('xlsx');
    assert.equal(captured[0].Sheets.Nodes.F2.v, "'=1+2, hello");
    assert.equal(captured[0].Sheets.Nodes.E2.v, 4);
    assert.equal(captured[0].Sheets.Nodes.E2.t, 'n');
    assert.match(XLSX.utils.sheet_to_csv(captured[0].Sheets.Nodes), /"'=1\+2, hello"/);
});

test('bundled SheetJS writes explicit Cypher projections to a typed Rows sheet', () => {
    const books = [];
    const context = {
        window: {},
        document: { getElementById: () => null },
        XLSX: { ...XLSX, writeFile: book => books.push(book) },
        Date,
        alert: () => {},
    };
    vm.runInNewContext(source, context);
    context.window.setCypherExportResult({ success: true, nodes: [], edges: [],
        columns: ['name', 'count'], rows: [['=1+1', 5]], hasScalarColumns: true });
    context.window.exportCypherGraph('xlsx');
    assert.deepEqual(books[0].SheetNames, ['Rows']);
    assert.equal(books[0].Sheets.Rows.A2.v, "'=1+1");
    assert.equal(books[0].Sheets.Rows.B2.v, 5);
    assert.equal(books[0].Sheets.Rows.B2.t, 'n');
});
