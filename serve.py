"""Production entry point — run this instead of app.py for real day-to-day use.

app.py's `python app.py` uses Flask's built-in dev server (debug=True), which
auto-reloads on code changes and exposes an interactive debugger — great while
developing, but not meant to stay on for daily use. This uses waitress, a
plain production WSGI server, with debug off.
"""
from waitress import serve

from app import app

if __name__ == "__main__":
    serve(app, host="127.0.0.1", port=5000)
