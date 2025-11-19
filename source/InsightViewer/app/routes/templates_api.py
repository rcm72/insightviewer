# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

from flask import Blueprint, current_app, jsonify, request, abort, Response
from werkzeug.utils import secure_filename
import os
import re

bp = Blueprint('templates_api', __name__)

# Relative to Flask app.root_path
TEMPLATES_SUBDIR = os.path.join('templates', 'template_snippets')
ALLOWED_EXT = {'.html', '.htm', '.txt'}


def get_templates_dir():
    return os.path.join(current_app.root_path, TEMPLATES_SUBDIR)


@bp.route('/templates', methods=['GET'])
def list_templates():
    """
    Return JSON array of templates:
      [{ name, filename, description }, ...]
    """
    dirpath = get_templates_dir()
    if not os.path.isdir(dirpath):
        return jsonify([])

    out = []
    for fn in sorted(os.listdir(dirpath)):
        full = os.path.join(dirpath, fn)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ALLOWED_EXT:
            continue

        name = os.path.splitext(fn)[0].replace('_', ' ')
        description = ""
        try:
            with open(full, "r", encoding="utf-8") as fh:
                head = fh.read(512)
                # explicit name: <!-- name: Friendly Title -->
                m_name = re.search(r'<!--\s*name:\s*(.*?)\s*-->', head, re.I)
                if m_name:
                    name = m_name.group(1).strip()
                # explicit description: <!-- description: Short description -->
                m_desc = re.search(r'<!--\s*description:\s*(.*?)\s*-->', head, re.I)
                if m_desc:
                    description = m_desc.group(1).strip()[:200]
                else:
                    # fallback: first HTML comment (legacy)
                    m = re.search(r'<!--\s*([^>]+?)\s*-->', head)
                    if m:
                        description = m.group(1).strip()[:200]
        except Exception:
            description = ""

        out.append({"name": name, "filename": fn, "description": description})
    return jsonify(out)


@bp.route('/template', methods=['GET'])
def get_template():
    """
    Return raw template contents for a given filename (safe, no path-traversal).
    Query param: filename
    """
    filename = request.args.get('filename', '')
    if not filename:
        abort(400, "missing filename")

    # sanitize and reject if secure_filename changed it (simple guard)
    safe = secure_filename(filename)
    if not safe or safe != filename:
        abort(400, "invalid filename")

    dirpath = get_templates_dir()
    full = os.path.join(dirpath, safe)

    try:
        real_dir = os.path.realpath(dirpath)
        real_path = os.path.realpath(full)
        if not real_path.startswith(real_dir + os.sep):
            abort(403)
        if not os.path.isfile(real_path):
            abort(404)
        with open(real_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        return Response(content, mimetype="text/html; charset=utf-8")
    except Exception:
        abort(500)
