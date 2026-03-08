"""
EdgeCase Desktop - Native macOS app wrapper using PyWebView
Packages the Flask app as a standalone desktop application.
"""

import os
import sys
import threading
import time
import subprocess
import tempfile
from pathlib import Path

# Set desktop mode before importing app
os.environ['EDGECASE_DESKTOP'] = '1'


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
                temp_path = Path(tempfile.gettempdir()) / filename
                temp_path.write_bytes(response.content)
                subprocess.run(['open', str(temp_path)], check=False)
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
        """Download PDF and open in Preview (legacy method)."""
        return self.open_file(url)


def run_desktop():
    """Main entry point for desktop app."""
    import webview
    
    PORT = 8080
    api = Api(PORT)
    
    # Start Flask in background thread
    server_thread = threading.Thread(
        target=start_flask_server,
        args=(PORT,),
        daemon=True
    )
    server_thread.start()
    time.sleep(1.5)
    
    # Create window
    window = webview.create_window(
        'EdgeCase Equalizer',
        f'http://localhost:{PORT}',
        width=1280,
        height=800,
        min_size=(800, 600),
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
    storage_dir = str(Path.home() / 'Library' / 'Application Support' / 'EdgeCase' / 'webview')
    Path(storage_dir).mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=storage_dir)
    
    print("EdgeCase closed.")
    sys.exit(0)


if __name__ == '__main__':
    run_desktop()
