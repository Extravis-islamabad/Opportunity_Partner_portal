"""QA round: identity, users, auth and MFA.

Each class pins one reported bug. The weighting is towards what an attacker or
a careless edit could do — a profile save wiping fields, a deactivation that
skipped its own rules, a password change that left the old sessions alive —
rather than towards the happy paths, which already had coverage.
"""
import pyotp
import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.opportunity import OpportunityStatus
from app.models.user import User, UserRole, UserStatus
from tests.conftest import (
    PASSWORD,
    auth_header,
    make_company,
    make_opportunity,
    make_user,
    requires_db,
    unique,
)
from tests.test_mfa import code_at, enrol

pytestmark = requires_db
asyncio_test = pytest.mark.asyncio


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.manager = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.manager.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    await db.commit()
    return w


async def _reload(db, pk):
    row = (await db.execute(select(User).where(User.id == pk))).scalar_one()
    await db.refresh(row)
    return row


@pytest.fixture(autouse=True)
def _no_mail(monkeypatch):
    """Nothing here is about mail; keep it off the wire."""
    async def _fake(**kwargs):
        return True

    for target in (
        "app.services.partner_service.send_template_email",
        "app.services.auth_service.send_template_email",
    ):
        monkeypatch.setattr(target, _fake)


async def _login(client, email, password=PASSWORD):
    return await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def _refresh(client, refresh_token):
    # The cookie is Secure outside development, so httpx would not send it
    # back over http://test on its own; pass it explicitly.
    return await client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"refresh_token={refresh_token}"}
    )


async def _audit_actions(db, user_id):
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.entity_type == "user", AuditLog.entity_id == user_id)
    )).scalars().all()
    return [(r.metadata_json or {}).get("action") for r in rows]


# ---------------------------------------------------------------------------
# 1. Profile updates apply only what was sent
# ---------------------------------------------------------------------------

class TestProfileUpdate:
    pytestmark = asyncio_test

    async def test_phone_alone_does_not_touch_the_name(self, client, db):
        w = await build(db)
        r = await client.put(
            "/api/v1/users/me/profile", headers=auth_header(w.partner), json={"phone": "1"}
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["phone"] == "1"
        assert r.json()["full_name"] == w.partner.full_name

    async def test_saving_a_job_title_keeps_phone_and_department(self, client, db):
        w = await build(db)
        w.partner.phone = "+1 555 0100"
        w.partner.department = "Sales"
        await db.commit()

        r = await client.put(
            "/api/v1/users/me/profile",
            headers=auth_header(w.partner),
            json={"job_title": "Director", "full_name": "Renamed Person"},
        )
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert body["job_title"] == "Director"
        assert body["full_name"] == "Renamed Person"
        assert body["phone"] == "+1 555 0100"
        assert body["department"] == "Sales"

    @pytest.mark.parametrize("bad", [None, "", "   "])
    async def test_an_empty_name_is_refused(self, client, db, bad):
        w = await build(db)
        r = await client.put(
            "/api/v1/users/me/profile", headers=auth_header(w.partner), json={"full_name": bad}
        )
        assert r.status_code == 422, r.text[:300]

    async def test_admin_edit_also_refuses_a_null_name(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"full_name": None},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 2. Real client IP behind the proxy
# ---------------------------------------------------------------------------

class TestClientIp:
    pytestmark = asyncio_test

    async def _seen_by_app(self, peer, xff):
        """Run one request through uvicorn's proxy-headers middleware with the
        trust list the deployment uses, and report the client address the app
        (and so slowapi's key function) sees."""
        from starlette.requests import Request
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        from app.core.rate_limit import client_ip

        seen = {}

        async def app(scope, receive, send):
            seen["ip"] = client_ip(Request(scope))

        mw = ProxyHeadersMiddleware(app, trusted_hosts="172.16.0.0/12,192.168.0.0/16,127.0.0.1")
        headers = [(b"x-forwarded-for", xff.encode())] if xff else []
        await mw({"type": "http", "client": (peer, 1234), "headers": headers}, None, None)
        return seen["ip"]

    async def test_the_client_behind_nginx_is_seen(self):
        assert await self._seen_by_app("172.23.0.7", "203.0.113.9") == "203.0.113.9"

    async def test_a_forged_header_from_the_client_is_ignored(self):
        # nginx appends the real peer; whatever the client wrote sits to its left.
        assert await self._seen_by_app("172.23.0.7", "1.2.3.4, 203.0.113.9") == "203.0.113.9"

    async def test_an_untrusted_peer_cannot_set_its_address(self):
        assert await self._seen_by_app("203.0.113.50", "1.2.3.4") == "203.0.113.50"

    async def test_a_host_tls_proxy_through_the_gateway(self):
        assert await self._seen_by_app("172.23.0.7", "198.51.100.4, 172.23.0.1") == "198.51.100.4"


# ---------------------------------------------------------------------------
# 3. Staff accounts cannot be attached to a company
# ---------------------------------------------------------------------------

class TestCreateUserCompany:
    pytestmark = asyncio_test

    @pytest.mark.parametrize("role", ["admin", "sales_rep"])
    async def test_staff_with_a_company_is_refused(self, client, db, role):
        w = await build(db)
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "Staff", "email": f"{unique('s')}@fixture.example.com",
                  "role": role, "company_id": w.company.id},
        )
        assert r.status_code == 400, r.text[:300]
        assert r.json()["code"] == "COMPANY_NOT_ALLOWED"

    async def test_a_missing_company_id_for_a_rep_is_not_a_500(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "Rep", "email": f"{unique('s')}@fixture.example.com",
                  "role": "sales_rep", "company_id": 99999999},
        )
        assert r.status_code == 400

    async def test_a_partner_needs_a_real_company(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "P", "email": f"{unique('p')}@fixture.example.com",
                  "role": "partner", "company_id": 99999999},
        )
        assert r.status_code == 404

    async def test_staff_without_a_company_is_fine(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "Rep", "email": f"{unique('s')}@fixture.example.com",
                  "role": "sales_rep"},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["company_id"] is None


# ---------------------------------------------------------------------------
# 4 & 8. Status changes go through the deactivate / reactivate rules
# ---------------------------------------------------------------------------

class TestStatusChanges:
    pytestmark = asyncio_test

    async def test_put_inactive_is_refused_while_work_is_held(self, client, db):
        w = await build(db)
        await make_opportunity(
            db, company_id=w.company.id, submitted_by=w.partner.id,
            status=OpportunityStatus.PENDING_REVIEW,
        )
        await db.commit()

        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"status": "inactive", "job_title": "Leaving"},
        )
        assert r.status_code == 409, r.text[:300]
        assert r.json()["code"] == "HANDOVER_REQUIRED"
        # Nothing from the refused request sticks, the field edit included.
        user = await _reload(db, w.partner.id)
        assert user.status == UserStatus.ACTIVE
        assert user.job_title != "Leaving"

    async def test_put_inactive_deactivates_and_mails(self, client, db, monkeypatch):
        w = await build(db)
        mails = []

        async def _capture(**kwargs):
            mails.append(kwargs)
            return True

        monkeypatch.setattr("app.services.partner_service.send_template_email", _capture)
        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"status": "inactive"},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "inactive"
        assert [m["template_name"] for m in mails] == ["suspension"]

    async def test_put_with_the_current_status_is_a_no_op(self, client, db, monkeypatch):
        w = await build(db)
        mails = []

        async def _capture(**kwargs):
            mails.append(kwargs)
            return True

        monkeypatch.setattr("app.services.partner_service.send_template_email", _capture)
        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"status": "active", "job_title": "Same status"},
        )
        assert r.status_code == 200
        assert r.json()["job_title"] == "Same status"
        assert mails == []

    async def test_a_pending_invite_cannot_be_reactivated(self, client, db):
        w = await build(db)
        w.partner.status = UserStatus.PENDING_ACTIVATION
        await db.commit()

        r = await client.post(
            f"/api/v1/users/{w.partner.id}/reactivate", headers=auth_header(w.manager)
        )
        assert r.status_code == 409
        assert r.json()["code"] == "ACCOUNT_NOT_ACTIVATED"

        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"status": "active"},
        )
        assert r.status_code == 409
        assert (await _reload(db, w.partner.id)).status == UserStatus.PENDING_ACTIVATION

    async def test_reactivating_an_inactive_user_still_works(self, client, db):
        w = await build(db)
        w.partner.status = UserStatus.INACTIVE
        await db.commit()
        r = await client.post(
            f"/api/v1/users/{w.partner.id}/reactivate", headers=auth_header(w.manager)
        )
        assert r.status_code == 200
        assert (await _reload(db, w.partner.id)).status == UserStatus.ACTIVE


# ---------------------------------------------------------------------------
# 5 & 12. Password changes end the other sessions, and are audited
# ---------------------------------------------------------------------------

class TestPasswordChangeEndsSessions:
    pytestmark = asyncio_test

    async def test_change_password_revokes_refresh_and_issues_a_new_session(self, client, db):
        w = await build(db)
        login = await _login(client, w.partner.email)
        assert login.status_code == 200, login.text[:300]
        old_access = login.json()["access_token"]
        old_refresh = login.cookies.get("refresh_token")
        assert (await _refresh(client, old_refresh)).status_code == 200

        r = await client.post(
            "/api/v1/auth/change-password", headers=_bearer(old_access),
            json={"current_password": PASSWORD, "new_password": "Brand-New@123"},
        )
        assert r.status_code == 200, r.text[:300]
        new_access = r.json()["access_token"]
        new_refresh = r.cookies.get("refresh_token")

        assert (await _refresh(client, old_refresh)).status_code == 401
        assert (await _refresh(client, new_refresh)).status_code == 200
        me = await client.get("/api/v1/auth/me", headers=_bearer(new_access))
        assert me.status_code == 200

        await db.commit()
        assert "password_changed" in await _audit_actions(db, w.partner.id)

    async def test_old_access_tokens_are_stale_after_a_change(self, client, db):
        from app.core.security import access_token_is_current, decode_token

        w = await build(db)
        old_access = (await _login(client, w.partner.email)).json()["access_token"]
        assert await access_token_is_current(decode_token(old_access))

        r = await client.post(
            "/api/v1/auth/change-password", headers=_bearer(old_access),
            json={"current_password": PASSWORD, "new_password": "Brand-New@123"},
        )
        assert r.status_code == 200
        assert not await access_token_is_current(decode_token(old_access))
        assert await access_token_is_current(decode_token(r.json()["access_token"]))

    async def test_old_access_token_is_refused_by_the_api(self, client, db):
        w = await build(db)
        old_access = (await _login(client, w.partner.email)).json()["access_token"]
        await client.post(
            "/api/v1/auth/change-password", headers=_bearer(old_access),
            json={"current_password": PASSWORD, "new_password": "Brand-New@123"},
        )
        r = await client.get("/api/v1/auth/me", headers=_bearer(old_access))
        assert r.status_code == 401

    async def test_reset_password_revokes_and_is_audited(self, client, db):
        w = await build(db)
        login = await _login(client, w.partner.email)
        old_refresh = login.cookies.get("refresh_token")

        await client.post("/api/v1/auth/forgot-password", json={"email": w.partner.email})
        await db.commit()
        token = (await _reload(db, w.partner.id)).reset_token
        assert token

        r = await client.post(
            "/api/v1/auth/reset-password", json={"token": token, "new_password": "Reset-New@123"}
        )
        assert r.status_code == 200, r.text[:300]
        assert (await _refresh(client, old_refresh)).status_code == 401
        await db.commit()
        assert "password_reset" in await _audit_actions(db, w.partner.id)

    async def test_refresh_refuses_a_deactivated_account(self, client, db):
        w = await build(db)
        refresh = (await _login(client, w.partner.email)).cookies.get("refresh_token")
        w.partner.status = UserStatus.INACTIVE
        await db.commit()
        r = await _refresh(client, refresh)
        assert r.status_code == 401
        assert r.json()["code"] == "ACCOUNT_INACTIVE"


class TestLockout:
    pytestmark = asyncio_test

    async def test_failed_passwords_lock_and_are_audited(self, client, db, monkeypatch):
        from app.core.config import settings

        # Under the 10-a-minute login rate limit, whatever the env configures.
        monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
        w = await build(db)
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            r = await _login(client, w.partner.email, "wrong-password")
            assert r.status_code == 401
        user = await _reload(db, w.partner.id)
        # The counter used to be rolled back with the failed request, so the
        # lock never happened.
        assert user.status == UserStatus.LOCKED
        assert "account_locked" in await _audit_actions(db, w.partner.id)

        r = await _login(client, w.partner.email)
        assert r.json()["code"] == "ACCOUNT_LOCKED"


# ---------------------------------------------------------------------------
# 6. MFA hardening
# ---------------------------------------------------------------------------

class TestMfaHardening:
    pytestmark = asyncio_test

    async def test_turning_mfa_off_needs_a_code(self, client, db):
        w = await build(db)
        await enrol(client, db, w.manager)
        r = await client.delete("/api/v1/mfa", headers=auth_header(w.manager))
        assert r.status_code == 422

        r = await client.request(
            "DELETE", "/api/v1/mfa", headers=auth_header(w.manager), json={"code": "000000"}
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_MFA_CODE"
        assert (await client.get("/api/v1/mfa/status", headers=auth_header(w.manager))).json()["enabled"]

    async def test_a_recovery_code_turns_it_off(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.manager)
        r = await client.request(
            "DELETE", "/api/v1/mfa", headers=auth_header(w.manager), json={"code": codes[0]}
        )
        assert r.status_code == 200, r.text[:300]
        assert not (await client.get("/api/v1/mfa/status", headers=auth_header(w.manager))).json()["enabled"]

    async def test_a_challenge_is_spent_by_its_login(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.manager)
        challenge = (await _login(client, w.manager.email)).json()["challenge_token"]

        first = await client.post(
            "/api/v1/auth/login/mfa", json={"challenge_token": challenge, "code": codes[0]}
        )
        assert first.status_code == 200, first.text[:300]
        again = await client.post(
            "/api/v1/auth/login/mfa", json={"challenge_token": challenge, "code": codes[1]}
        )
        assert again.status_code == 401
        assert again.json()["code"] == "INVALID_MFA_CHALLENGE"

    async def test_a_typo_does_not_spend_the_challenge(self, client, db):
        w = await build(db)
        secret, _ = await enrol(client, db, w.manager)
        challenge = (await _login(client, w.manager.email)).json()["challenge_token"]
        bad = await client.post(
            "/api/v1/auth/login/mfa", json={"challenge_token": challenge, "code": "000000"}
        )
        assert bad.status_code == 401
        good = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": code_at(secret, windows_ahead=1)},
        )
        assert good.status_code == 200, good.text[:300]

    async def test_failed_codes_count_towards_the_lockout(self, client, db, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
        w = await build(db)
        await enrol(client, db, w.manager)
        challenge = (await _login(client, w.manager.email)).json()["challenge_token"]
        for _ in range(settings.LOGIN_MAX_ATTEMPTS):
            await client.post(
                "/api/v1/auth/login/mfa", json={"challenge_token": challenge, "code": "000000"}
            )
        user = await _reload(db, w.manager.id)
        assert user.status == UserStatus.LOCKED
        assert "account_locked" in await _audit_actions(db, w.manager.id)


# ---------------------------------------------------------------------------
# 7. Emails are case-insensitive
# ---------------------------------------------------------------------------

class TestEmailCase:
    pytestmark = asyncio_test

    async def test_an_upper_case_duplicate_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "Dup", "email": w.partner.email.upper(),
                  "role": "partner", "company_id": w.company.id},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "EMAIL_EXISTS"

    async def test_new_accounts_are_stored_lower_case(self, client, db):
        w = await build(db)
        email = f"{unique('Mixed')}@Fixture.Example.com"
        r = await client.post(
            "/api/v1/users", headers=auth_header(w.superadmin),
            json={"full_name": "Mixed", "email": email, "role": "sales_rep"},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["email"] == email.lower()

    async def test_team_duplicate_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users/team", headers=auth_header(w.partner),
            json={"full_name": "Dup", "email": w.partner.email.upper(), "contact": "1",
                  "designation": "Eng", "department": "R&D"},
        )
        assert r.status_code == 409

    async def test_login_ignores_case(self, client, db):
        w = await build(db)
        r = await _login(client, w.partner.email.upper())
        assert r.status_code == 200, r.text[:300]

    async def test_a_legacy_mixed_case_row_still_signs_in(self, client, db):
        w = await build(db)
        w.partner.email = f"{unique('Legacy')}@Fixture.Example.com"
        await db.commit()
        r = await _login(client, w.partner.email.lower())
        assert r.status_code == 200, r.text[:300]


# ---------------------------------------------------------------------------
# 9. company_type on every user response
# ---------------------------------------------------------------------------

class TestCompanyType:
    pytestmark = asyncio_test

    async def test_put_returns_company_type(self, client, db):
        w = await build(db)
        r = await client.put(
            f"/api/v1/users/{w.partner.id}", headers=auth_header(w.manager),
            json={"job_title": "Lead"},
        )
        assert r.status_code == 200
        assert r.json()["company_type"] == w.company.company_type.value

    async def test_team_create_returns_company_type(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/users/team", headers=auth_header(w.partner),
            json={"full_name": "New Hire", "email": f"{unique('t')}@fixture.example.com",
                  "contact": "1", "designation": "Eng", "department": "R&D"},
        )
        assert r.status_code == 201, r.text[:300]
        assert r.json()["company_type"] == w.company.company_type.value


# ---------------------------------------------------------------------------
# 10. Notification count
# ---------------------------------------------------------------------------

class TestNotificationCount:
    pytestmark = asyncio_test

    async def test_total_count_is_real(self, client, db):
        w = await build(db)
        for read in (True, False, False):
            db.add(Notification(
                user_id=w.partner.id, type="info", title="t", message="m", read=read,
            ))
        await db.commit()
        r = await client.get("/api/v1/notifications/count", headers=auth_header(w.partner))
        assert r.status_code == 200
        assert r.json() == {"unread_count": 2, "total_count": 3}


# ---------------------------------------------------------------------------
# 11. List filters
# ---------------------------------------------------------------------------

class TestUserListFilters:
    pytestmark = asyncio_test

    @pytest.mark.parametrize("param", ["status", "role"])
    async def test_an_unknown_value_is_a_422(self, client, db, param):
        w = await build(db)
        r = await client.get(
            "/api/v1/users", headers=auth_header(w.superadmin), params={param: "foo"}
        )
        assert r.status_code == 422

    async def test_percent_is_matched_literally(self, client, db):
        w = await build(db)
        r = await client.get(
            "/api/v1/users", headers=auth_header(w.superadmin), params={"search": "%"}
        )
        assert r.status_code == 200
        assert all("%" in u["full_name"] or "%" in u["email"] for u in r.json()["items"])

        w.partner.full_name = f"Hundred {unique('x')} 100% Club"
        await db.commit()
        r = await client.get(
            "/api/v1/users", headers=auth_header(w.superadmin), params={"search": "100% Club"}
        )
        assert w.partner.id in [u["id"] for u in r.json()["items"]]
