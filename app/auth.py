from flask import session, redirect, url_for, flash
from functools import wraps
from .db import query_one

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None

    return query_one("""
        SELECT u.*, c.name as company_name
        FROM users u
        LEFT JOIN companies c ON c.id = u.company_id
        WHERE u.id = ?
    """, (uid,))

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("web.login"))
        return view(*args, **kwargs)
    return wrapped

def roles_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user["role"] not in roles:
                flash("Acesso não permitido.", "danger")
                return redirect(url_for("web.dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return deco