"""Production entry point — run this instead of app.py for real day-to-day use.

app.py's `python app.py` uses Flask's built-in dev server (debug=True), which
auto-reloads on code changes and exposes an interactive debugger — great while
developing, but not meant to stay on for daily use. This uses waitress, a
plain production WSGI server, with debug off.

Binds to 0.0.0.0 (every network interface), not just 127.0.0.1 — so other
devices on the same WiFi/hotspot (phone, another PC) can reach it too, at
http://<this-PC's-LAN-IP>:5000, not just from this machine. See DEPLOYMENT.md
("Access from other devices on the network") for the Windows Firewall prompt
this triggers the first time, and the security tradeoffs of doing this.
"""
import socket

from waitress import serve

from app import app


def _lan_ip():
    """Best-effort local network IP to print at startup, so the shop owner
    doesn't have to go dig it up via ipconfig. Doesn't actually send
    anything — connect() on a UDP socket just makes the OS pick which local
    interface/IP would be used to route to that address, so this works even
    fully offline (no real internet needed, matching this app's offline-first
    design) as long as some default route/interface exists. Falls back to
    loopback if that lookup fails for any reason (e.g. no network at all)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    lan_ip = _lan_ip()
    print("Server starting:")
    print(f"  On this PC:        http://127.0.0.1:5000")
    if lan_ip != "127.0.0.1":
        print(f"  On other devices:  http://{lan_ip}:5000  (same WiFi/hotspot only)")
    serve(app, host="0.0.0.0", port=5000)
