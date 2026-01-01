"""
EdgeCase CLI - Command line interface for starting the server
"""

import atexit
import logging
import sys
import os
import signal

# Track if cleanup has run to avoid running twice
_cleanup_done = False


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
                # Run backup check before shutdown
                try:
                    from utils import backup
                    frequency = db.get_setting('backup_frequency', 'daily')
                    if backup.check_backup_needed(frequency):
                        location = db.get_setting('backup_location', '')
                        result = backup.create_backup(location if location else None)
                        if result:
                            print(f"Backup completed: {result['filename']}")
                        backup.record_backup_check()
                except Exception as e:
                    print(f"Backup warning: {e}")
                
                db.checkpoint()
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
  --dev          Development mode with auto-reload
  --help         Show this message

Environment variables:
  EDGECASE_PORT  Port number (default: 8080)
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
                    # Run backup check before shutdown
                    try:
                        from utils import backup
                        frequency = db.get_setting('backup_frequency', 'daily')
                        if backup.check_backup_needed(frequency):
                            location = db.get_setting('backup_location', '')
                            result = backup.create_backup(location if location else None)
                            if result:
                                print(f"Backup completed: {result['filename']}")
                            backup.record_backup_check()
                    except Exception as e:
                        print(f"Backup warning: {e}")
                    
                    db.checkpoint()
                    print("Database checkpoint completed.")
        except Exception as e:
            # Best effort - don't crash on shutdown
            print(f"Shutdown warning: {e}")
    
    sys.exit(0)


def run():
    """Entry point for the edgecase command."""
    
    # Check for --help first
    if '--help' in sys.argv or '-h' in sys.argv:
        show_help()
    
    from web.app import app
    from waitress import serve
    
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
    
    # Check for --dev flag for development mode with auto-reload
    if '--dev' in sys.argv:
        print("\nStarting in DEVELOPMENT mode (auto-reload enabled)...")
        print(f"Open your browser to: http://localhost:{port}")
        print("\nPress Ctrl+C to stop the server\n")
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # Production mode with Waitress
        print("\nStarting web server...")
        print(f"Open your browser to: http://localhost:{port}")
        print("\nPress Ctrl+C to stop the server\n")
        serve(app, host='0.0.0.0', port=port)
