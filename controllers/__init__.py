"""Controller helpers: authentication guards, CSRF, rate limiting."""
import secrets, time
from functools import wraps
from flask import session, redirect, url_for, g, request, abort, current_app
from models.user import User

_hits = {}

def rate_limited(key, limit=None, window=60):
    limit = limit or current_app.config.get("RATE_LIMIT", 10)
    t = time.time(); q = [x for x in _hits.get(key, []) if t - x < window]; q.append(t); _hits[key] = q
    return len(q) > limit

def load_user():
    uid = session.get("uid"); g.user = User.get(uid) if uid else None
    if g.user and g.user.is_locked: session.clear(); g.user = None

def csrf_token():
    if "csrf" not in session: session["csrf"] = secrets.token_hex(16)
    return session["csrf"]

def check_csrf():
    if request.method == "POST" and not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf", "x")):
        abort(400, "Invalid or missing CSRF token.")

def role_required(*roles):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if g.user is None: return redirect(url_for("auth.login", next=request.path))
            if roles and g.user.role not in roles: abort(403)
            return f(*a, **k)
        return w
    return deco
login_required = role_required()
