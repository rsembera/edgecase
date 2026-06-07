"""
EdgeCase Desktop - Native desktop app wrapper using PyWebView
Packages the Flask app as a standalone desktop application.
Works on macOS and Linux.
"""

import os
import sys
import threading
import time
import socket
import shutil
import subprocess
import tempfile
import platform
from pathlib import Path

# Set desktop mode before importing app
os.environ['EDGECASE_DESKTOP'] = '1'

# Per-run private directory for files opened in external viewers (set up
# lazily by _get_viewer_dir).
_viewer_dir = None


def _get_viewer_dir():
    """Get (creating on first use) the private temp dir for opened files.

    Files handed to an external viewer (Preview, etc.) contain decrypted
    PHI, so they must not live in the shared, world-readable system temp
    dir. They also must outlive the open_file call — the viewer reads the
    file lazily and may keep it open — so we can't delete them right after
    launching the viewer. Tradeoff: files persist for this run inside a
    0700 per-user directory and are deleted on the NEXT launch, by wiping
    and recreating the fixed parent directory below.
    """
    global _viewer_dir
    if _viewer_dir is not None:
        return _viewer_dir

    # Fixed per-user parent dir: wiped and recreated at each launch so
    # files from previous runs are cleaned up best-effort.
    parent = Path(tempfile.gettempdir()) / f'edgecase-viewer-{os.getuid()}'
    shutil.rmtree(parent, ignore_errors=True)
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(parent, 0o700)  # enforce mode even if rmtree partially failed

    # Per-run subdirectory with a randomized name (mkdtemp creates it 0700)
    _viewer_dir = Path(tempfile.mkdtemp(prefix='edgecase-', dir=parent))
    return _viewer_dir


def get_data_dir():
    """Get platform-appropriate data directory."""
    if platform.system() == 'Darwin':
        return Path.home() / 'Library' / 'Application Support' / 'EdgeCase'
    else:
        # Linux: use XDG_DATA_HOME or ~/.local/share
        xdg_data = os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))
        return Path(xdg_data) / 'edgecase'


def open_with_default_app(filepath):
    """Open file with system default application."""
    if platform.system() == 'Darwin':
        subprocess.run(['open', str(filepath)], check=False)
    else:
        # Linux: use xdg-open
        subprocess.run(['xdg-open', str(filepath)], check=False)


def _is_edgecase_responding(port, timeout=2.0):
    """Check whether an EdgeCase server is already answering on this port."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(
            f'http://127.0.0.1:{port}/api/heartbeat', timeout=timeout
        ) as resp:
            return resp.status == 200 and json.loads(resp.read().decode()).get('ok') is True
    except Exception:
        return False


def _pick_port(preferred=8080):
    """Pick a port for the local server.

    Tries the preferred port first; if it's taken by another EdgeCase
    instance, exits with a clear message instead of opening a dead page.
    If it's taken by something else, falls back to an ephemeral port.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', preferred))
        return preferred
    except OSError:
        pass

    # Preferred port is busy — is it us?
    if _is_edgecase_responding(preferred):
        print(
            "EdgeCase is already running. Close the existing window "
            "before starting it again.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Something else owns the port; let the OS hand us a free one.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _wait_for_server(port, timeout=15.0):
    """Poll the server until it responds (or the timeout elapses)."""
    import urllib.request
    deadline = time.monotonic() + timeout
    url = f'http://127.0.0.1:{port}/api/heartbeat'
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def start_flask_server(port=8080):
    """Start Flask server in background thread."""
    from web.app import app
    from waitress import serve
    import logging
    
    # Suppress logging
    logging.getLogger('waitress').setLevel(logging.ERROR)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    
    # Run server (blocks in this thread)
    serve(app, host='127.0.0.1', port=port, _quiet=True)


class Api:
    """JavaScript API for communication between webview and Python."""
    
    def __init__(self, port):
        self.port = port
    
    def open_file(self, url):
        """Download file and open in default system application."""
        import requests
        try:
            full_url = f'http://localhost:{self.port}{url}'
            response = requests.get(full_url)
            
            if response.status_code == 200:
                filename = self._get_filename(response, url)
                # Randomized subdir (0700) inside the private viewer dir;
                # keeps the user-visible filename while making the full
                # path unpredictable. Cleaned up on next app launch — see
                # _get_viewer_dir for why we don't delete immediately.
                file_dir = Path(tempfile.mkdtemp(dir=_get_viewer_dir()))
                temp_path = file_dir / filename
                temp_path.write_bytes(response.content)
                os.chmod(temp_path, 0o600)
                open_with_default_app(temp_path)
                return True
        except Exception as e:
            print(f"File open error: {e}")
        return False
    
    def download_file(self, url):
        """Download file to user's Downloads folder. Returns filename on success."""
        import requests
        try:
            full_url = f'http://localhost:{self.port}{url}'
            response = requests.get(full_url)
            
            if response.status_code == 200:
                filename = self._get_filename(response, url)
                downloads_path = Path.home() / 'Downloads' / filename
                
                # Handle duplicate filenames
                if downloads_path.exists():
                    base = downloads_path.stem
                    ext = downloads_path.suffix
                    counter = 1
                    while downloads_path.exists():
                        downloads_path = Path.home() / 'Downloads' / f"{base} ({counter}){ext}"
                        counter += 1
                
                downloads_path.write_bytes(response.content)
                print(f"Downloaded to: {downloads_path}")
                return downloads_path.name
        except Exception as e:
            print(f"Download error: {e}")
        return None
    
    def _get_filename(self, response, url):
        """Extract filename from response headers or URL."""
        filename = 'document'
        if 'Content-Disposition' in response.headers:
            cd = response.headers['Content-Disposition']
            if 'filename=' in cd:
                filename = cd.split('filename=')[1].strip('"').strip("'")
        elif '/' in url:
            url_filename = url.split('/')[-1].split('?')[0]
            if url_filename:
                filename = url_filename
        return filename
    
    def open_pdf(self, url):
        """Download PDF and open in default viewer (legacy method)."""
        return self.open_file(url)
    
    def open_external_url(self, url):
        """Open any URL (including mailto:) with system default handler."""
        try:
            open_with_default_app(url)
            return True
        except Exception as e:
            print(f"Error opening URL: {e}")
            return False



def run_desktop():
    """Main entry point for desktop app."""
    import webview
    
    # Prefer 8080; fall back to an ephemeral port if it's taken, and bail
    # out early if another EdgeCase instance already owns it.
    PORT = _pick_port(8080)
    api = Api(PORT)

    # Clean up viewer temp files from previous runs and set up this run's
    # private directory (see _get_viewer_dir).
    _get_viewer_dir()

    # Start Flask in background thread
    server_thread = threading.Thread(
        target=start_flask_server,
        args=(PORT,),
        daemon=True
    )
    server_thread.start()

    # Wait until the server actually responds before loading the webview.
    if not _wait_for_server(PORT, timeout=15.0):
        print(
            f"EdgeCase failed to start: the local server on port {PORT} "
            "did not respond within 15 seconds.",
            file=sys.stderr,
        )
        sys.exit(1)


    # Create window
    window = webview.create_window(
        'EdgeCase Equalizer',
        f'http://localhost:{PORT}',
        width=1280,
        height=800,
        min_size=(1100, 700),
        js_api=api
    )
    
    def on_closing():
        """Run backup when window is closed (if logged in)."""
        try:
            from web.app import app
            from web.cli import _run_shutdown_backup
            
            with app.app_context():
                db = app.config.get('db')
                if db:
                    print("Running shutdown backup...")
                    _run_shutdown_backup(db, label="Window Close")
                    db.close()
                    app.config['db'] = None
                    print("Backup complete.")
        except Exception as e:
            print(f"Shutdown backup error: {e}")
    
    # Register close handler
    window.events.closing += on_closing
    
    # Start webview with persistent storage
    # private_mode=False enables persistent localStorage/cookies between sessions
    # storage_path ensures consistent storage location
    storage_dir = str(get_data_dir() / 'webview')
    Path(storage_dir).mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=storage_dir)
    
    print("EdgeCase closed.")
    sys.exit(0)


if __name__ == '__main__':
    run_desktop()
