from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime

from app.db import query_one, query_all, execute
from app.auth import login_required, current_user, roles_required

web_bp = Blueprint("web", __name__)


# HOME
@web_bp.route("/")
def home():
    companies = query_all("select * from companies order by name")
    protocol = request.args.get("protocol", "").strip()
    tracking = None

    if protocol:
        tracking = query_one(
            "select protocol, status, created_at, deadline_iso, closed_at from tickets where protocol = ?",
            (protocol,),
        )

    return render_template("home.html", companies=companies, tracking=tracking)


# CRIAR CHAMADO
@web_bp.post("/tickets/new")
def create_ticket():
    requester = request.form.get("requester_name", "").strip()
    sector = request.form.get("sector", "").strip()
    description = request.form.get("description", "").strip()
    company_choice = request.form.get("company_choice", "").strip()
    company_other = request.form.get("company_other", "").strip()

    if not requester or not sector or not description or not company_choice:
        flash("Preencha os campos obrigatórios.", "danger")
        return redirect(url_for("web.home"))

    if len(description) < 10:
        flash("Descrição muito curta.", "danger")
        return redirect(url_for("web.home"))

    company_id = None

    if company_choice != "other":
        row = query_one("select id from companies where id = ?", (company_choice,))
        if not row:
            flash("Empresa inválida.", "danger")
            return redirect(url_for("web.home"))
        company_id = row["id"]

    execute(
        """
        insert into tickets(protocol, requester_name, sector, description, company_id, status, created_at)
        values(?, ?, ?, ?, ?, 'ABERTO', ?)
        """,
        (
            f"HGA-{datetime.utcnow().timestamp()}",
            requester,
            sector,
            description,
            company_id,
            datetime.utcnow().isoformat(timespec="seconds"),
        ),
    )

    flash("Chamado criado com sucesso!", "success")
    return redirect(url_for("web.home"))


# LOGIN
@web_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = query_one("select * from users where username = ?", (username,))

        from werkzeug.security import check_password_hash

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Usuário ou senha inválidos.", "danger")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]

        return redirect(url_for("web.dashboard"))

    return render_template("login.html")


# LOGOUT
@web_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.home"))


# DASHBOARD
@web_bp.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    tickets = query_all("select * from tickets order by id desc")

    open_count = len([t for t in tickets if t["status"] == "ABERTO"])
    andamento_count = len([t for t in tickets if t["status"] == "EM_ANDAMENTO"])
    concl_count = len([t for t in tickets if t["status"] == "CONCLUIDO"])

    return render_template(
        "dashboard.html",
        tickets=tickets,
        open_count=open_count,
        andamento_count=andamento_count,
        concl_count=concl_count,
    )


# DETALHE DO CHAMADO
@web_bp.route("/ticket/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    user = current_user()

    ticket = query_one("select * from tickets where id = ?", (ticket_id,))
    if not ticket:
        flash("Chamado não encontrado.", "danger")
        return redirect(url_for("web.dashboard"))

    if request.method == "POST":
        status = request.form.get("status", "").strip()
        note = request.form.get("note", "").strip()

        execute(
            "update tickets set status = ? where id = ?",
            (status, ticket_id),
        )

        execute(
            "insert into observations(ticket_id, user_id, status_after, note, created_at) values(?, ?, ?, ?, ?)",
            (
                ticket_id,
                user["id"],
                status,
                note,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )

        flash("Chamado atualizado.", "success")
        return redirect(url_for("web.ticket_detail", ticket_id=ticket_id))

    observations = query_all(
        """
        select o.*, u.display_name
        from observations o
        join users u on u.id = o.user_id
        where o.ticket_id = ?
        order by o.id desc
        """,
        (ticket_id,),
    )

    return render_template(
        "ticket_detail.html",
        ticket=ticket,
        observations=observations,
    )


# PERFIL
@web_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()

        execute(
            "update users set display_name = ? where id = ?",
            (display_name, user["id"]),
        )

        flash("Perfil atualizado.", "success")
        return redirect(url_for("web.profile"))

    return render_template("profile.html", user=user)


# SETTINGS
@web_bp.route("/settings", methods=["GET", "POST"])
@login_required
@roles_required("master")
def settings_view():
    if request.method == "POST":
        flash("Configurações salvas.", "success")
        return redirect(url_for("web.settings_view"))

    return render_template("settings.html")


# RELATÓRIOS
@web_bp.route("/reports", methods=["GET", "POST"])
@login_required
def reports_view():
    user = current_user()

    if request.method == "POST":
        notes = request.form.get("notes", "").strip()

        execute(
            "insert into reports(company_id, notes, created_at) values(?, ?, ?)",
            (user["company_id"], notes, datetime.utcnow().isoformat(timespec="seconds")),
        )

        flash("Relatório enviado.", "success")
        return redirect(url_for("web.reports_view"))

    reports = query_all(
        """
        select r.*, c.name as company_name
        from reports r
        join companies c on c.id = r.company_id
        order by r.id desc
        """
    )

    return render_template("reports.html", reports=reports)