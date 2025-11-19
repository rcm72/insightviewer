// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

// This file contains the JavaScript code to initialize and manage the Tabulator table for displaying the templates.

document.addEventListener('DOMContentLoaded', function() {
    const tableData = [];
    const table = new Tabulator("#template-table", {
        height: "300px",
        data: tableData,
        layout: "fitColumns",
        columns: [
            { title: "Template Name", field: "name", width: 200 },
            { title: "File Name", field: "file", width: 200 },
            { title: "Description", field: "description", width: 300 },
            { title: "Action", field: "action", formatter: actionFormatter }
        ],
    });

    function actionFormatter(cell) {
        const templateData = cell.getRow().getData();
        return `<button onclick="loadTemplate('${templateData.file}')">Load</button>`;
    }

    window.loadTemplates = function() {
        fetch('/get_templates')
            .then(response => response.json())
            .then(data => {
                table.setData(data.templates);
            })
            .catch(error => console.error('Error fetching templates:', error));
    };

    window.loadTemplate = function(fileName) {
        fetch(`/get_template_content?file=${fileName}`)
            .then(response => response.text())
            .then(htmlContent => {
                const editor = document.getElementById('html-editor-textarea');
                editor.value = htmlContent;
                closeChooseTemplateDialog();
            })
            .catch(error => console.error('Error loading template:', error));
    };
});
