# MotoSpareParts ERP

A simple inventory, billing, and tracking app for a two-wheeler spare parts shop.

## First-time setup

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
set FLASK_APP=app.py
flask db upgrade
```

## Running the app

For day-to-day use on the shop PC, see [DEPLOYMENT.md](DEPLOYMENT.md) —
double-click `start.bat`.

For development:

```
venv\Scripts\activate
python app.py
```

Then open http://127.0.0.1:5000 in your browser. The first time you visit, you'll be asked to create your shop-owner login.

## Making changes to the data model later

If you add/change a field in `models.py`, run:

```
set FLASK_APP=app.py
flask db migrate -m "describe your change"
flask db upgrade
```

## Backing up your data

Go to Settings > Backup in the app to download a copy of `instance/erp.db`. Keep it somewhere safe.
