import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Picks up SECRET_KEY (and anything else) from a local .env file if present —
# lets the shop PC have a real, persistent secret key without setting a
# Windows environment variable by hand. .env is gitignored since it's
# per-install, not project config.
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "instance", "erp.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Folder to mirror erp.db/erp_data.xlsx into after every change — point this
    # at a folder a cloud-sync client (Google Drive Desktop, OneDrive, etc.)
    # already watches, e.g. "G:\My Drive\MotoSparePartsERP-Backup". Left unset,
    # cloud backup is simply skipped (see excel_sync.py::_backup_to_cloud) —
    # this is opt-in per install, not a hard dependency.
    CLOUD_BACKUP_DIR = os.environ.get("CLOUD_BACKUP_DIR", "")
