"""Flask extension instances, initialized without an app.

Kept separate from __init__.py and models.py to avoid circular imports:
models.py needs `db`, blueprints need `db`/`jwt`/`bcrypt`, and the app
factory needs to call .init_app() on each — this file lets everyone
import the same instance safely.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate

db = SQLAlchemy()
jwt = JWTManager()
bcrypt = Bcrypt()
migrate = Migrate()