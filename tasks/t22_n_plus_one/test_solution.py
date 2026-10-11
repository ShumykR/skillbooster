import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from models import Author, Base, Book
from solution import list_authors_with_book_titles


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        for i in range(20):
            a = Author(name=f"author{i}")
            a.books = [Book(title=f"a{i}-b{j}") for j in range(3)]
            s.add(a)
        s.add(Author(name="no-books"))
        s.commit()
    return eng


def count_queries(engine, fn):
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", before)
    try:
        with Session(engine) as s:
            result = fn(s)
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return result, statements


def test_result_is_correct(engine):
    result, _ = count_queries(engine, list_authors_with_book_titles)
    assert len(result) == 21
    assert result["author3"] == ["a3-b0", "a3-b1", "a3-b2"]
    assert result["no-books"] == []


def test_at_most_two_queries(engine):
    _, statements = count_queries(engine, list_authors_with_book_titles)
    assert len(statements) <= 2, f"{len(statements)} запитів замість ≤2 (N+1)"


def test_query_count_does_not_grow_with_data(engine):
    with Session(engine) as s:
        for i in range(20, 60):
            a = Author(name=f"author{i}")
            a.books = [Book(title=f"a{i}-b{j}") for j in range(2)]
            s.add(a)
        s.commit()
    result, statements = count_queries(engine, list_authors_with_book_titles)
    assert len(result) == 61
    assert len(statements) <= 2
