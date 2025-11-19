// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

// filepath: /insight-viewer/insight-viewer/static/js/indexScript.js

function openHtmlEditorDialog() {
    document.getElementById('html-editor-dialog').style.display = 'block';
}

function closeHtmlEditorDialog() {
    document.getElementById('html-editor-dialog').style.display = 'none';
}

function saveHtmlFromEditor() {
    const htmlContent = document.getElementById('html-editor-textarea').value;
    // Implement saving logic here
}

function openAiSnippetDialog() {
    document.getElementById('ai-snippet-dialog').style.display = 'block';
}

function closeAiSnippetDialog() {
    document.getElementById('ai-snippet-dialog').style.display = 'none';
}

function previewEditorHtml() {
    const htmlContent = document.getElementById('html-editor-textarea').value;
    const iframe = document.getElementById('html-preview-iframe');
    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write(htmlContent);
    doc.close();
}

function loadTemplate() {
    fetch('/get_templates')
        .then(response => response.json())
        .then(data => {
            // Initialize Tabulator with the template data
            initializeTemplateTabulator(data);
            document.getElementById('choose-template-dialog').style.display = 'block';
        })
        .catch(error => console.error('Error loading templates:', error));
}

function initializeTemplateTabulator(data) {
    // Assuming Tabulator is already included and available
    const table = new Tabulator("#template-table", {
        data: data.templates,
        layout: "fitColumns",
        columns: [
            { title: "Name", field: "name", width: 150 },
            { title: "Description", field: "description", width: 300 },
            { title: "HTML File", field: "html_file", width: 150 }
        ],
        rowClick: function (e, row) {
            const selectedTemplate = row.getData();
            fetch(`/get_template_content/${selectedTemplate.html_file}`)
                .then(response => response.text())
                .then(htmlContent => {
                    document.getElementById('html-editor-textarea').value = htmlContent;
                    closeChooseTemplateDialog();
                })
                .catch(error => console.error('Error retrieving template content:', error));
        }
    });
}

function closeChooseTemplateDialog() {
    document.getElementById('choose-template-dialog').style.display = 'none';
}
