import sqlite3
import hashlib
import os
import re
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT    NOT NULL UNIQUE,
                email      TEXT    NOT NULL UNIQUE,
                password   TEXT    NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                filename     TEXT    NOT NULL,
                file_type    TEXT    NOT NULL,
                file_data    BLOB    NOT NULL,
                raw_text     TEXT,
                final_data   TEXT,
                conditions   TEXT,
                summary      TEXT,
                uploaded_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return False, "Enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username.strip(), email.strip().lower(), _hash(password))
            )
            conn.commit()
        return True, "Account created successfully."
    except sqlite3.IntegrityError as e:
        if "username" in str(e):
            return False, "Username already taken."
        if "email" in str(e):
            return False, "Email already registered."
        return False, "Registration failed."


def login_user(identifier: str, password: str) -> tuple[bool, str, dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?",
            (identifier.strip(), identifier.strip().lower(), _hash(password))
        ).fetchone()
    if row:
        return True, "Login successful.", {"id": row["id"], "username": row["username"], "email": row["email"]}
    return False, "Invalid credentials. Please try again.", {}


def save_report(user_id: int, filename: str, file_type: str, file_data: bytes,
                raw_text: str, final_data: dict, conditions: list, summary: str) -> int:
    with _get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reports (user_id, filename, file_type, file_data, raw_text, final_data, conditions, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, filename, file_type, file_data,
             raw_text, json.dumps(final_data), json.dumps(conditions), summary)
        )
        conn.commit()
        return cur.lastrowid


def get_user_reports(user_id: int) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, filename, file_type, conditions, summary, uploaded_at, final_data FROM reports WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user_id,)
        ).fetchall()
    result = []
    for r in rows:
        conditions = json.loads(r["conditions"]) if r["conditions"] else []
        final_data = json.loads(r["final_data"]) if r["final_data"] else {}
        result.append({
            "id": r["id"],
            "filename": r["filename"],
            "file_type": r["file_type"],
            "conditions": conditions,
            "summary": r["summary"],
            "uploaded_at": r["uploaded_at"],
            "final_data": final_data,
        })
    return result


def get_report_by_id(report_id: int, user_id: int) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ? AND user_id = ?",
            (report_id, user_id)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "filename": row["filename"],
        "file_type": row["file_type"],
        "file_data": row["file_data"],
        "raw_text": row["raw_text"],
        "final_data": json.loads(row["final_data"]) if row["final_data"] else {},
        "conditions": json.loads(row["conditions"]) if row["conditions"] else [],
        "summary": row["summary"],
        "uploaded_at": row["uploaded_at"],
    }


def delete_report(report_id: int, user_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM reports WHERE id = ? AND user_id = ?",
            (report_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
