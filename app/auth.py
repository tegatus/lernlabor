from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .models import User, db

bp = Blueprint("auth", __name__)


def lp_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if not current_user.ist_lp:
            abort(403)
        return f(*a, **kw)
    return wrapper


def lernende_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **kw):
        if current_user.ist_lp:
            return redirect(url_for("lp.dashboard"))
        return f(*a, **kw)
    return wrapper


@bp.route("/")
def start():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for("lp.dashboard" if current_user.ist_lp else "lernende.dashboard"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(benutzername=request.form.get("benutzername", "").strip().lower()).first()
        if u and u.aktiv and u.check_passwort(request.form.get("passwort", "")):
            login_user(u)
            ziel = request.args.get("next")
            if not ziel or not ziel.startswith("/") or ziel.startswith("//"):
                ziel = url_for("auth.start")
            return redirect(ziel)
        flash("Benutzername oder Passwort falsch.", "fehler")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/passwort", methods=["GET", "POST"])
@login_required
def passwort():
    if request.method == "POST":
        alt, neu, neu2 = (request.form.get(k, "") for k in ("alt", "neu", "neu2"))
        if not current_user.check_passwort(alt):
            flash("Das bisherige Passwort stimmt nicht.", "fehler")
        elif len(neu) < 8:
            flash("Das neue Passwort muss mindestens 8 Zeichen lang sein.", "fehler")
        elif neu != neu2:
            flash("Die beiden neuen Passwörter stimmen nicht überein.", "fehler")
        else:
            current_user.set_passwort(neu)
            db.session.commit()
            flash("Passwort geändert.", "ok")
            return redirect(url_for("auth.start"))
    return render_template("auth/passwort.html")
