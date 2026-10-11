"""Завдання №22: N+1 запит у SQLAlchemy.

Функція повертає {імʼя автора: [назви книг]} для ВСІХ авторів.
Результат правильний, але на 20 авторів робиться 21 запит. Виправ так,
щоб запитів було не більше двох незалежно від кількості авторів.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Author


def list_authors_with_book_titles(session: Session) -> dict[str, list[str]]:
    authors = session.scalars(select(Author).order_by(Author.id)).all()
    return {a.name: [b.title for b in a.books] for a in authors}
