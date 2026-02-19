# Data layer testing guide (SQLAlchemy + Python)

This document explains **how to test the data layer** when using SQLAlchemy as the ORM, including tests for **ORM-based code** and **raw SQL**. It is aimed at developers with a **Java/Spring Boot** background (e.g. `@DataJpaTest`, `@Transactional` rollback) and shows the equivalent patterns in Python with pytest.

---

## 1. Strategy overview

### What you want to achieve

- **Isolate tests**: Each test runs against a known database state; tests do not affect each other.
- **No production data**: Tests use a separate database (in-memory SQLite or a dedicated test DB).
- **Repeatable**: Running tests multiple times gives the same results (deterministic).
- **Fast**: Prefer in-memory SQLite for unit tests when possible; use a real DB only when you need DB-specific behavior (e.g. PostgreSQL).

### Java/Spring vs Python/SQLAlchemy (mental map)

| Java / Spring Boot | Python / SQLAlchemy + pytest |
|--------------------|------------------------------|
| `@DataJpaTest` | Pytest fixture that provides a `Session` bound to an in-memory (or test) engine |
| `@Transactional` (rollback after test) | Session with `session.begin_nested()` (savepoint) or a fresh DB per test |
| `ApplicationContext` / `@Autowired` | Fixtures that create `engine`, `SessionLocal`, and inject `Session` |
| `JpaRepository` / custom repo | Functions or services that take `Session` as an argument (e.g. `load_user(db, user_id)`) |
| H2 / embedded DB for tests | SQLite in-memory (`sqlite:///:memory:`) for speed; optional: real PostgreSQL in CI |

### Recommended approach for this project

1. **Unit tests for data access**: Use an **in-memory SQLite** database. Create tables from `Base.metadata`, optionally seed data, and pass a `Session` into the code under test. Each test can use a fresh DB or a transaction that is rolled back so tests do not leak state.
2. **ORM code**: Test functions that use `select(Model)`, `db.add()`, `db.commit()` by driving them with a test `Session` and asserting on query results or persisted rows.
3. **Raw SQL**: If you use `text(...)` or `connection.execute("SELECT ...")`, test the same way: use a test `Session` (and its connection) so the SQL runs against your in-memory or test DB; assert on the returned rows.
4. **Integration tests** (optional): Use a real database (e.g. PostgreSQL in Docker) when you need to verify DB-specific SQL or behavior; keep these in a separate suite or tag.

---

## 2. Test database setup (fixtures)

You need a **test engine** and a **test session** that do not touch the development or production database.

### 2.1 Overridable settings

Ensure the app can use a different DB URL for tests. This project uses `app.settings.get_settings()` and `resolved_db_url()`. For tests, set the environment variable **before** the engine is created (e.g. in `conftest.py`):

```python
# tests/conftest.py
import os
import pytest

# Force test DB before any app code creates the engine.
os.environ["APP_DB_URL"] = "sqlite:///:memory:"
```

Alternatively, tests can create their own engine and session factory and **never** import the global `app.db.session.engine` for test runs (see below).

### 2.2 Pytest fixtures: engine and session

A common pattern is to define fixtures that create an in-memory engine, create all tables, and provide a session that is closed (and optionally rolled back) after each test. Example:

```python
# tests/conftest.py
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Use in-memory SQLite for tests. Set before app.db.session is imported if you use it.
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def engine():
    """Create a fresh engine for each test (optional: use scope='session' for speed)."""
    return create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

@pytest.fixture
def tables(engine):
    """Create all tables from the ORM metadata."""
    from app.db.base import Base
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture
def db_session(tables):
    """Provide a transactional session; roll back after each test so DB is clean."""
    connection = tables.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False, class_=Session)
    session = SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

**Explanation:**

- **engine**: One engine per test (or per session if you use `scope="session"`). In-memory SQLite is fast and isolated.
- **tables**: Creates all tables defined by your ORM `Base` so you can insert and query.
- **db_session**: Gives the test a `Session`. The `yield` runs the test; after the test, we roll back the transaction so no data persists. This is similar to `@Transactional` rollback in Spring.

If your app code uses a **global** `SessionLocal` (e.g. `from app.db.session import SessionLocal`), you have two options:

- **A)** In tests, **patch** or replace that with the test session factory so the code under test uses the test DB.
- **B)** Avoid importing the global engine/session in code that you want to test in isolation; instead, pass `Session` in (dependency injection). This project already does that for routes (e.g. `get_db`), so in tests you can pass `db_session` into functions that accept `Session`.

---

## 3. Testing ORM-based code

ORM-based code uses SQLAlchemy **models** and **select()** (or legacy `query()`). You test it by controlling the `Session` and the data in the database.

### 3.1 Example: testing a function that loads a user by ID

The app has `load_user(db, user_id)` in `app.security.auth`:

```python
def load_user(db: Session, user_id: int) -> User:
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.department),
            selectinload(User.roles),
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(...)
    return user
```

**Test idea:** Insert a user (and department, roles) in the test DB, call `load_user(db_session, user_id)`, and assert the returned user and relationships.

```python
# tests/test_data_layer/test_auth_data.py
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.security import Department, Role, User
from app.security.auth import load_user


def test_load_user_returns_user_with_department_and_roles(db_session):
    # Arrange: create department, role, user (like init_db does)
    dept = Department(name="IT", code="IT", description="IT Dept")
    db_session.add(dept)
    db_session.flush()

    role = Role(name="admin", description="Admin role")
    db_session.add(role)
    db_session.flush()

    user = User(
        username="testuser",
        email="test@example.com",
        department_id=dept.id,
        is_active=True,
    )
    user.roles.append(role)
    db_session.add(user)
    db_session.commit()

    # Act
    loaded = load_user(db_session, user.id)

    # Assert
    assert loaded.id == user.id
    assert loaded.username == "testuser"
    assert loaded.department is not None
    assert loaded.department.code == "IT"
    assert len(loaded.roles) == 1
    assert loaded.roles[0].name == "admin"


def test_load_user_raises_when_not_found(db_session):
    with pytest.raises(HTTPException) as exc_info:
        load_user(db_session, 99999)
    assert exc_info.value.status_code == 401


def test_load_user_raises_when_inactive(db_session):
    dept = Department(name="IT", code="IT", description="IT")
    db_session.add(dept)
    db_session.flush()
    user = User(
        username="inactive",
        email="inactive@example.com",
        department_id=dept.id,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        load_user(db_session, user.id)
    assert exc_info.value.status_code == 401
```

**Notes:**

- **db_session** is the fixture that provides a `Session` with a rolled-back transaction so each test starts clean.
- You create only the entities needed for the test (department, role, user). This is similar to building entities in a Spring test and using the JPA repository.
- Assert on both the scalar fields and the relationships (`department`, `roles`) to ensure the `selectinload` options behave as expected.

### 3.2 Example: testing a query that lists entities

Suppose you want to test the **data access** behind “list employees” (the actual select and ordering), without going through HTTP. You can test the same `select` logic with a test session:

```python
# tests/test_data_layer/test_employees_data.py
from sqlalchemy import select

from app.models.hr import Employee
from app.models.security import Department


def test_list_employees_ordered_by_id(db_session):
    dept = Department(name="IT", code="IT", description="IT")
    db_session.add(dept)
    db_session.flush()

    e1 = Employee(employee_id="E-1", first_name="A", last_name="B", email="a@b.com", department_id=dept.id)
    e2 = Employee(employee_id="E-2", first_name="C", last_name="D", email="c@d.com", department_id=dept.id)
    db_session.add_all([e1, e2])
    db_session.commit()

    stmt = select(Employee).order_by(Employee.id)
    result = list(db_session.scalars(stmt).all())

    assert len(result) == 2
    assert result[0].employee_id == "E-1"
    assert result[1].employee_id == "E-2"
```

### 3.3 Example: testing init_db / seed logic

If you want to test that `init_db` (or the internal `_seed`) creates the expected structure and rows, use a dedicated engine/session so you don’t touch the real app DB:

```python
# tests/test_data_layer/test_init_db.py
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from app.db.base import Base
from app.db.init_db import init_db, _has_seed_data
from app.models.security import Department, User


def test_init_db_creates_tables_and_seed():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

    # Simulate first run: no seed data yet
    with SessionLocal() as db:
        assert _has_seed_data(db) is False

    # Run init_db (it will seed because _has_seed_data was False)
    init_db()

    with SessionLocal() as db:
        assert _has_seed_data(db) is True
        depts = list(db.scalars(select(Department)).all())
        assert len(depts) >= 1
        users = list(db.scalars(select(User)).all())
        assert len(users) >= 1
```

**Caveat:** If `init_db()` uses the **global** `engine` from `app.db.session`, you must either patch that engine with the in-memory one for this test or refactor `init_db` to accept an optional engine/session. The example above assumes you can run `init_db()` against the in-memory DB (e.g. by temporarily setting `APP_DB_URL` and reinitializing the app’s engine, or by passing an engine into `init_db` if you add that parameter).

---

## 4. Testing raw SQL

When you have code that runs **raw SQL** (e.g. `text("SELECT ...")` or `connection.execute("...")`), you still use the same idea: run it against a test database and assert on results.

### 4.1 Running raw SQL with SQLAlchemy

SQLAlchemy runs raw SQL via `text()` and the session or connection:

```python
from sqlalchemy import text

# With a Session (same connection as ORM)
result = db_session.execute(text("SELECT id, name FROM departments WHERE code = :code"), {"code": "IT"})
rows = result.fetchall()
```

### 4.2 Example: testing a function that uses raw SQL

A runnable example lives in **`tests/test_data_layer/test_raw_sql_example.py`**: it defines `get_department_user_counts(db)` (raw SQL) and tests it with the `db_session` fixture.

Suppose you have a small data access function that uses raw SQL:

```python
# Example: app/db/reports.py (hypothetical)
from sqlalchemy import text
from sqlalchemy.orm import Session

def get_department_stats_raw(db: Session) -> list[dict]:
    result = db.execute(text("""
        SELECT d.code, COUNT(u.id) AS user_count
        FROM departments d
        LEFT JOIN users u ON u.department_id = d.id
        GROUP BY d.id, d.code
    """))
    return [{"code": row.code, "user_count": row.user_count} for row in result]
```

**Test:** Use the same `db_session` fixture, insert departments and users via ORM (or raw SQL), then call the function and assert on the returned list:

```python
# tests/test_data_layer/test_reports.py
from app.db.reports import get_department_stats_raw
from app.models.security import Department, User


def test_get_department_stats_raw(db_session):
    hr = Department(name="HR", code="HR", description="HR")
    it = Department(name="IT", code="IT", description="IT")
    db_session.add_all([hr, it])
    db_session.flush()

    u1 = User(username="u1", email="u1@x.com", department_id=hr.id, is_active=True)
    u2 = User(username="u2", email="u2@x.com", department_id=hr.id, is_active=True)
    u3 = User(username="u3", email="u3@x.com", department_id=it.id, is_active=True)
    db_session.add_all([u1, u2, u3])
    db_session.commit()

    stats = get_department_stats_raw(db_session)

    assert len(stats) == 2
    codes = {s["code"] for s in stats}
    assert "HR" in codes
    assert "IT" in codes
    by_code = {s["code"]: s["user_count"] for s in stats}
    assert by_code["HR"] == 2
    assert by_code["IT"] == 1
```

**Points:**

- The test DB is populated with known data (ORM or raw INSERT).
- You call the **same** function that runs raw SQL; it uses the test `Session`, so the SQL runs against the in-memory DB.
- You assert on the structure and values of the result. No need to assert on the SQL string itself; behavior is what matters.

### 4.3 Raw SQL and SQLite vs PostgreSQL

If your raw SQL uses database-specific features (e.g. PostgreSQL `jsonb`), in-memory SQLite may not run it. Options:

- Use **pytest markers** to skip raw-SQL tests on SQLite, or
- Run those tests only when a real PostgreSQL (or target DB) is available (e.g. in CI with a test container).

---

## 5. Fixture design choices

| Approach | Pros | Cons |
|----------|------|------|
| **Rollback after each test** | No need to recreate tables; fast. | Same connection/transaction for the whole test; some edge cases (e.g. nested transactions) may differ. |
| **New in-memory DB per test** | Maximum isolation; each test starts with empty schema. | Slightly slower (create_all per test). |
| **Session-scoped engine, function-scoped session with rollback** | Good balance: one engine, clean state per test. | Requires discipline to not hold state in the session across tests. |

For this project, **function-scoped session with rollback** (as in the `db_session` fixture above) is a good default. Use a **session-scoped engine** if you want to avoid creating the engine many times:

```python
@pytest.fixture(scope="session")
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

@pytest.fixture(scope="session")
def tables(engine):
    from app.db.base import Base
    Base.metadata.create_all(bind=engine)
    return engine
```

---

## 6. Running the tests

From the project root:

```bash
pytest tests/ -v
# or only data-layer tests
pytest tests/test_data_layer/ -v
```

Example tests included in this project:

- **`tests/conftest.py`** — Defines `engine`, `tables`, and `db_session` fixtures.
- **`tests/test_data_layer/test_auth_data.py`** — Tests `load_user()` (ORM, with relationships).
- **`tests/test_data_layer/test_employees_data.py`** — Tests a `select(Employee).order_by(...)` query.
- **`tests/test_data_layer/test_raw_sql_example.py`** — Tests a function that uses `text(...)` raw SQL.

To use the fixtures, the test modules must be under `tests/` and the fixtures must be visible (e.g. in `tests/conftest.py`). Ensure `pythonpath = ["."]` in `pyproject.toml` (or set `PYTHONPATH`) so that `app` can be imported.

---

## 7. Summary

- **Strategy**: Use an in-memory SQLite (or a dedicated test DB) and a `Session` provided by pytest fixtures. Roll back the transaction after each test so tests are independent.
- **ORM**: Test functions that take `Session` by inserting data with the ORM, calling the function, and asserting on returned entities or query results.
- **Raw SQL**: Same idea: feed the same test `Session` into the code that runs `text(...)` or `execute(...)`, prepare data (ORM or raw), then assert on the function’s return value or side effects.
- **Java comparison**: The test `Session` is like the transactional context in `@DataJpaTest`; the fixture is like the Spring test context that provides the repository. You “arrange” with adds/commits, “act” by calling your data layer function, and “assert” on results.

This gives you a clear, maintainable strategy for testing both ORM and raw SQL in the data layer.
