from flask import Flask

from config import Config
from extensions import db, migrate, login_manager, csrf
from models import User


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

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.products import products_bp
    from routes.suppliers import suppliers_bp
    from routes.purchases import purchases_bp
    from routes.customers import customers_bp
    from routes.mechanics import mechanics_bp
    from routes.sales import sales_bp
    from routes.stock import stock_bp
    from routes.reports import reports_bp
    from routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(mechanics_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
