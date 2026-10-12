"""Працює, але все в одній купі: HTTP, бізнес-правила, SQL і конфіг разом.

Твоє завдання: розкласти це на шари (див. README) і НЕ зламати поведінку.
"""

import os
import sqlite3

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class NoteIn(BaseModel):
    title: str
    body: str = ""


def create_app() -> FastAPI:
    db_path = os.getenv("NOTES_DATABASE_PATH", "notes.db")

    def connect() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE IF NOT EXISTS notes "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL)"
        )
        return conn

    app = FastAPI()

    @app.post("/notes", status_code=201)
    def create_note(payload: NoteIn):
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title must not be blank")
        conn = connect()
        cur = conn.execute("INSERT INTO notes (title, body) VALUES (?, ?)", (title, payload.body))
        conn.commit()
        note = {"id": cur.lastrowid, "title": title, "body": payload.body}
        conn.close()
        return note

    @app.get("/notes")
    def list_notes():
        conn = connect()
        rows = [dict(r) for r in conn.execute("SELECT id, title, body FROM notes ORDER BY id")]
        conn.close()
        return rows

    @app.get("/notes/{note_id}")
    def get_note(note_id: int):
        conn = connect()
        row = conn.execute("SELECT id, title, body FROM notes WHERE id = ?", (note_id,)).fetchone()
        conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="note not found")
        return dict(row)

    return app
