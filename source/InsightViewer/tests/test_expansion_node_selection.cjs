const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/static/indexScript.js'), 'utf8');
const dialogSource = source.slice(
    source.indexOf('function showNodeNameSelectionDialog('),
    source.indexOf('async function chooseExpansionTargets('),
);

function element(tagName) {
    return {
        tagName,
        children: [],
        attributes: {},
        handlers: {},
        style: { setProperty(name, value) { this[name] = value; } },
        value: '',
        hidden: false,
        append(...children) { this.children.push(...children); },
        appendChild(child) { this.children.push(child); },
        removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
        setAttribute(name, value) { this.attributes[name] = value; },
        addEventListener(name, handler) { this.handlers[name] = handler; },
    };
}

function descendants(root, tagName) {
    return root.children.flatMap(child => [
        ...(child.tagName === tagName ? [child] : []),
        ...descendants(child, tagName),
    ]);
}

function setup() {
    const document = { body: element('body'), createElement: element };
    const context = { document };
    vm.runInNewContext(dialogSource, context);
    const result = context.showNodeNameSelectionDialog([
        { id: '1', name: 'app.package.Alpha', textAfterLastDot: 'Alpha', nodeType: 'Class', edgeTypes: new Set(['CALLS']) },
        { id: '2', name: 'app.package.Beta', textAfterLastDot: 'Beta', nodeType: 'Function', edgeTypes: new Set(['USES']) },
    ]);
    const dialog = document.body.children[0];
    const table = descendants(dialog, 'table')[0];
    const rows = descendants(table, 'tbody')[0].children;
    const checkboxes = descendants(table, 'input');
    const filter = descendants(dialog, 'input').find(input => input.type === 'search');
    const button = text => descendants(dialog, 'button').find(item => item.textContent === text);
    return { document, dialog, table, rows, checkboxes, filter, button, result };
}

test('renders short and full names in separate table columns with associated selection labels', () => {
    const { table, rows, checkboxes } = setup();
    assert.deepEqual(descendants(table, 'th').map(cell => cell.textContent || ''), ['', 'Short name', 'Name']);
    assert.equal(rows[0].children.length, 3);
    assert.equal(rows[0].children[1].children[0].textContent, 'Alpha');
    assert.equal(rows[0].children[2].children[0].children[0].textContent, 'app.package.Alpha');
    assert.equal(rows[0].children[1].children[0].htmlFor, checkboxes[0].id);
    assert.equal(rows[0].children[2].children[0].htmlFor, checkboxes[0].id);
    assert.equal(rows[0].style.display, 'table-row');
    assert.equal(descendants(table, 'th')[1].scope, 'col');
});

test('filtering preserves table rows and displays an empty-state row spanning all columns', () => {
    const { filter, rows } = setup();
    filter.value = 'beta';
    filter.oninput();
    assert.equal(rows[0].hidden, true);
    assert.equal(rows[0].style.display, 'none');
    assert.equal(rows[1].style.display, 'table-row');
    filter.value = 'not-found';
    filter.oninput();
    assert.equal(rows[2].style.display, 'table-row');
    assert.equal(rows[2].children[0].colSpan, 3);
    filter.value = 'calls';
    filter.oninput();
    assert.equal(rows[0].style.display, 'table-row');
    assert.equal(rows[1].hidden, true);
    assert.equal(rows[2].style.display, 'none');
});

test('selection buttons affect only filtered rows and expansion returns the selected IDs', async () => {
    const { filter, button, checkboxes, document, result } = setup();
    button('Select none').handlers.click();
    assert.deepEqual(checkboxes.map(item => item.checked), [false, false]);
    filter.value = 'alpha';
    filter.oninput();
    button('Select all').handlers.click();
    assert.deepEqual(checkboxes.map(item => item.checked), [true, false]);
    filter.value = 'beta';
    filter.oninput();
    button('Select none').handlers.click();
    assert.deepEqual(checkboxes.map(item => item.checked), [true, false]);
    button('Expand selected').onclick();
    assert.deepEqual(Array.from(await result), ['1']);
    assert.equal(document.body.children.length, 0);
});

test('cancelling closes the dialog without selecting nodes', async () => {
    const { button, document, result } = setup();
    button('Cancel').onclick();
    assert.equal((await result).length, 0);
    assert.equal(document.body.children.length, 0);
});
