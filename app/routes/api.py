from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash

from app.db import query_one, query_all
from app.auth import login_required, current_user

api_bp = Blueprint("api", __name__)

@api_bp.get("/tickets")
@login_required
def tickets():
    rows = query_all("SELECT * FROM tickets")
    return jsonify([dict(r) for r in rows])

@api_bp.post("/login")
def login():
    data = request.json

    user = query_one("SELECT * FROM users WHERE username=?", (data.get("username"),))

    if not user or not check_password_hash(user["password_hash"], data.get("password")):
        return jsonify({"error": "invalid"}), 401

    session["user_id"] = user["id"]
    return jsonify({"ok": True})