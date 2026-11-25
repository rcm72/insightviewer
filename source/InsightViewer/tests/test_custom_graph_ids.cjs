const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/static/indexScript.js'), 'utf8');
const submitSource = source.slice(source.indexOf('async function submitNode('), source.indexOf('function submitEdge('));
const saveSource = source.slice(source.indexOf('function saveCustomGraph('), source.indexOf('//Function to load graph previously saved'));

function setup(visualProperties = { id_rc: 'shared-type-id', description: 'Default description' }) {
    const records = [];
    const saves = [];
    const errors = [];
    const fields = {
        'node-type-selector': { value: 'Demo.Person' },
        'node-name': { value: 'Alice' },
        'node-image-url': { value: '' },
    };
    let nextId = 0;
    const context = {
        document: { getElementById: id => fields[id] },
        window: { currentCallback() {} },
        console: { log() {}, error(...args) { errors.push(args); } },
        alert() {},
        createNodeCurrentShape: 'ellipse',
        gCustomGraphName: 'Demo graph',
        getNodeTypeProperties: async () => ({}),
        refreshGraph() {},
        nodeIdToNameMap: new Map(),
        nodes: { add(record) { records.push(record); }, get() { return records; } },
        network: { getPositions: () => ({}) },
        fetch: async (url, options) => {
            let body;
            if (url === '/add-node') {
                body = { success: true, node_id: `node-${++nextId}`, labels: ['Demo.Person'] };
            } else if (url === '/nodes/get_node_type_visuals') {
                body = { success: true, shape: 'ellipse', properties: visualProperties };
            } else if (url === '/nodes/connect-custom-graph-position') {
                saves.push(JSON.parse(options.body));
                body = { success: true };
            } else {
                throw new Error(`Unexpected request: ${url}`);
            }
            return { json: async () => body };
        },
    };
    vm.createContext(context);
    vm.runInContext(`${submitSource}\n${saveSource}`, context);
    const add = async name => {
        fields['node-name'].value = name;
        await context.submitNode();
        // submitNode starts a nested fetch chain without returning it.
        await new Promise(resolve => setImmediate(resolve));
        assert.deepEqual(errors, []);
    };
    return { context, records, saves, add, visualProperties };
}

test('new nodes retain their own IDs rather than copying the node type ID', async () => {
    const { records, add, visualProperties } = setup();
    await add('Alice');
    await add('Bob');

    assert.equal(records.length, 2);
    assert.notEqual(records[0].id, records[1].id);
    for (const record of records) {
        assert.equal(record.id_rc, record.id);
        assert.equal(record.properties.id_rc, record.id);
        assert.equal(record.properties.name, record.label);
        assert.equal(record.properties.description, 'Default description');
    }
    assert.equal(visualProperties.id_rc, 'shared-type-id');
});

test('new nodes get explicit id_rc even when no visual properties are returned', async () => {
    const { records, add } = setup(null);
    await add('Alice');
    assert.equal(records[0].id_rc, 'node-1');
    assert.equal(records[0].properties.id_rc, 'node-1');
});

test('saving a custom graph sends the original node IDs, not the shared type ID', async () => {
    const { context, records, saves, add } = setup();
    await add('Alice');
    await add('Bob');
    context.saveCustomGraph();

    assert.equal(saves.length, 1);
    assert.deepEqual(saves[0].nodes.map(node => node.id), records.map(node => node.id));
    assert.deepEqual(saves[0].nodes.map(node => node.properties.id_rc), ['node-1', 'node-2']);
});
