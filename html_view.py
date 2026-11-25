#!/usr/bin/env python3
"""
Image Grid Viewer - 5x5 grid with selection, delete, and export functionality
Usage: python image_viewer.py
"""

import os
import json
import io
import zipfile
import mimetypes
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

class ImageViewerHandler(BaseHTTPRequestHandler):
    FOLDER_PATH = None
    
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.send_html()
        elif path == '/api/images':
            self.send_image_list()
        elif path == '/api/download-all':
            self.send_zip(all_files=True)
        elif path == '/api/download-selected':
            query = urllib.parse.parse_qs(parsed.query)
            names = query.get('names', [])
            # names may be a single comma-separated string
            if len(names) == 1 and ',' in names[0]:
                names = names[0].split(',')
            self.send_zip(files=names)
        elif path.startswith('/image/'):
            self.send_image(path[7:])
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/delete':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            self.delete_images(data.get('images', []))
        else:
            self.send_error(404)
    
    def send_html(self):
        html = get_html()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_image_list(self):
        folder = self.FOLDER_PATH
        extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif'}
        images = []
        if folder and os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if Path(f).suffix.lower() in extensions:
                    full = os.path.join(folder, f)
                    if os.path.isfile(full):
                        images.append({
                            'name': f,
                            'size': os.path.getsize(full)
                        })
        data = json.dumps({'folder': folder, 'images': images}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    
    def send_image(self, filename):
        filename = urllib.parse.unquote(filename)
        if '..' in filename or '/' in filename or '\\' in filename:
            self.send_error(403)
            return
        filepath = os.path.join(self.FOLDER_PATH, filename)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(filepath)
        with open(filepath, 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', mime or 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
    
    def send_zip(self, files=None, all_files=False):
        """Build a ZIP archive in memory and stream it back."""
        folder = self.FOLDER_PATH
        extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif'}
        
        if all_files:
            file_list = [f for f in sorted(os.listdir(folder))
                         if Path(f).suffix.lower() in extensions
                         and os.path.isfile(os.path.join(folder, f))]
            zip_name = 'images-all.zip'
        else:
            file_list = []
            for name in files:
                name = urllib.parse.unquote(name).strip()
                if not name:
                    continue
                if '..' in name or '/' in name or '\\' in name:
                    continue
                if os.path.isfile(os.path.join(folder, name)):
                    file_list.append(name)
            zip_name = 'images-selected.zip'
        
        if not file_list:
            self.send_error(404, 'No images to download')
            return
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for name in file_list:
                full = os.path.join(folder, name)
                zf.write(full, arcname=name)
        data = buf.getvalue()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', f'attachment; filename="{zip_name}"')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    
    def delete_images(self, filenames):
        folder = self.FOLDER_PATH
        deleted = []
        failed = []
        for name in filenames:
            if '..' in name or '/' in name or '\\' in name:
                failed.append(name)
                continue
            filepath = os.path.join(folder, name)
            try:
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted.append(name)
                else:
                    failed.append(name)
            except Exception:
                failed.append(name)
        result = json.dumps({'deleted': deleted, 'failed': failed}).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(result)))
        self.end_headers()
        self.wfile.write(result)
    
    def log_message(self, format, *args):
        pass


def get_html():
    return r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Image Grid Viewer</title>
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #1a1a1a;
        color: #eee;
        min-height: 100vh;
        padding-bottom: 80px;
    }
    .header {
        position: sticky;
        top: 0;
        z-index: 100;
        background: #2a2a2a;
        padding: 12px 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.5);
    }
    .header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        flex-wrap: wrap;
    }
    .header h1 { font-size: 18px; font-weight: 600; }
    .stats { font-size: 14px; color: #aaa; }
    .actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    button {
        padding: 10px 18px;
        border: none;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
        white-space: nowrap;
    }
    .btn-secondary { background: #444; color: #eee; }
    .btn-secondary:hover { background: #555; }
    .btn-export {
        background: #2e7d32;
        color: white;
    }
    .btn-export:hover { background: #388e3c; }
    .btn-export:disabled {
        background: #555;
        color: #888;
        cursor: not-allowed;
    }
    .btn-delete {
        background: #d32f2f;
        color: white;
    }
    .btn-delete:hover { background: #e53935; }
    .btn-delete:disabled {
        background: #555;
        color: #888;
        cursor: not-allowed;
    }
    .grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 10px;
        padding: 20px;
        max-width: 1800px;
        margin: 0 auto;
    }
    @media (max-width: 1200px) { .grid { grid-template-columns: repeat(4, 1fr); } }
    @media (max-width: 900px) { .grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 600px) { .grid { grid-template-columns: repeat(2, 1fr); } }

    .image-card {
        position: relative;
        background: #2a2a2a;
        border-radius: 10px;
        overflow: hidden;
        cursor: pointer;
        border: 3px solid transparent;
        transition: all 0.2s;
        aspect-ratio: 1;
    }
    .image-card:hover { border-color: #555; transform: scale(1.02); }
    .image-card.selected {
        border-color: #2196f3;
        box-shadow: 0 0 0 2px #2196f3, 0 0 20px rgba(33,150,243,0.4);
    }
    .image-card img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .image-card .checkmark {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: rgba(0,0,0,0.6);
        border: 2px solid #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: opacity 0.2s;
        color: #fff;
        font-size: 16px;
        font-weight: bold;
    }
    .image-card.selected .checkmark {
        opacity: 1;
        background: #2196f3;
        border-color: #2196f3;
    }
    .image-card .filename {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: linear-gradient(transparent, rgba(0,0,0,0.9));
        padding: 20px 8px 6px;
        font-size: 11px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        opacity: 0;
        transition: opacity 0.2s;
    }
    .image-card:hover .filename { opacity: 1; }
    .image-card.selected .filename { opacity: 1; }

    .empty {
        grid-column: 1 / -1;
        text-align: center;
        padding: 60px 20px;
        color: #666;
        font-size: 16px;
    }
    .toast {
        position: fixed;
        bottom: 30px;
        left: 50%;
        transform: translateX(-50%) translateY(100px);
        background: #333;
        color: #fff;
        padding: 14px 24px;
        border-radius: 10px;
        font-size: 14px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        transition: transform 0.3s;
        z-index: 1000;
    }
    .toast.show { transform: translateX(-50%) translateY(0); }
    .toast.success { background: #2e7d32; }
    .toast.error { background: #c62828; }
    .toast.info { background: #1565c0; }
</style>
</head>
<body>
<div class="header">
    <div class="header-row">
        <div>
            <h1>🖼️ Image Grid Viewer</h1>
            <div class="stats" id="stats">Loading...</div>
        </div>
        <div class="actions">
            <button class="btn-secondary" id="selectAllBtn" onclick="toggleSelectAll()">Select All</button>
            <button class="btn-export" id="exportAllBtn" onclick="exportAll()">⬇ Export All (ZIP)</button>
            <button class="btn-export" id="exportBtn" onclick="exportSelected()" disabled>⬇ Export Selected (0)</button>
            <button class="btn-delete" id="deleteBtn" onclick="deleteSelected()" disabled>Delete Selected (0)</button>
        </div>
    </div>
</div>
<div class="grid" id="grid">
    <div class="empty">Loading images...</div>
</div>
<div class="toast" id="toast"></div>

<script>
let allImages = [];
let selected = new Set();

async function loadImages() {
    try {
        const res = await fetch('/api/images');
        const data = await res.json();
        allImages = data.images;
        document.getElementById('stats').textContent =
            `${allImages.length} images in ${data.folder || 'folder'}`;
        renderGrid();
    } catch (e) {
        document.getElementById('stats').textContent = 'Error loading images';
        console.error(e);
    }
}

function renderGrid() {
    const grid = document.getElementById('grid');
    if (allImages.length === 0) {
        grid.innerHTML = '<div class="empty">No images found in this folder.</div>';
        updateControls();
        return;
    }
    grid.innerHTML = allImages.map(img => {
        const sel = selected.has(img.name);
        return `
            <div class="image-card ${sel ? 'selected' : ''}"
                 data-name="${escapeHtml(img.name)}"
                 onclick="toggleSelect('${escapeJs(img.name)}')">
                <img src="/image/${encodeURIComponent(img.name)}" loading="lazy" alt="">
                <div class="checkmark">✓</div>
                <div class="filename">${escapeHtml(img.name)}</div>
            </div>`;
    }).join('');
    updateControls();
}

function toggleSelect(name) {
    if (selected.has(name)) selected.delete(name);
    else selected.add(name);
    const card = document.querySelector(`.image-card[data-name="${cssEscape(name)}"]`);
    if (card) card.classList.toggle('selected', selected.has(name));
    updateControls();
}

function toggleSelectAll() {
    if (selected.size === allImages.length && allImages.length > 0) {
        selected.clear();
    } else {
        allImages.forEach(img => selected.add(img.name));
    }
    renderGrid();
}

function updateControls() {
    const deleteBtn = document.getElementById('deleteBtn');
    const exportBtn = document.getElementById('exportBtn');
    const allBtn = document.getElementById('selectAllBtn');
    const exportAllBtn = document.getElementById('exportAllBtn');
    
    deleteBtn.textContent = `Delete Selected (${selected.size})`;
    deleteBtn.disabled = selected.size === 0;
    exportBtn.textContent = `⬇ Export Selected (${selected.size})`;
    exportBtn.disabled = selected.size === 0;
    exportAllBtn.disabled = allImages.length === 0;
    allBtn.textContent = (selected.size === allImages.length && allImages.length > 0)
        ? 'Deselect All' : 'Select All';
}

function exportAll() {
    if (allImages.length === 0) return;
    showToast(`Packaging ${allImages.length} image(s)...`, 'info');
    // Use a hidden iframe/link so the browser handles the download dialog
    window.location.href = '/api/download-all';
    showToast('ZIP download started', 'success');
}

function exportSelected() {
    if (selected.size === 0) return;
    const names = Array.from(selected).join(',');
    showToast(`Packaging ${selected.size} image(s)...`, 'info');
    window.location.href = '/api/download-selected?names=' + encodeURIComponent(names);
    showToast('ZIP download started', 'success');
}

async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} image(s)? This cannot be undone.`)) return;
    const toDelete = Array.from(selected);
    try {
        const res = await fetch('/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({images: toDelete})
        });
        const data = await res.json();
        if (data.deleted.length > 0) {
            showToast(`Deleted ${data.deleted.length} image(s)`, 'success');
            selected.clear();
            await loadImages();
        }
        if (data.failed.length > 0) {
            showToast(`Failed to delete ${data.failed.length} image(s)`, 'error');
        }
    } catch (e) {
        showToast('Error deleting images', 'error');
        console.error(e);
    }
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show ' + (type || '');
    setTimeout(() => t.className = 'toast ' + (type || ''), 3000);
}

function escapeHtml(s) {
    return s.replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
}
function escapeJs(s) {
    return s.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}
function cssEscape(s) {
    return s.replace(/"/g, '\\"');
}

loadImages();
</script>
</body>
</html>'''


def main():
    default_path = "/Users/priyanshu/marrow convertor/pyq/_figures"
    print("=" * 60)
    print("  Image Grid Viewer - 5x5 with delete + export")
    print("=" * 60)
    folder = input(f"Enter folder path [default: {default_path}]: ").strip()
    if not folder:
        folder = default_path
    folder = os.path.expanduser(folder)
    
    if not os.path.isdir(folder):
        print(f"❌ Error: '{folder}' is not a valid directory.")
        return
    
    ImageViewerHandler.FOLDER_PATH = folder
    
    port = 8765
    print(f"\n✅ Serving images from: {folder}")
    print(f"🌐 Open your browser at: http://localhost:{port}")
    print("   Press Ctrl+C to stop the server.\n")
    
    server = HTTPServer(('127.0.0.1', port), ImageViewerHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
        server.shutdown()


if __name__ == '__main__':
    main()