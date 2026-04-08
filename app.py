import base64
import hashlib
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
INSTANCE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = INSTANCE_DIR / "app.db"

def create_app():
    app = Flask(__name__, instance_path=str(INSTANCE_DIR), instance_relative_config=True)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,  # True em produção (https)
        SESSION_COOKIE_SAMESITE="Lax"
    )   
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
    app.config["FIXED_YEAR"] = int(os.getenv("FIXED_YEAR", "2026"))
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
    app.config["UPLOAD_EXTENSIONS"] = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

    def get_fernet():
        digest = hashlib.sha256(app.config["SECRET_KEY"].encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)

    app.fernet = get_fernet()

    def get_db():
        if "db" not in g:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            g.db = conn
        return g.db

    @app.teardown_appcontext
    def close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    app.get_db = get_db

    def encrypt_text(value: str | None):
        if not value:
            return None
        return app.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_text(value: str | None):
        if not value:
            return ""
        try:
            return app.fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def query_one(sql, params=()):
        return get_db().execute(sql, params).fetchone()

    def query_all(sql, params=()):
        return get_db().execute(sql, params).fetchall()

    def execute(sql, params=()):
        db = get_db()
        cur = db.execute(sql, params)
        db.commit()
        return cur

    def setting(key, default=""):
        row = query_one("select value from settings where key = ?", (key,))
        return row["value"] if row else default

    def set_setting(key, value):
        execute(
            "insert into settings(key, value) values(?, ?) on conflict(key) do update set value = excluded.value",
            (key, value),
        )

    def current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        row = query_one(
            """
            select u.id, u.username, u.display_name, u.role, u.company_id, c.name as company_name
            from users u left join companies c on c.id = u.company_id where u.id = ?
            """,
            (uid,),
        )
        return row

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped
    
    @app.get("/api/tickets")
    @login_required
    def api_tickets():
        user = current_user()
        tickets = visible_tickets(user)

        return jsonify([
            {
                "id": t["id"],
                "protocol": t["protocol"],
                "status": t["status"],
                "sector": t["sector"],
                "created_at": t["created_at"]
            } for t in tickets
        ])
    
    @app.get("/api/ticket/<int:ticket_id>")
    @login_required
    def api_ticket_detail(ticket_id):
        user = current_user()
        ticket = ticket_or_404(ticket_id, user)

        if not ticket:
            return jsonify({"error": "not found"}), 404

        return jsonify(dict(ticket))
    
    @app.post("/api/login")
    def api_login():
        data = request.json

        username = data.get("username")
        password = data.get("password")

        user = query_one("select * from users where username = ?", (username,))

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "invalid credentials"}), 401

        session["user_id"] = user["id"]

        return jsonify({"message": "ok"})

    def roles_required(*roles):
        def deco(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = current_user()
                if not user or user["role"] not in roles:
                    flash("Acesso não permitido.", "danger")
                    return redirect(url_for("dashboard"))
                return view(*args, **kwargs)
            return wrapped
        return deco

    def format_dt(value):
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return value

    def next_protocol():
        row = query_one("select count(*) as total from tickets")
        total = int(row["total"] or 0) + 1
        return f"HGA-{total:03d}"

    def visible_tickets(user):
        sql = "select t.*, c.name as company_name from tickets t left join companies c on c.id = t.company_id"
        params = []
        if user["role"] == "company":
            sql += " where t.company_id = ?"
            params.append(user["company_id"])
        sql += " order by t.id desc"
        return query_all(sql, tuple(params))

    def ticket_or_404(ticket_id, user):
        row = query_one(
            "select t.*, c.name as company_name from tickets t left join companies c on c.id = t.company_id where t.id = ?",
            (ticket_id,),
        )
        if not row:
            return None
        if user["role"] == "company" and row["company_id"] != user["company_id"]:
            return None
        return row

    def init_db():
        db = get_db()
        db.executescript(
            """
            create table if not exists settings (
                key text primary key,
                value text not null
            );
            create table if not exists companies (
                id integer primary key autoincrement,
                name text not null unique
            );
            create table if not exists users (
                id integer primary key autoincrement,
                username text not null unique,
                password_hash text not null,
                display_name text not null,
                role text not null,
                company_id integer,
                first_access integer not null default 1,
                created_at text not null,
                foreign key(company_id) references companies(id)
            );
            create table if not exists tickets (
                id integer primary key autoincrement,
                protocol text not null unique,
                requester_name text not null,
                requester_phone_enc text,
                sector text not null,
                description text not null,
                company_id integer,
                company_other_enc text,
                status text not null,
                deadline_iso text,
                created_at text not null,
                closed_at text,
                foreign key(company_id) references companies(id)
            );
            create table if not exists observations (
                id integer primary key autoincrement,
                ticket_id integer not null,
                user_id integer not null,
                status_after text not null,
                note text,
                created_at text not null,
                foreign key(ticket_id) references tickets(id),
                foreign key(user_id) references users(id)
            );
            create table if not exists reports (
                id integer primary key autoincrement,
                company_id integer not null,
                notes text,
                created_at text not null,
                foreign key(company_id) references companies(id)
            );
            """
        )
        db.commit()

        defaults = {
            "hospital_name": "Hospital Geral de Areias",
            "credits": "Créditos do desenvolvimento: equipe do sistema",
            "logo_path": "",
            "whatsapp_enabled": "1",
            "theme_default": "light",
            "end_of_day_hour": "17",
        }
        for key, value in defaults.items():
            set_setting(key, setting(key, value) or value)

        companies = ["Giga Vida", "White Martins", "Resmedical"]
        for name in companies:
            execute("insert or ignore into companies(name) values(?)", (name,))

        def ensure_user(username, password, display_name, role, company_name=None):
            row = query_one("select id from users where username = ?", (username,))
            if row:
                return
            company_id = None
            if company_name:
                c = query_one("select id from companies where name = ?", (company_name,))
                company_id = c["id"] if c else None
            execute(
                """
                insert into users(username, password_hash, display_name, role, company_id, first_access, created_at)
                values(?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    username,
                    generate_password_hash(password),
                    display_name,
                    role,
                    company_id,
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )

        ensure_user("master", "hgaMaster@2026", "Suporte Master HGA", "master")
        ensure_user("admin", "admin123", "Responsável Patrimônio", "admin")
        ensure_user("empresa1", "123456", "Giga Vida", "company", "Giga Vida")
        ensure_user("empresa2", "123456", "White Martins", "company", "White Martins")
        ensure_user("empresa3", "123456", "Resmedical", "company", "Resmedical")

    @app.context_processor
    def inject_globals():
        user = current_user()
        return {
            "session_user": user,
            "hospital_name": setting("hospital_name", "Hospital Geral de Areias"),
            "credits": setting("credits", ""),
            "logo_path": setting("logo_path", ""),
            "default_theme": setting("theme_default", "light"),
            "whatsapp_enabled": setting("whatsapp_enabled", "1") == "1",
            "fixed_year": app.config["FIXED_YEAR"],
            "end_of_day_hour": int(setting("end_of_day_hour", "17") or 17),
            "fmt": format_dt,
        }

    @app.route("/")
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

    @app.post("/tickets/new")
    def create_ticket():
        requester = request.form.get("requester_name", "").strip()
        sector = request.form.get("sector", "").strip()
        description = request.form.get("description", "").strip()
        company_choice = request.form.get("company_choice", "").strip()
        company_other = request.form.get("company_other", "").strip()
        phone = request.form.get("requester_phone", "").strip()

        if not requester or not sector or not description or not company_choice:
            flash("Preencha os campos obrigatórios.", "danger")
            return redirect(url_for("home"))
        
        if len(description) < 10:
            flash("Descrição muito curta.", "danger")
            return redirect(url_for("home"))

        company_id = None
        company_other_enc = None
        if company_choice == "other":
            if not company_other:
                flash("Informe o nome da empresa em 'Outros'.", "danger")
                return redirect(url_for("home"))
            company_other_enc = encrypt_text(company_other)
        else:
            row = query_one("select id from companies where id = ?", (company_choice,))
            if not row:
                flash("Empresa inválida.", "danger")
                return redirect(url_for("home"))
            company_id = row["id"]

        execute(
            """
            insert into tickets(protocol, requester_name, requester_phone_enc, sector, description, company_id, company_other_enc, status, deadline_iso, created_at, closed_at)
            values(?, ?, ?, ?, ?, ?, ?, 'ABERTO', null, ?, null)
            """,
            (
                next_protocol(),
                requester,
                encrypt_text(phone) if phone else None,
                sector,
                description,
                company_id,
                company_other_enc,
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )

        protocol = row["protocol"]
        return redirect(url_for("home", protocol=protocol))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = query_one("select * from users where username = ?", (username,))
            if not user or not check_password_hash(user["password_hash"], password):
                flash("Usuário ou senha inválidos.", "danger")
                return render_template("login.html")
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        tickets = visible_tickets(user)
        open_count = len([t for t in tickets if t["status"] == "ABERTO"])
        andamento_count = len([t for t in tickets if t["status"] == "EM_ANDAMENTO"])
        concl_count = len([t for t in tickets if t["status"] == "CONCLUIDO"])
        pending_companies = []
        if user["role"] in ("admin", "master"):
            pending_companies = query_all(
                """
                select c.id, c.name,
                sum(case when t.status != 'CONCLUIDO' then 1 else 0 end) as pending_tickets,
                sum(case when o.id is null and t.status != 'CONCLUIDO' then 1 else 0 end) as no_activity
                from companies c
                left join tickets t on t.company_id = c.id
                left join observations o on o.ticket_id = t.id
                group by c.id, c.name
                order by c.name
                """
            )
        return render_template(
            "dashboard.html",
            tickets=tickets,
            open_count=open_count,
            andamento_count=andamento_count,
            concl_count=concl_count,
            pending_companies=pending_companies,
        )

    @app.route("/ticket/<int:ticket_id>", methods=["GET", "POST"])
    @login_required
    def ticket_detail(ticket_id):
        user = current_user()
        ticket = ticket_or_404(ticket_id, user)
        if not ticket:
            flash("Chamado não encontrado.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            if user["role"] != "company":
                flash("Somente empresa pode atualizar andamento.", "danger")
                return redirect(url_for("ticket_detail", ticket_id=ticket_id))
            status = request.form.get("status", "").strip()
            note = request.form.get("note", "").strip()
            deadline_date = request.form.get("deadline_date", "").strip()
            deadline_time = request.form.get("deadline_time", "").strip()
            if status not in {"ABERTO", "EM_ANDAMENTO", "CONCLUIDO"}:
                flash("Atualizar o status é obrigatório.", "danger")
                return redirect(url_for("ticket_detail", ticket_id=ticket_id))
            deadline_iso = None
            if deadline_date and deadline_time:
                try:
                    dt = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    if dt.year != app.config["FIXED_YEAR"]:
                        raise ValueError("Ano inválido")
                    deadline_iso = dt.isoformat(timespec="minutes")
                except Exception:
                    flash(f"O prazo deve usar o ano {app.config['FIXED_YEAR']}.", "danger")
                    return redirect(url_for("ticket_detail", ticket_id=ticket_id))
            closed_at = datetime.utcnow().isoformat(timespec="seconds") if status == "CONCLUIDO" else None
            execute(
                "update tickets set status = ?, deadline_iso = ?, closed_at = ? where id = ?",
                (status, deadline_iso, closed_at, ticket_id),
            )
            execute(
                "insert into observations(ticket_id, user_id, status_after, note, created_at) values(?, ?, ?, ?, ?)",
                (ticket_id, user["id"], status, note, datetime.utcnow().isoformat(timespec="seconds")),
            )
            flash("Chamado atualizado.", "success")
            return redirect(url_for("ticket_detail", ticket_id=ticket_id))

        observations = query_all(
            """
            select o.*, u.display_name from observations o join users u on u.id = o.user_id
            where o.ticket_id = ? order by o.id desc
            """,
            (ticket_id,),
        )
        company_display = ticket["company_name"] or decrypt_text(ticket["company_other_enc"])
        requester_phone = decrypt_text(ticket["requester_phone_enc"])
        whatsapp_link = None
        if setting("whatsapp_enabled", "1") == "1" and requester_phone:
            clean = "".join(ch for ch in requester_phone if ch.isdigit())
            if clean:
                msg = f"Olá, aqui é a empresa responsável pelo chamado {ticket['protocol']}."
                whatsapp_link = f"https://wa.me/{clean}?text={msg.replace(' ', '%20')}"
        return render_template(
            "ticket_detail.html",
            ticket=ticket,
            observations=observations,
            company_display=company_display,
            requester_phone=requester_phone,
            whatsapp_link=whatsapp_link,
        )

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user = current_user()
        full_user = query_one("select * from users where id = ?", (user["id"],))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            display_name = request.form.get("display_name", "").strip()
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            updates = []
            params = []

            if username and username != full_user["username"]:
                exists = query_one("select id from users where username = ? and id != ?", (username, full_user["id"]))
                if exists:
                    flash("Login já está em uso.", "danger")
                    return redirect(url_for("profile"))
                updates.append("username = ?")
                params.append(username)
            if user["role"] in ("master", "admin") and display_name:
                updates.append("display_name = ?")
                params.append(display_name)
            if new_password:
                if not current_password or not check_password_hash(full_user["password_hash"], current_password):
                    flash("Senha atual incorreta.", "danger")
                    return redirect(url_for("profile"))
                updates.append("password_hash = ?")
                params.append(generate_password_hash(new_password))
                updates.append("first_access = 0")
            if updates:
                params.append(full_user["id"])
                execute(f"update users set {', '.join(updates)} where id = ?", tuple(params))
                flash("Perfil atualizado.", "success")
            return redirect(url_for("profile"))
        return render_template("profile.html", full_user=full_user)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    @roles_required("master")
    def settings_view():
        if request.method == "POST":
            hospital_name = request.form.get("hospital_name", "").strip()
            credits = request.form.get("credits", "").strip()
            whatsapp_enabled = "1" if request.form.get("whatsapp_enabled") == "on" else "0"
            end_hour = request.form.get("end_of_day_hour", "17").strip() or "17"
            theme_default = request.form.get("theme_default", "light").strip() or "light"
            if hospital_name:
                set_setting("hospital_name", hospital_name)
            set_setting("credits", credits)
            set_setting("whatsapp_enabled", whatsapp_enabled)
            set_setting("end_of_day_hour", end_hour)
            set_setting("theme_default", theme_default)
            file = request.files.get("logo")
            if file and file.filename:
                ext = Path(file.filename).suffix.lower()
                if ext not in app.config["UPLOAD_EXTENSIONS"]:
                    flash("Formato de logomarca inválido.", "danger")
                    return redirect(url_for("settings_view"))
                filename = secure_filename(f"logo-{uuid4().hex}{ext}")
                save_path = UPLOAD_DIR / filename
                file.save(save_path)
                set_setting("logo_path", f"uploads/{filename}")
            flash("Configurações salvas.", "success")
            return redirect(url_for("settings_view"))
        return render_template("settings.html")

    @app.route("/reports", methods=["GET", "POST"])
    @login_required
    def reports_view():
        user = current_user()
        if request.method == "POST" and user["role"] == "company":
            notes = request.form.get("notes", "").strip()
            execute(
                "insert into reports(company_id, notes, created_at) values(?, ?, ?)",
                (user["company_id"], notes, datetime.utcnow().isoformat(timespec="seconds")),
            )
            flash("Relatório enviado.", "success")
            return redirect(url_for("reports_view"))

        selected_company = request.args.get("company_id", "")
        reports = []
        pending_companies = []
        if user["role"] == "company":
            reports = query_all(
                "select r.*, c.name as company_name from reports r join companies c on c.id = r.company_id where r.company_id = ? order by r.id desc",
                (user["company_id"],),
            )
        else:
            pending_companies = query_all(
                """
                select c.id, c.name,
                sum(case when t.status != 'CONCLUIDO' then 1 else 0 end) as pending_tickets,
                sum(case when o.id is null and t.status != 'CONCLUIDO' then 1 else 0 end) as no_activity
                from companies c
                left join tickets t on t.company_id = c.id
                left join observations o on o.ticket_id = t.id
                group by c.id, c.name
                order by c.name
                """
            )
            sql = "select r.*, c.name as company_name from reports r join companies c on c.id = r.company_id"
            params = []
            if selected_company:
                sql += " where r.company_id = ?"
                params.append(selected_company)
            sql += " order by r.id desc"
            reports = query_all(sql, tuple(params))
        return render_template(
            "reports.html",
            reports=reports,
            pending_companies=pending_companies,
            selected_company=selected_company,
        )

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    with app.app_context():
        init_db()

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)