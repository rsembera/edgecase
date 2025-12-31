"""
EdgeCase CLI - Command line interface for starting the server
"""

import logging
import sys
import os


def run():
    """Entry point for the edgecase command."""
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
