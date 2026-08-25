"""Two-factor authentication.

The assertions here are weighted towards the ways MFA locks the wrong people
out: a half-finished setup, a code replayed inside its own window, a recovery
code used twice, enforcement switched on with nobody enrolled. Getting the
happy path working is the easy part.
"""
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import select

from app.models.mfa import MfaEnrollment, MfaRecoveryCode
from app.models.user import UserRole
from tests.conftest import PASSWORD, auth_header, make_company, make_user, requires_db

pytestmark = requires_db
asyncio_test = pytest.mark.asyncio


class World:
    pass


async def build(db):
    w = World()
    w.superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    w.admin = await make_user(db, role=UserRole.ADMIN)
    w.company = await make_company(db, channel_manager_id=w.admin.id)
    w.partner = await make_user(db, role=UserRole.PARTNER, company_id=w.company.id)
    await db.commit()
    return w


def code_at(secret, *, windows_ahead=0):
    """The code an authenticator shows `windows_ahead` thirty-second steps on.

    Confirming an enrolment burns the window whose code proved it, so a login
    moments later needs the next code — which is exactly what the phone shows
    half a minute later.
    """
    return pyotp.TOTP(secret).at(
        datetime.now(timezone.utc) + timedelta(seconds=30 * windows_ahead)
    )


async def enrol(client, db, user):
    """Take a user all the way through setup. Returns (secret, codes)."""
    setup = await client.post("/api/v1/mfa/setup", headers=auth_header(user))
    assert setup.status_code == 201, setup.text[:300]
    secret = setup.json()["secret"]

    confirm = await client.post(
        "/api/v1/mfa/confirm",
        headers=auth_header(user),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert confirm.status_code == 200, confirm.text[:300]
    await db.commit()
    return secret, confirm.json()["recovery_codes"]


async def _enrollment(db, user_id):
    row = (await db.execute(
        select(MfaEnrollment).where(MfaEnrollment.user_id == user_id)
    )).scalar_one_or_none()
    if row is not None:
        await db.refresh(row)
    return row


class TestEnrolment:
    pytestmark = asyncio_test

    async def test_setup_returns_a_secret_and_a_qr(self, client, db):
        w = await build(db)
        r = await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        assert r.status_code == 201, r.text[:300]
        body = r.json()
        assert body["secret"]
        assert body["otpauth_uri"].startswith("otpauth://totp/")
        assert body["qr_svg"].lstrip().startswith("<?xml")

    async def test_setup_alone_does_not_switch_it_on(self, client, db):
        # A mistyped setup must not lock somebody out of their own account.
        w = await build(db)
        await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        await db.commit()

        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.admin))
        assert status.json()["enabled"] is False

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert login.status_code == 200
        assert "mfa_required" not in login.json()

    async def test_confirming_switches_it_on_and_returns_codes(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)
        assert len(codes) == 10

        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.admin))
        assert status.json()["enabled"] is True
        assert status.json()["recovery_codes_remaining"] == 10

    async def test_a_wrong_code_does_not_switch_it_on(self, client, db):
        w = await build(db)
        await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        r = await client.post(
            "/api/v1/mfa/confirm",
            headers=auth_header(w.admin),
            json={"code": "000000"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "INVALID_MFA_CODE"
        assert (await _enrollment(db, w.admin.id)).confirmed_at is None

    async def test_confirming_without_setup_is_refused(self, client, db):
        w = await build(db)
        r = await client.post(
            "/api/v1/mfa/confirm",
            headers=auth_header(w.partner),
            json={"code": "123456"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "MFA_NOT_STARTED"

    async def test_restarting_setup_replaces_an_abandoned_secret(self, client, db):
        # Somebody who gave up halfway should get a fresh QR, not an error
        # about a row they cannot see.
        w = await build(db)
        first = await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        await db.commit()
        second = await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        assert second.status_code == 201, second.text[:300]
        assert second.json()["secret"] != first.json()["secret"]

    async def test_setting_up_twice_when_enabled_is_refused(self, client, db):
        w = await build(db)
        await enrol(client, db, w.admin)
        r = await client.post("/api/v1/mfa/setup", headers=auth_header(w.admin))
        assert r.status_code == 409
        assert r.json()["code"] == "MFA_ALREADY_ENABLED"

    async def test_a_partner_can_enrol_too(self, client, db):
        # Optional for everybody, not just staff.
        w = await build(db)
        _, codes = await enrol(client, db, w.partner)
        assert len(codes) == 10


class TestLogin:
    pytestmark = asyncio_test

    async def test_password_alone_no_longer_logs_you_in(self, client, db):
        w = await build(db)
        await enrol(client, db, w.admin)

        r = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mfa_required"] is True
        assert body["challenge_token"]
        assert "access_token" not in body

    async def test_the_challenge_token_is_not_an_access_token(self, client, db):
        # Otherwise the second factor is decorative: the thing handed out
        # after the password step would already open the door.
        w = await build(db)
        await enrol(client, db, w.admin)
        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]

        r = await client.get(
            "/api/v1/opportunities",
            headers={"Authorization": f"Bearer {challenge}"},
        )
        assert r.status_code == 401

    async def test_a_code_finishes_the_login(self, client, db):
        w = await build(db)
        secret, _ = await enrol(client, db, w.admin)
        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]

        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": code_at(secret, windows_ahead=1)},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["access_token"]
        assert r.json()["user"]["id"] == w.admin.id

    async def test_burning_one_window_does_not_burn_the_next(self, client, db):
        # Confirming setup used the current window's code. The next one is what
        # the phone shows thirty seconds later, and it has to still work — a
        # replay guard that remembers "now" instead of the window that matched
        # would refuse it and look like a broken authenticator.
        w = await build(db)
        secret, _ = await enrol(client, db, w.admin)
        enrollment = await _enrollment(db, w.admin.id)
        burned = enrollment.last_used_counter
        assert burned is not None, "confirming a setup did not record a window"

        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]
        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": code_at(secret, windows_ahead=1)},
        )
        assert r.status_code == 200, r.text[:300]
        await db.commit()
        assert (await _enrollment(db, w.admin.id)).last_used_counter == burned + 1

    async def test_a_wrong_code_does_not(self, client, db):
        w = await build(db)
        await enrol(client, db, w.admin)
        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]

        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": "000000"},
        )
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_MFA_CODE"

    async def test_a_forged_challenge_is_refused(self, client, db):
        w = await build(db)
        secret, _ = await enrol(client, db, w.admin)
        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": "not-a-token", "code": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_MFA_CHALLENGE"

    async def test_an_access_token_cannot_stand_in_for_a_challenge(self, client, db):
        # The reverse of the earlier check: a token of the wrong type in
        # either direction has to be refused.
        from app.core.security import create_access_token

        w = await build(db)
        secret, _ = await enrol(client, db, w.admin)
        access = create_access_token({"sub": str(w.admin.id), "role": "admin"})

        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": access, "code": pyotp.TOTP(secret).now()},
        )
        assert r.status_code == 401
        assert r.json()["code"] == "INVALID_MFA_CHALLENGE"

    async def test_a_code_cannot_be_replayed(self, client, db):
        # A TOTP code lives for thirty seconds. Without remembering the last
        # accepted window, a code read over somebody's shoulder works again.
        w = await build(db)
        secret, _ = await enrol(client, db, w.admin)
        code = code_at(secret, windows_ahead=1)

        first_challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]
        first = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": first_challenge, "code": code},
        )
        assert first.status_code == 200, first.text[:300]
        await db.commit()

        second_challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]
        second = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": second_challenge, "code": code},
        )
        assert second.status_code == 401, "the same code was accepted twice"


class TestRecoveryCodes:
    pytestmark = asyncio_test

    async def test_a_recovery_code_logs_you_in(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)
        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]

        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": codes[0]},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["access_token"]

    async def test_a_recovery_code_works_only_once(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)

        for expected in (200, 401):
            challenge = (await client.post(
                "/api/v1/auth/login",
                json={"email": w.admin.email, "password": PASSWORD},
            )).json()["challenge_token"]
            r = await client.post(
                "/api/v1/auth/login/mfa",
                json={"challenge_token": challenge, "code": codes[0]},
            )
            assert r.status_code == expected, r.text[:200]
            await db.commit()

    async def test_codes_are_stored_hashed(self, client, db):
        # They are credentials. Somebody who reads the database must not get a
        # way in.
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)
        enrollment = await _enrollment(db, w.admin.id)
        rows = (await db.execute(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.enrollment_id == enrollment.id
            )
        )).scalars().all()
        stored = {r.code_hash for r in rows}
        assert not (stored & set(codes)), "a recovery code was stored in the clear"

    async def test_using_one_shows_in_the_remaining_count(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)
        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]
        await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": codes[0]},
        )
        await db.commit()

        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.admin))
        assert status.json()["recovery_codes_remaining"] == 9

    async def test_regenerating_invalidates_the_old_set(self, client, db):
        w = await build(db)
        _, old = await enrol(client, db, w.admin)
        fresh = await client.post(
            "/api/v1/mfa/recovery-codes", headers=auth_header(w.admin)
        )
        assert fresh.status_code == 200, fresh.text[:300]
        await db.commit()
        assert set(fresh.json()["recovery_codes"]).isdisjoint(old)

        challenge = (await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )).json()["challenge_token"]
        r = await client.post(
            "/api/v1/auth/login/mfa",
            json={"challenge_token": challenge, "code": old[0]},
        )
        assert r.status_code == 401


class TestDisabling:
    pytestmark = asyncio_test

    async def test_you_can_turn_off_your_own(self, client, db):
        w = await build(db)
        await enrol(client, db, w.admin)
        r = await client.delete("/api/v1/mfa", headers=auth_header(w.admin))
        assert r.status_code == 200, r.text[:300]
        await db.commit()

        login = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert "mfa_required" not in login.json()

    async def test_a_superadmin_can_reset_somebody_else(self, client, db):
        # The lockout escape hatch: lost phone, lost codes. Without it the
        # answer is a database edit.
        w = await build(db)
        await enrol(client, db, w.admin)
        r = await client.delete(
            f"/api/v1/mfa/users/{w.admin.id}", headers=auth_header(w.superadmin)
        )
        assert r.status_code == 200, r.text[:300]
        await db.commit()
        assert await _enrollment(db, w.admin.id) is None

    async def test_a_peer_admin_cannot_reset_somebody_else(self, client, db):
        w = await build(db)
        await enrol(client, db, w.partner)
        r = await client.delete(
            f"/api/v1/mfa/users/{w.partner.id}", headers=auth_header(w.admin)
        )
        assert r.status_code in (403, 404)

    async def test_disabling_takes_the_recovery_codes_with_it(self, client, db):
        w = await build(db)
        _, codes = await enrol(client, db, w.admin)
        enrollment_id = (await _enrollment(db, w.admin.id)).id
        await client.delete("/api/v1/mfa", headers=auth_header(w.admin))
        await db.commit()

        rows = (await db.execute(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.enrollment_id == enrollment_id
            )
        )).scalars().all()
        assert rows == []


class TestEnforcement:
    pytestmark = asyncio_test

    async def test_it_is_off_by_default(self, client, db):
        w = await build(db)
        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.admin))
        assert status.json()["required"] is False

    async def test_when_required_an_admin_is_told(self, client, db, monkeypatch):
        from app.core.config import settings

        w = await build(db)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.admin))
        assert status.json()["required"] is True

    async def test_a_partner_is_not_required_to(self, client, db, monkeypatch):
        from app.core.config import settings

        w = await build(db)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        status = await client.get("/api/v1/mfa/status", headers=auth_header(w.partner))
        assert status.json()["required"] is False

    async def test_the_grace_window_keeps_the_team_logging_in(
        self, client, db, monkeypatch
    ):
        # The whole point: switching enforcement on must not lock out every
        # admin who has not enrolled yet.
        from app.core.config import settings

        w = await build(db)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        monkeypatch.setattr(settings, "MFA_GRACE_DAYS", 14)

        r = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["access_token"]

    async def test_after_the_grace_window_an_unenrolled_admin_is_refused(
        self, client, db, monkeypatch
    ):
        from app.core.config import settings

        w = await build(db)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        monkeypatch.setattr(settings, "MFA_GRACE_DAYS", 14)

        w.admin.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        await db.commit()

        r = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert r.status_code == 401
        assert r.json()["code"] == "MFA_ENROLMENT_REQUIRED"

    async def test_an_enrolled_admin_is_never_locked_out_by_the_deadline(
        self, client, db, monkeypatch
    ):
        from app.core.config import settings

        w = await build(db)
        await enrol(client, db, w.admin)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        monkeypatch.setattr(settings, "MFA_GRACE_DAYS", 0)
        w.admin.created_at = datetime.now(timezone.utc) - timedelta(days=365)
        await db.commit()

        r = await client.post(
            "/api/v1/auth/login",
            json={"email": w.admin.email, "password": PASSWORD},
        )
        assert r.status_code == 200
        assert r.json()["mfa_required"] is True

    async def test_a_partner_is_never_refused_by_enforcement(
        self, client, db, monkeypatch
    ):
        from app.core.config import settings

        w = await build(db)
        monkeypatch.setattr(settings, "MFA_REQUIRED_FOR_ADMINS", True)
        monkeypatch.setattr(settings, "MFA_GRACE_DAYS", 0)
        w.partner.created_at = datetime.now(timezone.utc) - timedelta(days=365)
        await db.commit()

        r = await client.post(
            "/api/v1/auth/login",
            json={"email": w.partner.email, "password": PASSWORD},
        )
        assert r.status_code == 200, r.text[:300]
        assert r.json()["access_token"]
