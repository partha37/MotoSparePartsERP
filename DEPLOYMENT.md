# Running the app on the shop PC

This app runs locally on one Windows PC — nothing is hosted online. There are
two ways to start it; use the daily-use one unless you're actively changing code.

## Daily use (production server)

Just double-click **`start.bat`** in the project folder.

- It activates the venv, starts the app using `serve.py` (a proper production
  server, not the dev one), and opens your browser to it automatically.
- A console window titled "MotoSpareParts ERP Server" opens and stays open
  while the app runs — **closing that window stops the app**.
- Reachable from this PC at `http://127.0.0.1:5000`, and also from other
  devices on the same WiFi/hotspot — see below.

## Access from other devices on the network

`serve.py` binds to all network interfaces, not just this PC, so a phone or
another PC connected to the **same WiFi network or hotspot** can open the app
too — handy for a second billing point, or checking reports from the counter
without walking over to the PC.

1. Start the server as usual (`start.bat`, or the silent options below). The
   console window prints two URLs — use the second one on other devices:
   ```
   Server starting:
     On this PC:        http://127.0.0.1:5000
     On other devices:  http://192.168.1.23:5000  (same WiFi/hotspot only)
   ```
   That IP address is this PC's address on whichever network it's currently
   connected to — it changes if you switch networks (e.g. a different mobile
   hotspot), so re-check it each time rather than writing it down once.
2. On the phone/other PC, connect to the **exact same WiFi network or
   hotspot** as the shop PC, then open that address in a browser.
3. **First time only — Windows Firewall**: Windows will likely pop up a
   "Windows Defender Firewall has blocked some features of this app" prompt
   the first time `python.exe`/`pythonw.exe` binds to the network. Check
   **Private networks** (not Public) and click **Allow access**. If you
   missed the prompt, open **Windows Defender Firewall → Allow an app
   through firewall** and add it manually — browse to the *real* interpreter
   path, not `venv\Scripts\python.exe` (that's just a redirect on this
   machine; Windows Firewall matches on the actual file, which resolves to
   somewhere like `C:\Users\<you>\AppData\Local\Programs\Python\Python3xx\python.exe` —
   check Task Manager → Details tab while the server is running, right-click
   `python.exe` → **Open file location**, to find the exact path). Tick
   **Private** for it.
4. **If it still won't connect even with that rule allowed** — check one
   more Windows Firewall setting that's easy to miss and silently overrides
   the app-specific allow rule: **Windows Security → Firewall & network
   protection → Private network → make sure "Block all incoming
   connections, including those in the list of allowed apps" is OFF.**
   When this is on, connections *from this PC to itself* (e.g. opening
   `127.0.0.1:5000`, or even testing the PC's own LAN IP from itself) still
   work fine, which makes it look like everything's configured correctly —
   but genuine incoming connections from another device (a phone, another
   PC) get silently refused. This was the actual cause the one time this was
   debugged end-to-end, after the firewall app-rule and router settings had
   already checked out fine.
5. If it still doesn't connect: confirm both devices show the *same* WiFi
   network name, and that the network is set to "Private" in Windows (not
   "Public") — Windows blocks more by default on Public networks, which is
   the usual reason a phone can't reach it even with the firewall rule
   allowed. Also check the router isn't isolating WiFi clients from each
   other ("AP Isolation"/"Client Isolation", sometimes labeled something
   unexpected like "Block Relay") — usually under the router's WiFi/wireless
   settings.

**Security note**: this makes the app reachable by anything on that WiFi
network, not just your own devices — fine for a private shop WiFi or a
personal mobile hotspot, but don't do this on a shared/public network. There's
no HTTPS (plain HTTP only), so treat it the same as any other device on your
own trusted network, not something to expose further (e.g. via router port
forwarding to the internet) — this app was never built with that in mind.

## While developing (dev server)

```
venv\Scripts\activate
python app.py
```

Then open http://127.0.0.1:5000. This uses Flask's built-in dev server —
auto-reloads on code changes, but shouldn't be left running for real
day-to-day billing (no auto-restart if it crashes, exposes a debug console).

**Don't run both at once** — they both try to use port 5000; whichever
started second will fail to start until the first is closed.

## One-time setup on a new/fresh PC

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set FLASK_APP=app.py
flask db upgrade
```

The first `pip install` also pulls in `waitress`, the production server
`start.bat` needs.

A `.env` file holding a random `SECRET_KEY` is created once and kept locally
(it's gitignored — never copied between machines or committed). If it's
missing, `config.py` falls back to an insecure placeholder key, so make sure
one exists before relying on the app for real data. Contents look like:

```
SECRET_KEY=<a long random hex string>
```

## Auto-start when Windows boots (optional)

1. Right-click `start.bat` → **Copy**.
2. Press `Win+R`, type `shell:startup`, hit Enter.
3. Paste a shortcut to `start.bat` into that folder.

The app will now start automatically on every Windows login, with the
console window visible (see below if you'd rather it stay hidden).

## Running with no console window

`start.bat` deliberately shows a console window — closing it is how you stop
the app. If you'd rather it start with nothing visible at all (no window,
not even in the taskbar), use `pythonw.exe` instead of `python.exe`:
`pythonw` is the same Python that ships in `venv\Scripts`, just built to run
without opening a console.

### Option A — a silent shortcut you double-click instead of `start.bat`

1. Right-click the desktop → **New → Shortcut**.
2. For the location, enter (adjust the path to where this project actually lives):
   ```
   "C:\Users\Parthiban\Desktop\Repos\MotoSparePartsERP\venv\Scripts\pythonw.exe" serve.py
   ```
3. Right-click the new shortcut → **Properties** → set **Start in** to the
   project folder (`C:\Users\Parthiban\Desktop\Repos\MotoSparePartsERP`) —
   without this, it won't find `serve.py` or `instance\erp.db`.
4. Name it something like "ERP (silent)". Double-clicking it starts the app
   with no window at all; your browser won't open automatically either
   (nothing runs to trigger it), so open http://127.0.0.1:5000 yourself.

### Option B — auto-start hidden at Windows login (fully hands-off, no double-click)

This uses **Task Scheduler**, built into Windows — no extra software needed.

1. Open Start menu → search **Task Scheduler** → open it.
2. **Action → Create Task…** (not "Create Basic Task", so you get the
   "hidden" option).
3. **General** tab: name it `MotoSpareParts ERP`. Under **Security options**,
   select "Run only when user is logged on", and check **Hidden**.
4. **Triggers** tab → **New…** → Begin the task **At log on** → OK.
5. **Actions** tab → **New…** →
   - Program/script: `C:\Users\Parthiban\Desktop\Repos\MotoSparePartsERP\venv\Scripts\pythonw.exe`
   - Add arguments: `serve.py`
   - Start in: `C:\Users\Parthiban\Desktop\Repos\MotoSparePartsERP`
   - OK.
6. Save the task. From now on, the app silently starts in the background
   every time you log into Windows — no icon, no window, nothing to click.

### Stopping a silent/hidden run

Since there's no window to close, double-click **`stop.bat`** — it finds
whatever is listening on port 5000 and stops it, regardless of whether it
was started via `start.bat`, a silent shortcut, or Task Scheduler.

## Making data-model changes later

If you add/change a field in `models.py`:

```
set FLASK_APP=app.py
flask db migrate -m "describe your change"
flask db upgrade
```

## Backing up your data

Settings > Backup in the app downloads a copy of `instance/erp.db`. Do this
regularly and keep the copy somewhere safe (a USB drive, cloud storage, etc.).

### Automatic cloud backup (optional)

Set `CLOUD_BACKUP_DIR` in `.env` to a folder that a cloud-sync client (Google
Drive Desktop, OneDrive, etc.) already watches, and the app will copy
`erp.db`/`erp_data.xlsx` into it after every change — no manual backup step
needed day to day:

```
CLOUD_BACKUP_DIR=G:\My Drive\MotoSparePartsERP-Backup
```

Requirements:
- The cloud client must already be installed, signed in, and running — the
  app doesn't install or sign into anything itself. If the folder doesn't
  currently exist (client not running, signed out, no internet), the backup
  step is silently skipped and the sale/purchase you were saving still
  completes normally — this is a safety net, not something that can block
  billing.
- Leave `CLOUD_BACKUP_DIR` unset (the default) to turn this off entirely.
- The app never writes directly into the synced folder while a file is
  mid-write — it copies to a temporary name and renames it into place, so
  the sync client only ever uploads a complete file.
