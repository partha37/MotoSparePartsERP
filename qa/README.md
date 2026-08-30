# QA server — test against a disposable copy of real data

`qa/qa_server.py` runs the actual Flask app against a **copy** of `instance/erp.db`, on a separate port, with cloud backup disabled — so you (or Claude) can click through real workflows (record a purchase, bill a sale, hide a table column, whatever's being changed) without ever touching the live shop database, its Excel mirror, or the cloud backup folder.

## Why this exists

Every real QA pass on this app needs the exact same isolation: a fresh DB copy, an overridden `SQLALCHEMY_DATABASE_URI`/`CLOUD_BACKUP_DIR`/`instance_path`, and a way to log in without knowing the real password. Before this script existed, that setup got hand-rolled from scratch in a temp folder every single session — a real, repeated cost, and each of the three isolation steps has independently caused live-data contamination in the past when done slightly wrong (see the `qa-db-isolation-bug` memory). This script is that same setup, written once and checked in, so it doesn't need to be re-derived — or re-broken — next time.

## Usage

```
# from the repo root, with the venv activated
python qa/qa_server.py                # fresh copy of erp.db, runs on port 5099
python qa/qa_server.py --port 5100    # use a different port (e.g. to run two QA servers side by side)
python qa/qa_server.py --keep         # reuse qa/data/erp.db as-is instead of re-copying from the real DB
```

Then open **http://127.0.0.1:5099/qa-auto-login** — logs in as whichever shop-owner account exists in the QA copy, no password needed, then links through to the dashboard.

Stop it the normal way (Ctrl+C, or however the process was launched — e.g. a background task).

## What it guarantees

- `instance/erp.db` (the real data) is **read once, to copy it** — this script never writes to it.
- The QA copy lives at `qa/data/erp.db`, gitignored, fully separate from the real `instance/` folder — including its own Excel mirror at `qa/data/erp_data.xlsx`, which never touches the real `instance/erp_data.xlsx`.
- `CLOUD_BACKUP_DIR` is force-set to `""`, so QA data can never leak into the real cloud backup folder configured in `.env`.
- Runs with `debug=False` — same template-caching behavior as production `serve.py`. **If you edit a template while this server is already running, restart it to see the change** — this is a known Flask gotcha (Jinja only checks template mtimes when `debug=True`), also documented in `.claude/skills/ui-visual-conventions/SKILL.md`.

## When to still be careful

- This script only isolates *this one process*. If you're driving it with `chrome-devtools` MCP tools, double-check `list_pages` before acting — it's easy to have a leftover tab pointed at the user's real `127.0.0.1:5000` session open at the same time, and clicking the wrong tab defeats all of the isolation above.
- After a QA session, it's still worth spot-checking that the real `instance/erp.db` row counts/ids are unchanged, especially if this script itself was modified — trust but verify, per the `qa-db-isolation-bug` memory.
- `qa/data/` can be deleted any time you want a completely clean slate; it's regenerated (fresh copy of the real DB) on the next run unless `--keep` is passed.

## Extending it

If a QA scenario needs something this script doesn't do yet (seeding specific test data, a different starting user, hitting a non-default port range), prefer adding a flag to `qa_server.py` over writing a new one-off script — that's the whole point of having checked this in.
