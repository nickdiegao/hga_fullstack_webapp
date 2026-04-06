import sqlite3
from flask import g
from pathlib import Path

DB_PATH = Path("instance/app.db")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()

def query_all(sql, params=()):
    return get_db().execute(sql, params).fetchall()

def execute(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur

def init_db():
    db = get_db()

    db.executescript("""
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
        created_at text not null
    );

    create table if not exists tickets (
        id integer primary key autoincrement,
        protocol text not null,
        requester_name text not null,
        sector text not null,
        description text not null,
        company_id integer,
        status text not null,
        created_at text not null
    );

    create table if not exists observations (
        id integer primary key autoincrement,
        ticket_id integer,
        user_id integer,
        status_after text,
        note text,
        created_at text
    );

    create table if not exists reports (
        id integer primary key autoincrement,
        company_id integer,
        notes text,
        created_at text
    );
    """)

    db.commit()