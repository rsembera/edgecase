"""
EdgeCase - Practice Management for Independent Therapists
Main entry point - launches Flask web interface
"""

from web.app import app
import logging

if __name__ == "__main__":
    # Reduce Flask logging noise
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    print("\n" + "="*50)
    print("EdgeCase Equalizer")
    print("="*50)
    print("\nStarting web server...")
    print("Open your browser to: http://localhost:8080")
    print("\nPress Ctrl+C to stop the server\n")
    
    app.run(host='0.0.0.0', port=8080, debug=True)