"""Student Attendance System (QR) - Flask application, MVC architecture.
Model: models/*   View: templates/*   Controller: controllers/*"""
import os
from flask import Flask, g, render_template
import database
from controllers import load_user, csrf_token, check_csrf

def create_app(config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"), MAX_CONTENT_LENGTH=5 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", RATE_LIMIT=10)
    app.config["DATABASE"] = os.path.join(app.instance_path, "attendance.db")
    app.config["UPLOAD_DIR"] = os.path.join(app.instance_path, "uploads")
    app.config.update(config or {})
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True); os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    database.init_app(app)
    app.before_request(load_user); app.before_request(check_csrf)
    app.jinja_env.globals.update(csrf_token=csrf_token)
    app.context_processor(lambda: {"me": g.get("user")})
    from controllers import auth, student, lecturer, admin
    for m in (auth, student, lecturer, admin): app.register_blueprint(m.bp)
    @app.errorhandler(403)
    def forbidden(e): return render_template("error.html", code=403, msg="You do not have permission to view this page."), 403
    @app.errorhandler(404)
    def missing(e): return render_template("error.html", code=404, msg="Page not found."), 404
    @app.errorhandler(400)
    def bad(e): return render_template("error.html", code=400, msg=getattr(e, "description", "Bad request.")), 400
    @app.errorhandler(413)
    def big(e): return render_template("error.html", code=413, msg="File is too large (max 5 MB)."), 413
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
