"""Application factory for HomeSpace."""
import os
from flask import Flask, send_from_directory

from app.config import config_map
from app.extensions import db, jwt, bcrypt, migrate, limiter
from app.properties.image_routes import images_bp


def create_app(config_name: str | None = None) -> Flask:
    """Build and configure the Flask application."""
    app = Flask(__name__, static_folder="../frontend", static_url_path="")

    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app.config.from_object(config_map[config_name])

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    _register_blueprints(app)

    @app.route("/")
    def serve_index():
        return send_from_directory(app.static_folder, "index.html")

    return app


def _register_blueprints(app: Flask) -> None:
    """Register all application blueprints."""
    from app.auth.routes import auth_bp
    from app.properties.routes import properties_bp
    from app.bookings.routes import bookings_bp
    from app.payments.routes import payments_bp
    from app.chatbot.routes import chatbot_bp
    from app.properties.availability_routes import availability_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(properties_bp, url_prefix="/api/properties")
    app.register_blueprint(bookings_bp, url_prefix="/api/bookings")
    app.register_blueprint(payments_bp, url_prefix="/api/payments")
    app.register_blueprint(chatbot_bp, url_prefix="/api/chat")
    app.register_blueprint(availability_bp, url_prefix="/api/properties") 
    app.register_blueprint(images_bp, url_prefix="/api/properties")