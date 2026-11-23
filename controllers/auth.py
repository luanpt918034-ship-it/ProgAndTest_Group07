from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from controllers import login_required, rate_limited, csrf_token
from database import AppError
from models.user import User

bp = Blueprint("auth", __name__)

@bp.route("/")
def index(): return redirect(url_for(g.user.home())) if g.user else redirect(url_for("auth.login"))

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("username", ""), request.form.get("password", "")
        if rate_limited(("login", request.remote_addr, u.lower())):
            flash("Too many attempts. Please wait a minute.", "error"); return render_template("login.html"), 429
        try: user = User.login(u, p)
        except AppError as e:
            flash(str(e), "error"); return render_template("login.html"), 401
        session.clear(); session["uid"] = user.user_id; csrf_token()
        nxt = request.args.get("next", "")
        return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for(user.home()))
    return render_template("login.html")

@bp.route("/logout", methods=["POST"])
def logout():
    session.clear(); flash("You have been logged out.", "ok"); return redirect(url_for("auth.login"))

@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        User.request_reset(request.form.get("email", ""), lambda t: url_for("auth.reset", token=t, _external=True))
        return render_template("reset_sent.html")
    return render_template("forgot.html")

@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    if request.method == "POST":
        try:
            User.reset_password(token, request.form.get("password", ""), request.form.get("confirm", ""))
            flash("Password updated. Please log in.", "ok"); return redirect(url_for("auth.login"))
        except AppError as e: flash(str(e), "error")
    elif not User.valid_reset_token(token):
        flash("The reset link is invalid or has expired.", "error"); return redirect(url_for("auth.forgot"))
    return render_template("reset.html")

@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        try:
            g.user.change_password(request.form.get("old", ""), request.form.get("new", ""), request.form.get("confirm", ""))
            flash("Password changed successfully.", "ok"); return redirect(url_for(g.user.home()))
        except AppError as e: flash(str(e), "error")
    return render_template("change_password.html")

@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        try:
            g.user.update_profile(request.form.get("full_name", ""), request.form.get("email", ""), request.form.get("phone", ""))
            flash("Profile updated.", "ok"); return redirect(url_for("auth.profile"))
        except AppError as e: flash(str(e), "error")
    return render_template("profile.html", u=User.get(g.user.user_id))
