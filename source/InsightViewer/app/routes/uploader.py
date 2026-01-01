# SPDX-License-Interier: AGPL-3.0-or-later
# Single-file drag‑and‑drop uploader blueprint

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
    url_for,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = "static/images"  # <-- make it relative, not /static/images

MAX_CONTENT_LENGTH = 512 * 1024 * 1024

ALLOWED_EXTENSIONS: set[str] = {
    "csv", "json", "txt", "xlsx", "xls", "tsv",
    "png", "jpg", "jpeg", "gif", "svg",
    "zip", "gz", "tar", "parquet", "pptx", "docx", "pkg", "sql", "mp3"
}

uploader_bp = Blueprint("uploader", __name__)


def _upload_dir() -> Path:
    """
    Return the base directory for uploads, under app/static/images.
    """
    # Always use app root + UPLOAD_FOLDER
    app_root = Path(current_app.root_path)
    p = app_root / UPLOAD_FOLDER
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


def sanitize_segment(segment: str | None, default: str) -> str:
    if not segment:
        return default
    cleaned = secure_filename(segment)
    return cleaned or default


@uploader_bp.route("/")
def index():
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
    .field { margin-bottom:12px; }
    .field label { display:block; margin-bottom:4px; font-size:0.9rem; color:var(--muted); }
    .field input[type="text"] { width:100%; padding:6px 8px; border-radius:6px; border:1px solid #374151; background:#020617; color:#e5e7eb; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>InsightViewer – File Upload</h1>

      <div class="field">
        <label for="finalSubdirectory">Dodatna podmapa:</label>
        <input type="text"
              id="finalSubdirectory"
              name="finalSubdirectory"
              value="anything"
              placeholder="npr. naloga1" />
      </div>

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

  fetch('/uploader/config')
    .then(r => r.json())
    .then(cfg => {
      const mb = (cfg.max_bytes / 1024 / 1024).toFixed(0);
      maxinfo.textContent =
        `Max upload size: ${mb} MB` +
        (cfg.allowed && cfg.allowed.length
          ? ` | Allowed: .${cfg.allowed.join(', .')}`
          : '');
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

    // directory metadata
    const finalSub = document.getElementById('finalSubdirectory').value.trim() || 'anything';
    const project = window.currentProject || localStorage.getItem('iv_project') || 'unknown_project';
    const email   = window.currentEmail   || localStorage.getItem('iv_email')   || 'unknown_user';

    form.append('project', project);
    form.append('email', email);
    form.append('finalSubdirectory', finalSub);

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
        """
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
    project = sanitize_segment(request.form.get("project"), "unknown_project")
    email = sanitize_segment(request.form.get("email"), "unknown_user")
    final_subdir = sanitize_segment(request.form.get("finalSubdirectory"), "ckeditor")    
    # --- CKEditor simple upload (field name 'upload') ---
    if "upload" in request.files:
        f = request.files["upload"]
        if not f or f.filename == "":
            abort(400, "No file uploaded.")
        if not allowed_file(f.filename):
            abort(415, f"File type not allowed: {f.filename}")

        # Read meta from form OR query string (for CKEditor uploads)
        project = sanitize_segment(
            request.form.get("project") or request.args.get("project"),
            "unknown_project",
        )
        email = sanitize_segment(
            request.form.get("email") or request.args.get("email"),
            "unknown_user",
        )
        final_subdir = sanitize_segment(
            request.form.get("finalSubdirectory") or request.args.get("finalSubdirectory"),
            "ckeditor",
        )

        base_upload_dir = _upload_dir()
        upload_dir = base_upload_dir / project / email / final_subdir
        upload_dir.mkdir(parents=True, exist_ok=True)

        final_name = uniquify_filename(f.filename)
        dest = upload_dir / final_name
        f.save(str(dest))

        # Try to build a static URL if under static root; otherwise /uploader/download/<rel-path>
        try:
            static_folder = Path(current_app.static_folder).resolve()
            rel_static = Path(dest).resolve().relative_to(static_folder)
            url = url_for(
                "static",
                filename=str(rel_static).replace(os.sep, "/"),
                _external=False,
            )
        except Exception:
            rel_from_root = dest.relative_to(base_upload_dir).as_posix()
            url = url_for(".download", filename=rel_from_root, _external=False)

        return jsonify(
            {
                "url": url,
                "filename": final_name,
                "project": project,
                "email": email,
                "finalSubdirectory": final_subdir,
            }
        ), 201

    # --- Multi-file / normal uploader (drag&drop UI) ---
    if "files" in request.files:
        files = request.files.getlist("files")
    elif request.files:
        files = list(request.files.values())
    else:
        abort(400, "No files part in the request.")

    project = sanitize_segment(request.form.get("project"), "unknown_project")
    email = sanitize_segment(request.form.get("email"), "unknown_user")
    final_subdir = sanitize_segment(request.form.get("finalSubdirectory"), "ckeditor")

    base_upload_dir = _upload_dir()
    upload_dir = base_upload_dir / project / email / final_subdir
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if f.filename == "":
            continue
        if not allowed_file(f.filename):
            abort(415, f"File type not allowed: f.filename")
        final_name = uniquify_filename(f.filename)
        dest = upload_dir / final_name
        f.save(str(dest))
        saved.append({"name": final_name, "size": dest.stat().st_size})

    return jsonify(
        {
            "url": url_for("uploader.download_file_scoped",
                           project=project,
                           email=email,
                           final_subdir=final_subdir,
                           filename=final_name),
            "filename": final_name,
            "project": project,
            "email": email,
            "finalSubdirectory": final_subdir,
        }
    ), 201



@uploader_bp.route("/files")
def list_files():
    items = []
    upload_dir = _upload_dir()

    # walk recursively and include relative path from upload_dir
    for p in sorted(upload_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(upload_dir)
            items.append({
                "name": str(rel).replace(os.sep, "/"),  # e.g. project/email/subdir/file.ext
                "size": p.stat().st_size,
            })
    return jsonify(items)


@uploader_bp.route("/download/<path:filename>")
def download(filename: str):
    """
    Download a file by relative path under the upload root.
    Example: bookZgodovina1/Egipt/listi_nil.jpg
    """
    upload_root = _upload_dir()

    # normalise and prevent path traversal
    rel_path = Path(filename)
    # remove any leading separators
    rel_path = Path(*[p for p in rel_path.parts if p not in ("", ".", "..")])

    abs_path = (upload_root / rel_path).resolve()

    # security: ensure the resolved path is still under upload_root
    if not str(abs_path).startswith(str(upload_root.resolve()) + os.sep):
        abort(400, "Invalid path")

    if not abs_path.exists() or not abs_path.is_file():
        abort(404)

    # send_from_directory needs directory + filename
    return send_from_directory(
        directory=str(abs_path.parent),
        path=abs_path.name,
        as_attachment=True,
    )

@uploader_bp.route("/view/<filename>")
def view_spreadsheet(filename):
    safe = secure_filename(filename)
    download_url = url_for(".download", filename=safe, _external=False)
    xlsx_url = url_for("static", filename="js/xlsx.full.min.js", _external=False)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe} - Spreadsheet viewer</title>
<style>
  body{{font-family:system-ui, Arial, sans-serif;margin:12px}}
  #xls-tabs button{{margin-right:6px;padding:6px 10px;border:1px solid #ddd;border-radius:6px;cursor:pointer;background:#f7f7f7}}
  #xls-container table{{border-collapse:collapse;width:100%}}
  #xls-container table td, #xls-container table th{{border:1px solid #ddd;padding:6px}}
</style>
</head>
<body>
  <h3>{safe}</h3>
  <div id="xls-tabs" style="margin-bottom:8px;"></div>
  <div id="xls-container"></div>

  <script src="{xlsx_url}"></script>
  <script>
  window.addEventListener('load', async () => {{
    if (typeof XLSX === 'undefined') {{
      console.error('XLSX library failed to load');
      document.getElementById('xls-container').textContent =
        'Failed to load XLSX library (SheetJS).';
      return;
    }}

    try {{
      const res = await fetch('{download_url}');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const buf = await res.arrayBuffer();
      const wb = XLSX.read(buf, {{ type: 'array' }});
      const tabs = document.getElementById('xls-tabs');
      const container = document.getElementById('xls-container');
      tabs.innerHTML = '';
      container.innerHTML = '';
      function renderSheet(name) {{
        const sheet = wb.Sheets[name];
        const html = XLSX.utils.sheet_to_html(sheet, {{ id: "excel-table", editable: false }});
        container.innerHTML = html;
      }}
      wb.SheetNames.forEach((name, idx) => {{
        const btn = document.createElement('button');
        btn.textContent = name;
        btn.addEventListener('click', () => renderSheet(name));
        tabs.appendChild(btn);
        if (idx === 0) renderSheet(name);
      }});
    }} catch (err) {{
      console.error(err);
      document.getElementById('xls-container').textContent =
        'Failed to load spreadsheet. Check the server.';
    }}
  }});
  </script>
</body>
</html>"""
    return render_template_string(html)


@uploader_bp.errorhandler(413)
def too_large(e):
    return ("File too large. Increase MAX_CONTENT_LENGTH on the server.", 413)


@uploader_bp.errorhandler(415)
def unsupported_type(e):
    return (str(e), 415)


@uploader_bp.route("/download/<project>/<email>/<final_subdir>/<path:filename>")
def download_file_scoped(project: str, email: str, final_subdir: str, filename: str):
    base_dir = _upload_dir()
    safe_project = sanitize_segment(project, "unknown_project")
    safe_email = sanitize_segment(email, "unknown_user")
    safe_sub = sanitize_segment(final_subdir, "ckeditor")

    directory = base_dir / safe_project / safe_email / safe_sub
    if not directory.exists():
        abort(404)

    return send_from_directory(directory, filename, as_attachment=True)

@uploader_bp.route("/download/<path:filename>")
def download_file(filename: str):
    """
    Serve a previously uploaded file by bare filename.
    NOTE: This ignores project/email/subdir and just scans flat under UPLOAD_FOLDER.
    """
    base_dir = _upload_dir()  # -> app/static/images
    # Walk subdirs to find the file by name
    for root, dirs, files in os.walk(base_dir):
        if filename in files:
            return send_from_directory(root, filename, as_attachment=True)

    abort(404, description=f"File {filename} not found")

@uploader_bp.route("/view/<project>/<email>/<final_subdir>/<path:filename>")
def view_file_scoped(project: str, email: str, final_subdir: str, filename: str):
    """
    Render an HTML spreadsheet viewer for a scoped file.
    The viewer JS fetches the binary from download_file_scoped.
    """
    base_dir = _upload_dir()
    safe_project = sanitize_segment(project, "unknown_project")
    safe_email = sanitize_segment(email, "unknown_user")
    safe_sub = sanitize_segment(final_subdir, "ckeditor")

    directory = base_dir / safe_project / safe_email / safe_sub
    if not directory.exists():
        abort(404, description=f"Dir not found: {directory}")

    file_path = directory / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404, description=f"File not found: {file_path}")

    safe_name = secure_filename(filename)

    # scoped download URL + SheetJS URL
    download_url = url_for(
        "uploader.download_file_scoped",
        project=safe_project,
        email=safe_email,
        final_subdir=safe_sub,
        filename=filename,
        _external=False,
    )
    xlsx_url = url_for("static", filename="js/xlsx.full.min.js", _external=False)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_name} - Spreadsheet viewer</title>
<style>
  body{{font-family:system-ui, Arial, sans-serif;margin:12px}}
  #xls-tabs button{{margin-right:6px;padding:6px 10px;border:1px solid #ddd;border-radius:6px;cursor:pointer;background:#f7f7f7}}
  #xls-container table{{border-collapse:collapse;width:100%}}
  #xls-container table td, #xls-container table th{{border:1px solid #ddd;padding:6px}}
</style>
</head>
<body>
  <h3>{safe_name}</h3>
  <div id="xls-tabs" style="margin-bottom:8px;"></div>
  <div id="xls-container"></div>

  <script src="{xlsx_url}"></script>
  <script>
  window.addEventListener('load', async () => {{
    if (typeof XLSX === 'undefined') {{
      console.error('XLSX library failed to load');
      document.getElementById('xls-container').textContent =
        'Failed to load XLSX library (SheetJS).';
      return;
    }}

    try {{
      const res = await fetch('{download_url}');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const buf = await res.arrayBuffer();
      const wb = XLSX.read(buf, {{ type: 'array' }});
      const tabs = document.getElementById('xls-tabs');
      const container = document.getElementById('xls-container');
      tabs.innerHTML = '';
      container.innerHTML = '';
      function renderSheet(name) {{
        const sheet = wb.Sheets[name];
        const html = XLSX.utils.sheet_to_html(sheet, {{ id: "excel-table", editable: false }});
        container.innerHTML = html;
      }}
      wb.SheetNames.forEach((name, idx) => {{
        const btn = document.createElement('button');
        btn.textContent = name;
        btn.addEventListener('click', () => renderSheet(name));
        tabs.appendChild(btn);
        if (idx === 0) renderSheet(name);
      }});
    }} catch (err) {{
      console.error(err);
      document.getElementById('xls-container').textContent =
        'Failed to load spreadsheet. Check the server.';
    }}
  }});
  </script>
</body>
</html>"""
    return render_template_string(html)
