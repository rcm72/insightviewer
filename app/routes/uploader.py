# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

#!/usr/bin/env python3
"""
InsightViewer – Single‑file drag‑and‑drop uploader

A compact Flask app that lets users upload files via drag‑and‑drop or a
traditional file picker. Designed to be dropped into your InsightViewer
stack and extended (e.g., pass uploaded files to Neo4j importers or your
Python processing pipeline).

• Drag & drop area + fallback file picker
• Multiple files, progress bars, cancel upload
• Server‑side size cap and extension whitelist
• Simple file browser to see what’s uploaded
• Unique, sanitized filenames

Run:
    pip install flask werkzeug
    python insightviewer_uploader.py

Then visit:
    http://127.0.0.1:5000/

Adjust config near the top (UPLOAD_FOLDER, ALLOWED_EXTENSIONS, MAX_CONTENT_LENGTH).
"""

from __future__ import annotations
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template_string,
    request,
    send_from_directory,
    abort,
)
from werkzeug.utils import secure_filename

# -----------------------------
# Config
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = "/static/images"

# Increase or decrease as needed (bytes). Example: 512 MB
MAX_CONTENT_LENGTH = 512 * 1024 * 1024

# Allow whatever your app needs; empty set means allow everything
ALLOWED_EXTENSIONS: set[str] = {
    "csv", "json", "txt", "xlsx", "xls", "tsv",
    "png", "jpg", "jpeg", "gif", "svg",
    "zip", "gz", "tar", "parquet","pptx", "docx","pkg","sql",'mp3'
}

uploader_bp = Blueprint("uploader", __name__)

# helper to resolve the upload folder at request time
def _upload_dir() -> Path:
    folder = current_app.config.get("UPLOAD_FOLDER")
    if not folder:
        # fallback to a local uploads folder next to this file
        fallback = BASE_DIR / "uploads"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    p = Path(folder)
    # if config holds a relative path, make it absolute relative to app root
    if not p.is_absolute():
        p = Path(current_app.root_path) / str(folder)
    p.mkdir(parents=True, exist_ok=True)
    return p


def allowed_file(filename: str) -> bool:
    if not ALLOWED_EXTENSIONS:
        return True
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def uniquify_filename(filename: str) -> str:
    name = secure_filename(Path(filename).stem) or "file"
    ext = Path(filename).suffix.lower()
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"{name}-{stamp}-{short}{ext}"


@uploader_bp.route("/")
def index():
    # Inline HTML/JS so this stays a single portable file.
    return render_template_string(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>InsightViewer – Upload</title>
  <style>
    :root { --bg:#0f172a; --card:#111827; --muted:#9ca3af; --accent:#22c55e; --warn:#ef4444; --ring:#60a5fa; }
    html,body { height:100%; background:var(--bg); color:white; font:16px system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif; }
    .wrap { max-width:900px; margin:24px auto; padding: 0 16px; }
    .card { background:var(--card); border-radius:16px; padding:20px; box-shadow: 0 10px 30px rgba(0,0,0,.25); }
    h1 { font-size:1.5rem; margin:0 0 12px; }
    .muted { color:var(--muted); }
    .dropzone { border:2px dashed #374151; border-radius:16px; padding:26px; text-align:center; transition: border-color .2s, background .2s; }
    .dropzone.dragover { border-color: var(--ring); background: rgba(96,165,250,.08); }
    .pick { margin-top:12px; }
    input[type=file] { display:none; }
    button,label.btn { background:#1f2937; color:white; border:1px solid #334155; padding:10px 14px; border-radius:12px; cursor:pointer; }
    button:hover,label.btn:hover { filter:brightness(1.1); }
    .row { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
    .filelist { margin-top:18px; display:grid; gap:8px; }
    .file { background:#0b1220; padding:12px; border-radius:12px; display:grid; grid-template-columns: 1fr 120px 90px; gap:10px; align-items:center; }
    .bar { height:8px; background:#111827; border-radius:6px; overflow:hidden; }
    .bar > div { height:100%; width:0%; background:var(--accent); transition: width .1s; }
    .err { color: var(--warn); }
    .browser { margin-top:20px; }
    a { color:#93c5fd; text-decoration:none; }
    a:hover { text-decoration:underline; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>InsightViewer – File Upload</h1>
      <p class="muted">Drag files here or pick from your device. Multiple files supported.</p>
      <div id="drop" class="dropzone">
        <strong>Drop files to upload</strong>
        <div class="pick">
          <label class="btn" for="picker">Choose files…</label>
          <input id="picker" type="file" multiple />
        </div>
      </div>

      <div id="list" class="filelist"></div>

      <div class="browser">
        <div class="row">
          <button id="refresh">Refresh uploaded files</button>
          <span class="muted" id="maxinfo"></span>
        </div>
        <div id="files"></div>
      </div>
    </div>
  </div>

<script>
(function(){
  const drop = document.getElementById('drop');
  const picker = document.getElementById('picker');
  const list = document.getElementById('list');
  const filesDiv = document.getElementById('files');
  const refreshBtn = document.getElementById('refresh');
  const maxinfo = document.getElementById('maxinfo');

  fetch('/uploader/config').then(r=>r.json()).then(cfg=>{
    const mb = (cfg.max_bytes/1024/1024).toFixed(0);
    maxinfo.textContent = `Max upload size: ${mb} MB` + (cfg.allowed && cfg.allowed.length ? ` | Allowed: .${cfg.allowed.join(', .')}`: '');
  });

  const stop = e => { e.preventDefault(); e.stopPropagation(); };
  ['dragenter','dragover','dragleave','drop'].forEach(ev => {
    drop.addEventListener(ev, stop, false);
  });
  ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, ()=> drop.classList.add('dragover')));
  ['dragleave','drop'].forEach(ev => drop.addEventListener(ev, ()=> drop.classList.remove('dragover')));

  drop.addEventListener('drop', (e)=> {
    handleFiles(e.dataTransfer.files);
  });
  picker.addEventListener('change', (e)=> handleFiles(e.target.files));

  function handleFiles(fileList){
    [...fileList].forEach(uploadFile);
  }

  function uploadFile(file){
    const row = document.createElement('div');
    row.className = 'file';
    row.innerHTML = `<div><strong>${file.name}</strong><div class="bar"><div></div></div><div class="err"></div></div><div class="muted">${(file.size/1024/1024).toFixed(2)} MB</div><div><button class="cancel">Cancel</button></div>`;
    list.prepend(row);
    const bar = row.querySelector('.bar > div');
    const err = row.querySelector('.err');
    const cancelBtn = row.querySelector('.cancel');

    const form = new FormData();
    form.append('files', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/uploader/upload');

    xhr.upload.addEventListener('progress', (e)=>{
      if (e.lengthComputable){
        const pct = ((e.loaded / e.total) * 100).toFixed(1);
        bar.style.width = pct + '%';
      }
    });

    cancelBtn.addEventListener('click', ()=> xhr.abort());

    xhr.onreadystatechange = function(){
      if (xhr.readyState === 4){
        if (xhr.status >= 200 && xhr.status < 300){
          bar.style.width = '100%';
          refreshFiles();
        } else {
          err.textContent = (xhr.response && xhr.responseText) ? xhr.responseText : `Upload failed (${xhr.status})`;
        }
      }
    };

    xhr.send(form);
  }

  function refreshFiles(){
    fetch('/uploader/files').then(r=>r.json()).then(items => {
      if (!Array.isArray(items)) return;
      filesDiv.innerHTML = '';
      if (items.length === 0){ filesDiv.innerHTML = '<p class="muted">No files uploaded yet.</p>'; return; }
      const ul = document.createElement('ul');
      items.forEach(it => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = `/uploader/download/${encodeURIComponent(it.name)}`;
        a.textContent = `${it.name} (${(it.size/1024).toFixed(1)} KB)`;
        li.appendChild(a);
        ul.appendChild(li);
      });
      filesDiv.appendChild(ul);
    });
  }

  refreshBtn.addEventListener('click', refreshFiles);
  refreshFiles();
})();
</script>
</body>
</html>
        """,
    )


@uploader_bp.route("/config")
def config():
    return jsonify(
        {
            "max_bytes": current_app.config.get("MAX_CONTENT_LENGTH", MAX_CONTENT_LENGTH),
            "allowed": sorted(ALLOWED_EXTENSIONS),
        }
    )


@uploader_bp.route("/upload", methods=["POST"])
def upload():
    # Accepts multiple files under the same field name ("files") or a single file
    files = []
    if "files" in request.files:
        # Can be many if sent as FormData with the same key
        files = request.files.getlist("files")
    elif request.files:
        # Fallback: any single file key
        files = list(request.files.values())

    if not files:
        abort(400, "No files part in the request.")

    saved = []
    upload_dir = _upload_dir()
    for f in files:
        if f.filename == "":
            continue
        if not allowed_file(f.filename):
            abort(415, f"File type not allowed: {f.filename}")
        final_name = uniquify_filename(f.filename)
        dest = upload_dir / final_name
        f.save(str(dest))
        saved.append({"name": final_name, "size": dest.stat().st_size})

    return jsonify({"ok": True, "files": saved})


@uploader_bp.route("/files")
def list_files():
    items = []
    upload_dir = _upload_dir()
    for p in sorted(upload_dir.glob("*")):
        if p.is_file():
            items.append({"name": p.name, "size": p.stat().st_size})
    return jsonify(items)


@uploader_bp.route("/download/<path:filename>")
def download(filename: str):
    # Security: only serve from the upload folder
    safe = secure_filename(Path(filename).name)
    upload_dir = _upload_dir()
    path = upload_dir / safe
    if not path.exists():
        abort(404)
    return send_from_directory(str(upload_dir), safe, as_attachment=True)


@uploader_bp.errorhandler(413)
def too_large(e):
    return ("File too large. Increase MAX_CONTENT_LENGTH on the server.", 413)


@uploader_bp.errorhandler(415)
def unsupported_type(e):
    return (str(e), 415)

# End of blueprint file
