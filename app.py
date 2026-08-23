import os
from datetime import timedelta, timezone
from functools import lru_cache

from flask import Flask
from markupsafe import Markup

from config import Config
from extensions import db, migrate, login_manager, csrf
from models import User

# India doesn't observe daylight saving, so IST is always a fixed UTC+5:30
# offset — no timezone database (e.g. the `tzdata` package, not present on
# Windows by default) is needed to convert to it correctly.
IST = timezone(timedelta(hours=5, minutes=30))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @lru_cache(maxsize=64)
    def _read_icon(name):
        path = os.path.join(app.root_path, "static", "vendor", "bootstrap-icons", f"{name}.svg")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            app.logger.warning("Icon '%s' not found in static/vendor/bootstrap-icons/", name)
            return ""

    @app.context_processor
    def inject_icon_helper():
        def icon(name, css_class=""):
            """Inlines a locally-vendored Bootstrap Icon SVG so it inherits `currentColor`
            (works in dark navbars, colored buttons, etc. — unlike an <img> tag)."""
            svg = _read_icon(name)
            if css_class:
                svg = svg.replace('class="bi bi-' + name + '"', f'class="bi bi-{name} {css_class}"')
            return Markup(svg)
        return dict(icon=icon)

    @app.context_processor
    def inject_ist_helper():
        def ist(dt, fmt="%d-%m-%Y %I:%M %p"):
            """Formats a naive UTC datetime (every `created_at` column is stored via
            datetime.utcnow()) as IST in 12-hour clock — the display format used
            everywhere a record's actual timestamp is shown, as opposed to the
            separate user-editable business `date` fields (Purchase.date, Sale.date,
            etc.), which stay date-only and are not touched by this helper."""
            if dt is None:
                return ""
            return dt.replace(tzinfo=timezone.utc).astimezone(IST).strftime(fmt)
        return dict(ist=ist)

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.products import products_bp
    from routes.brands import brands_bp
    from routes.suppliers import suppliers_bp
    from routes.purchases import purchases_bp
    from routes.customers import customers_bp
    from routes.mechanics import mechanics_bp
    from routes.sales import sales_bp
    from routes.sale_returns import sale_returns_bp
    from routes.stock import stock_bp
    from routes.reports import reports_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(brands_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(mechanics_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(sale_returns_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
