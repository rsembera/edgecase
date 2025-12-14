"""
EdgeCase - Practice Management for Independent Therapists
Main entry point - launches Flask web interface
"""

from web.app import app
import logging
import sys

if __name__ == "__main__":
    # Reduce logging noise
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    print("\n" + "="*50)
    print("EdgeCase Equalizer")
    print("="*50)
    
    # Check for --dev flag for development mode with auto-reload
    if '--dev' in sys.argv:
        print("\nStarting in DEVELOPMENT mode (auto-reload enabled)...")
        print("Open your browser to: http://localhost:8080")
        print("\nPress Ctrl+C to stop the server\n")
        app.run(host='0.0.0.0', port=8080, debug=True)
    else:
        # Production mode with Waitress
        from waitress import serve
        print("\nStarting web server...")
        print("Open your browser to: http://localhost:8080")
        print("\nPress Ctrl+C to stop the server\n")
        serve(app, host='0.0.0.0', port=8080)
