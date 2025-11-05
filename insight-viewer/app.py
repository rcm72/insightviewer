# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

from flask import Flask, render_template, jsonify, send_from_directory
import os
import json

app = Flask(__name__)

TEMPLATES_DIR = 'templates_data/sample_templates'

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/templates')
def get_templates():
    templates = []
    for filename in os.listdir(TEMPLATES_DIR):
        if filename.endswith('.html'):
            template_name = filename[:-5]  # Remove .html extension
            template_description = f"This is a description for {template_name}."
            templates.append({
                'name': template_name,
                'file': filename,
                'description': template_description
            })
    return jsonify(templates)

@app.route('/template/<filename>')
def get_template(filename):
    return send_from_directory(TEMPLATES_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True)
