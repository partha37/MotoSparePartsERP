"""Isolated QA server — runs the real app against a throwaway COPY of
instance/erp.db, on a separate port, with cloud backup disabled. Use this
any time a change needs to be clicked through in a real browser instead of
just reasoning about the code — see qa/README.md for the full story on why
this exists and what it guarantees.

Usage (from the repo root, with the venv activated):

    python qa/qa_server.py                # fresh copy of erp.db, port 5099
    python qa/qa_server.py --port 5100    # run on a different port
    python qa/qa_server.py --keep         # reuse qa/data/erp.db instead of
                                           # re-copying from the real DB

Then open http://127.0.0.1:<port>/qa-auto-login to log in as the shop-owner
account with no password needed.

Do not "simplify" this by skipping any of the three isolation steps below
(DB URI, instance_path, CLOUD_BACKUP_DIR) — each one guards against a
separate, previously-real way QA data leaked into production. See the
qa-db-isolation-bug memory / qa/README.md for what happens if you do.
"""
import argparse
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QA_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
REAL_DB = os.path.join(REPO_ROOT, "instance", "erp.db")
QA_DB = os.path.join(QA_DATA_DIR, "erp.db")

sys.path.insert(0, REPO_ROOT)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", type=int, default=5099, help="Port to run on (default: 5099)")
    parser.add_argument(
        "--keep", action="store_true",
        help="Reuse the existing qa/data/erp.db as-is instead of refreshing it from the real DB",
    )
    args = parser.parse_args()

    os.makedirs(QA_DATA_DIR, exist_ok=True)

    if args.keep and os.path.exists(QA_DB):
        print(f"Reusing existing QA database: {QA_DB}")
    else:
        if not os.path.exists(REAL_DB):
            print(f"Real database not found at {REAL_DB} — nothing to copy.")
            sys.exit(1)
        shutil.copy2(REAL_DB, QA_DB)
        print(f"Copied {REAL_DB}\n     -> {QA_DB}")

    # Step 1/3: override the DB URI on the Config class BEFORE create_app()
    # runs — Flask-SQLAlchemy binds its engine eagerly inside db.init_app(),
    # so setting app.config[...] afterward is a silent no-op (see the
    # qa-db-isolation-bug memory for the incident that established this).
    import config
    config.Config.SQLALCHEMY_DATABASE_URI = "sqlite:///" + QA_DB.replace("\\", "/")
    # Step 2/3: never let a QA session's data reach the real cloud backup
    # folder — independent of the DB URI override above.
    config.Config.CLOUD_BACKUP_DIR = ""

    from app import create_app
    from flask_login import login_user
    from models import User

    app = create_app()
    # Step 3/3: app.instance_path controls where excel_sync.py writes the
    # Excel mirror (erp_data.xlsx) — independent of SQLALCHEMY_DATABASE_URI,
    # so it needs its own override or every sync_to_excel() call during this
    # session overwrites the real instance/erp_data.xlsx.
    app.instance_path = QA_DATA_DIR
    app.debug = False

    @app.route("/qa-auto-login")
    def qa_auto_login():
        user = User.query.first()
        if not user:
            return "No user found in the QA database.", 404
        login_user(user)
        return f"Logged in as {user.username}. <a href='/'>Go to dashboard</a>."

    print(f"\nQA server starting: http://127.0.0.1:{args.port}")
    print(f"Auto-login:         http://127.0.0.1:{args.port}/qa-auto-login\n")
    app.run(port=args.port, debug=False)


if __name__ == "__main__":
    main()
