from flask import Flask
import os
from pathlib import Path

from .db import init_db
from .routes.web import web_bp
from .routes.api import api_bp

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"

def create_app():
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=True)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # blueprints
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        init_db()

    return app