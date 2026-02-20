"""
EdgeCase CLI - Command line interface for starting the server
"""

import atexit
import logging
import sys
import os
import signal
import time
import threading

# Track if cleanup has run to avoid running twice
_cleanup_done = False

# Heartbeat tracking for desktop mode
_last_heartbeat = time.time()
_heartbeat_lock = threading.Lock()
HEARTBEAT_TIMEOUT = 30  # seconds without heartbeat before shutdown


def update_heartbeat():
    """Update the last heartbeat timestamp. Called on any browser request."""
    global _last_heartbeat
    with _heartbeat_lock:
        _last_heartbeat = time.time()


def _heartbeat_monitor():
    """Background thread that monitors for heartbeat timeout in desktop mode."""
    global _last_heartbeat
    
    while True:
        time.sleep(5)  # Check every 5 seconds
        
        with _heartbeat_lock:
            elapsed = time.time() - _last_heartbeat
        
        if elapsed > HEARTBEAT_TIMEOUT:
            print(f"\n[Desktop] No browser heartbeat for {int(elapsed)}s - shutting down...")
            # Trigger graceful shutdown
            os.kill(os.getpid(), signal.SIGTERM)
            break


def _run_shutdown_backup(db, label="Shutdown"):
    """Checkpoint WAL and run backup check. Shared by all shutdown paths."""
    import subprocess
    try:
        from utils import backup
        db.checkpoint()
        frequency = db.get_setting('backup_frequency', 'daily')
        if backup.check_backup_needed(frequency):
            print(f"[{label}] Checking backup status...")
            location = db.get_setting('backup_location', '')
            result = backup.create_backup(location if location else None)
            if result:
                print(f"[{label}] Backup completed: {result['filename']}")
                post_cmd = db.get_setting('post_backup_command', '')
                if post_cmd:
                    try:
                        import shlex
                        subprocess.run(shlex.split(post_cmd), timeout=300)
                        print(f"[{label}] Post-backup command completed")
                    except Exception as cmd_error:
                        print(f"[{label}] Post-backup command error: {cmd_error}")
            else:
                print(f"[{label}] No changes since last backup")
            backup.record_backup_check()
    except Exception as e:
        print(f"[{label}] Backup warning: {e}")


def _cleanup():
    """Cleanup function for atexit - backup and checkpoint database."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    
    try:
        from flask import current_app
        from web.app import app
        
        with app.app_context():
            db = current_app.config.get('db')
            if db:
                _run_shutdown_backup(db, label="atexit")
    except Exception:
        pass  # Silent fail on exit


# Register atexit handler
atexit.register(_cleanup)


def show_help():
    """Display help text and exit."""
    help_text = """
EdgeCase Equalizer - Practice management for independent therapists

Usage: python main.py [options]

Options:
  --port=XXXX    Port to run on (default: 8080)
  --lan          Allow access from other devices on your network (e.g. iPad)
  --dev          Development mode with auto-reload
  --help         Show this message

Environment variables:
  EDGECASE_PORT  Port number (default: 8080)
  EDGECASE_LAN   Set to 1 to allow LAN access
  EDGECASE_DATA  Custom data directory
"""
    print(help_text)
    sys.exit(0)


def shutdown_handler(signum, frame):
    """Handle Ctrl-C gracefully - backup and checkpoint database before exit."""
    global _cleanup_done
    
    print("\n\nShutting down...")
    
    if not _cleanup_done:
        _cleanup_done = True
        try:
            from flask import current_app
            from web.app import app
            
            with app.app_context():
                db = current_app.config.get('db')
                if db:
                    _run_shutdown_backup(db, label="Shutdown")
                    print("Database checkpoint completed.")
        except Exception as e:
            print(f"Shutdown warning: {e}")
    
    sys.exit(0)


def run():
    """Entry point for the edgecase command."""
    
    # Check for --help first
    if '--help' in sys.argv or '-h' in sys.argv:
        show_help()
    
    from web.app import app
    from waitress import serve
    import webbrowser
    
    # Desktop mode: register heartbeat callback
    desktop_mode = os.environ.get('EDGECASE_DESKTOP') == '1'
    if desktop_mode:
        app.config['HEARTBEAT_CALLBACK'] = update_heartbeat
    
    # Reduce logging noise
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    # Quiet Waitress queue warnings (normal for single-user app)
    waitress_log = logging.getLogger('waitress')
    waitress_log.setLevel(logging.ERROR)
    
    # Get port from command line (--port=XXXX) or environment variable or default
    port = 8080
    for arg in sys.argv:
        if arg.startswith('--port='):
            try:
                port = int(arg.split('=')[1])
            except ValueError:
                print(f"Invalid port: {arg}")
                sys.exit(1)
    
    # Environment variable override
    env_port = os.environ.get('EDGECASE_PORT')
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            print(f"Invalid EDGECASE_PORT: {env_port}")
            sys.exit(1)
    
    print("\n" + "="*50)
    print("EdgeCase Equalizer")
    print("="*50)
    
    # Register shutdown handler for clean database checkpoint on Ctrl-C
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    # Desktop mode: start heartbeat monitor and auto-open browser
    if desktop_mode:
        # Start heartbeat monitor thread
        monitor = threading.Thread(target=_heartbeat_monitor, daemon=True)
        monitor.start()
        
        # Auto-open browser in desktop mode
        def open_browser():
            time.sleep(1.0)
            webbrowser.open(f'http://localhost:{port}')
        threading.Thread(target=open_browser, daemon=True).start()
    
    # Bind to localhost only by default (security: don't expose to network)
    # Use --lan flag or EDGECASE_LAN=1 for access from other devices (e.g. iPad)
    lan_mode = '--lan' in sys.argv or os.environ.get('EDGECASE_LAN') == '1'
    bind_host = '0.0.0.0' if lan_mode else '127.0.0.1'
    
    # Check for --dev flag for development mode with auto-reload
    if '--dev' in sys.argv:
        print("\nStarting in DEVELOPMENT mode (auto-reload enabled)...")
        if lan_mode:
            print("LAN access enabled - accessible from other devices on your network")
        print(f"Open your browser to: http://localhost:{port}")
        print("\nPress Ctrl+C to stop the server\n")
        app.run(host=bind_host, port=port, debug=True)
    else:
        # Production mode with Waitress
        print("\nStarting web server...")
        if lan_mode:
            print("LAN access enabled - accessible from other devices on your network")
        print(f"Open your browser to: http://localhost:{port}")
        print("\nPress Ctrl+C to stop the server\n")
        serve(app, host=bind_host, port=port)
