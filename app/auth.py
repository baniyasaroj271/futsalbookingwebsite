import re
from urllib.parse import urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .extensions import db
from .models import User
from .security import login_required

auth_bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9 ()-]{7,20}$")


def _safe_next_url(target):
    if not target:
        return None
    candidate = urljoin(request.host_url, target)
    parsed = urlparse(candidate)
    if parsed.scheme in {"http", "https"} and parsed.netloc == request.host:
        return parsed.path
    return None


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        if not name or len(name) > 120 or not EMAIL_PATTERN.fullmatch(email):
            flash("Enter a valid name and email address.", "error")
        elif not PHONE_PATTERN.fullmatch(phone):
            flash("Enter a valid phone number.", "error")
        elif len(password) < 8:
            flash("Your password must be at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=name, email=email, phone=phone, role="customer")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            session.permanent = True
            flash("Welcome to FutsalHub Nepal!", "success")
            return redirect(url_for("main.dashboard"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password", "")):
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            return redirect(_safe_next_url(request.args.get("next")) or url_for("main.dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth/login.html")


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = db.session.get(User, session["user_id"])
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        if not name or len(name) > 120 or not PHONE_PATTERN.fullmatch(phone):
            flash("Enter a valid name and phone number.", "error")
        else:
            user.name = name
            user.phone = phone
            db.session.commit()
            flash("Your profile has been updated.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html", profile_user=user)
