# Running the app on the shop PC

This app runs locally on one Windows PC — nothing is hosted online. There are
two ways to start it; use the daily-use one unless you're actively changing code.

## Daily use (production server)

Just double-click **`start.bat`** in the project folder.

- It activates the venv, starts the app using `serve.py` (a proper production
  server, not the dev one), and opens your browser to it automatically.
- A console window titled "MotoSpareParts ERP Server" opens and stays open
  while the app runs — **closing that window stops the app**.
- Only reachable from this PC (`http://127.0.0.1:5000`), not from other
  devices on the shop WiFi.

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
regularly and keep the copy somewhere safe (a USB drive, cloud storage, etc.)
— nothing else backs it up automatically.
