"""Shared fixtures.

The pure-unit tests need nothing from here. The integration tests (anything
marked `requires_db`) need a real Postgres, because the schema uses Postgres
enums, `to_char`, JSON columns and a trigram index that SQLite cannot stand in
for. They are skipped automatically when no database is reachable, so a
developer without Postgres still gets a green unit-test run, while CI — which
provisions the service — runs the full set.

Point them at a database with TEST_DATABASE_URL; it defaults to a local
`partner_portal_test`. The schema is created once per session with
`alembic upgrade head`, so the migration chain itself is exercised on every CI
run rather than being assumed to work.
"""
import asyncio
import os
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/partner_portal_test",
)

# Set before anything imports app.core.config, which reads DATABASE_URL once at
# import time and hands it straight to create_async_engine. A fixture would be
# too late: pytest imports conftest first, but the test modules that import the
# app come next, well before any fixture runs. Unconditional on purpose — a
# test run must never be able to reach a developer's real database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def _database_reachable(url: str) -> bool:
    """Cheap pre-flight so the whole integration suite skips cleanly rather
    than erroring dozens of times with the same connection failure."""
    import asyncpg

    async def _probe() -> bool:
        dsn = url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            conn = await asyncio.wait_for(asyncpg.connect(dsn), timeout=5)
        except Exception:
            return False
        await conn.close()
        return True

    try:
        return asyncio.new_event_loop().run_until_complete(_probe())
    except Exception:
        return False


_DB_AVAILABLE: bool | None = None


def db_available() -> bool:
    global _DB_AVAILABLE
    if _DB_AVAILABLE is None:
        _DB_AVAILABLE = _database_reachable(TEST_DATABASE_URL)
    return _DB_AVAILABLE


requires_db = pytest.mark.skipif(
    not db_available(),
    reason=(
        "no test database reachable — set TEST_DATABASE_URL to run the "
        "integration suite (CI provisions one)"
    ),
)


@pytest.fixture(scope="session")
def _schema() -> None:
    """Create the schema once, by running the real migration chain."""
    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(autouse=True)
async def _fresh_pool() -> AsyncIterator[None]:
    """Drop the connection pool between tests.

    app.core.database builds one engine at import time, and pytest-asyncio
    gives each test its own event loop. A pooled asyncpg connection is bound to
    the loop that opened it, so the second test to run would reuse a connection
    from the first test's loop and die on "attached to a different loop".
    Disposing after each test costs a reconnect and removes the whole class of
    problem.

    autouse so it applies to any test that touches the database, whether
    through `db` or through `client`; declared before them so it tears down
    last, once both have returned their connections.
    """
    yield
    if not db_available():
        return

    from app.core.database import engine
    from app.core.redis import redis_client

    await engine.dispose()
    # Redis has the identical problem: one client built at import time, whose
    # pooled connections belong to whichever loop first used them. The token
    # blacklist check in get_current_user hits it on every authenticated
    # request, so a stale pool fails the request rather than the assertion.
    await redis_client.connection_pool.disconnect()


@pytest_asyncio.fixture
async def db(_schema) -> AsyncIterator:
    """A session against the test database.

    Fixture data must be committed before it is visible to the `client`
    fixture, which runs the app's own get_db session — the world-building
    helpers below flush but never commit, so tests call `await db.commit()`
    once their world is built.
    """
    from app.core.database import async_session_factory

    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(_schema) -> AsyncIterator:
    """The real FastAPI app, driven in-process over ASGI (no network).

    Deliberately without the lifespan: startup seeds a superadmin and warms
    caches, none of which these tests want. Every route and dependency is the
    production one.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# World-building helpers
# ---------------------------------------------------------------------------

PASSWORD = "Fixture@12345"


def unique(prefix: str) -> str:
    """Tests share one database across a session, so names and emails have to
    be unique per test rather than per run."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def make_user(db, *, role, company_id=None, is_superadmin=False, email=None):
    from app.core.security import hash_password
    from app.models.user import User, UserStatus

    user = User(
        full_name=f"Test {role.value}",
        # example.com, not .test: email-validator rejects reserved TLDs.
        email=email or f"{unique('u')}@fixture.example.com",
        password_hash=hash_password(PASSWORD),
        role=role,
        status=UserStatus.ACTIVE,
        company_id=company_id,
        is_superadmin=is_superadmin,
    )
    db.add(user)
    await db.flush()
    return user


async def make_company(db, *, channel_manager_id, company_type=None,
                       parent_distributor_id=None, name=None, tier=None):
    from app.models.company import Company, CompanyStatus, CompanyType, PartnerTier

    company = Company(
        name=name or unique("Co"),
        country="US",
        region="NA",
        city="Austin",
        industry="Tech",
        contact_email=f"{unique('c')}@fixture.example.com",
        status=CompanyStatus.ACTIVE,
        tier=tier or PartnerTier.SILVER,
        channel_manager_id=channel_manager_id,
        company_type=company_type or CompanyType.PARTNER,
        parent_distributor_id=parent_distributor_id,
    )
    db.add(company)
    await db.flush()
    return company


async def make_opportunity(db, *, company_id, submitted_by, name=None, status=None):
    from datetime import date
    from decimal import Decimal

    from app.models.opportunity import Opportunity, OpportunityStatus
    from app.utils.customer_normalize import normalize_customer_name

    customer = unique("Customer")
    opp = Opportunity(
        name=name or unique("Opp"),
        customer_name=customer,
        customer_name_normalized=normalize_customer_name(customer),
        region="NA",
        country="US",
        city="Austin",
        worth=Decimal("50000.00"),
        closing_date=date(2027, 6, 30),
        requirements="Fixture opportunity",
        status=status or OpportunityStatus.PENDING_REVIEW,
        submitted_by=submitted_by,
        company_id=company_id,
    )
    db.add(opp)
    await db.flush()
    return opp


def auth_header(user) -> dict:
    """An Authorization header for this user, minted the same way
    auth_service.login mints one.

    Deliberately not a POST to /auth/login. These tests are about
    authorisation, not authentication, and a single test can need five or six
    identities — /auth/login is rate-limited to 10 requests a minute per IP,
    and every in-process request arrives from 127.0.0.1, so real logins would
    make the suite fail on its own volume rather than on anything it tests.
    The token still goes through the real decode, blacklist and user lookup in
    deps.get_current_user, so nothing about the auth path is stubbed out.
    """
    from app.core.security import create_access_token

    token_data = {"sub": str(user.id), "role": user.role.value}
    if user.company_id:
        token_data["company_id"] = user.company_id
    return {"Authorization": f"Bearer {create_access_token(token_data)}"}


async def make_poc(db, *, opportunity_id, status=None, start_date=None):
    """A started POC by default.

    start_date and vm_provisioning_completed_at move together on purpose: the
    POC *starts* when the VM is allocated, and the service refuses to close
    one whose vm_provisioning_completed_at is null however its status column
    reads. Pass start_date=None explicitly for a not-yet-started POC.
    """
    from datetime import date

    from app.models.poc import Poc, PocStatus

    if start_date is None and (status or PocStatus.RUNNING) != PocStatus.NOT_STARTED:
        start_date = date(2026, 8, 1)

    poc = Poc(
        opportunity_id=opportunity_id,
        status=status or PocStatus.RUNNING,
        start_date=start_date,
        vm_provisioning_completed_at=start_date,
    )
    db.add(poc)
    await db.flush()
    return poc


async def make_team_member(db, *, poc_id, user_id, role, assigned_by=None):
    from app.models.poc_team import PocTeamMember

    member = PocTeamMember(
        poc_id=poc_id, user_id=user_id, role=role, assigned_by=assigned_by
    )
    db.add(member)
    await db.flush()
    return member


async def login(client, email: str) -> dict:
    """A real POST to /auth/login. Use only where the login flow itself is
    what's under test — auth_header is the cheap path everywhere else."""
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
