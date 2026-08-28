"""Creating a company must invite its contact.

The portal had no path from "company created" to "somebody can log in": the
company row was written, the channel manager was notified, and the company's
own contact was never told the portal existed. The only thing that mailed an
activation link was an admin separately creating a user, and the button that
was supposed to lead there was broken — so in practice nobody was ever
invited, and the missing mail looked like a broken mailer rather than a step
that never ran.

These tests hold the step in place: every company type provisions its contact
and mails them an activation link, and the awkward cases (an address that is
already somebody, a mailer that is down) leave the company created and say so
rather than failing or going quiet.
"""
import pytest

from app.models.company import CompanyType
from app.models.user import UserRole, UserStatus

from .conftest import auth_header, make_user, requires_db, unique

pytestmark = [pytest.mark.asyncio, requires_db]


@pytest.fixture
def sent(monkeypatch):
    """Capture welcome mail instead of sending it.

    Patched on partner_service, which is where the name is bound — patching
    utils.email would leave the already-imported reference untouched.
    """
    calls = []

    async def _capture(*, to_emails, subject, template_name, context, **kwargs):
        calls.append({
            "to": to_emails, "subject": subject,
            "template": template_name, "context": context,
        })
        return True

    monkeypatch.setattr(
        "app.services.partner_service.send_template_email", _capture
    )
    return calls


async def _superadmin(db):
    admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    await db.commit()
    return admin


def _payload(company_type: str, **overrides) -> dict:
    body = {
        "name": unique("Co"),
        "country": "US",
        "region": "NA",
        "city": "Austin",
        "industry": "Tech",
        "contact_email": f"{unique('contact')}@fixture.example.com",
        "company_type": company_type,
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("company_type", ["partner", "distributor", "customer"])
async def test_every_company_type_invites_its_contact(
    client, db, sent, company_type
):
    """A customer's contact gets an account for the same reason a partner's
    does. What a customer may then reach is settled by company_type on the
    reads, not by withholding the login."""
    admin = await _superadmin(db)
    body = _payload(company_type, channel_manager_id=admin.id)

    res = await client.post("/api/v1/companies", json=body, headers=auth_header(admin))

    assert res.status_code == 201, res.text
    assert res.json()["contact_invite"] == "sent"

    assert len(sent) == 1
    mail = sent[0]
    assert mail["to"] == [body["contact_email"]]
    assert mail["template"] == "welcome"
    # The link is the whole point — an activation token with nothing to
    # activate against is the failure this test exists to catch.
    assert mail["context"]["activation_token"]
    assert mail["context"]["company_name"] == body["name"]


async def test_contact_account_is_pending_activation_on_the_company(
    client, db, sent
):
    admin = await _superadmin(db)
    body = _payload("partner", channel_manager_id=admin.id)

    res = await client.post("/api/v1/companies", json=body, headers=auth_header(admin))
    company_id = res.json()["id"]

    from sqlalchemy import select
    from app.models.user import User

    contact = (
        await db.execute(select(User).where(User.email == body["contact_email"]))
    ).scalar_one()

    assert contact.company_id == company_id
    assert contact.role == UserRole.PARTNER
    # Pending, not active: the account is unusable until the emailed link is
    # followed and a real password is set.
    assert contact.status == UserStatus.PENDING_ACTIVATION
    assert contact.activation_token
    assert contact.activation_token_expires is not None


async def test_contact_name_greets_the_person_and_falls_back_to_the_company(
    client, db, sent
):
    admin = await _superadmin(db)

    named = _payload("partner", channel_manager_id=admin.id, contact_name="Dana Reed")
    await client.post("/api/v1/companies", json=named, headers=auth_header(admin))
    assert sent[-1]["context"]["name"] == "Dana Reed"

    anonymous = _payload("partner", channel_manager_id=admin.id)
    await client.post("/api/v1/companies", json=anonymous, headers=auth_header(admin))
    assert sent[-1]["context"]["name"] == anonymous["name"]


async def test_address_that_already_has_an_account_still_creates_the_company(
    client, db, sent
):
    """One person can be the contact for several companies, but a User belongs
    to exactly one. The company must still be created — and the caller told
    that no invite went out, rather than left assuming one did."""
    admin = await _superadmin(db)
    taken = f"{unique('taken')}@fixture.example.com"
    await make_user(db, role=UserRole.ADMIN, email=taken)
    await db.commit()

    body = _payload("partner", channel_manager_id=admin.id, contact_email=taken)
    res = await client.post("/api/v1/companies", json=body, headers=auth_header(admin))

    assert res.status_code == 201, res.text
    assert res.json()["contact_invite"] == "existing_user"
    assert sent == []


async def test_a_dead_mailer_reports_failure_but_keeps_the_account(
    client, db, monkeypatch
):
    """The account is real whether or not the mail left. Rolling the company
    back would be worse; reporting "sent" would be a lie that hides a
    reachable-by-nobody account."""
    admin = await _superadmin(db)

    async def _refuse(**kwargs):
        return False

    monkeypatch.setattr(
        "app.services.partner_service.send_template_email", _refuse
    )

    body = _payload("customer", channel_manager_id=admin.id)
    res = await client.post("/api/v1/companies", json=body, headers=auth_header(admin))

    assert res.status_code == 201, res.text
    assert res.json()["contact_invite"] == "failed"

    from sqlalchemy import select
    from app.models.user import User

    contact = (
        await db.execute(select(User).where(User.email == body["contact_email"]))
    ).scalar_one_or_none()
    assert contact is not None


async def test_invalid_company_is_rejected_before_anyone_is_invited(
    client, db, sent
):
    """A parent distributor that is not a distributor fails the create. No
    orphan account may be left behind by the attempt."""
    admin = await _superadmin(db)
    not_a_distributor = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    await db.commit()

    from .conftest import make_company

    partner_co = await make_company(
        db, channel_manager_id=admin.id, company_type=CompanyType.PARTNER
    )
    await db.commit()

    body = _payload(
        "partner",
        channel_manager_id=not_a_distributor.id,
        parent_distributor_id=partner_co.id,
    )
    res = await client.post("/api/v1/companies", json=body, headers=auth_header(admin))

    assert res.status_code == 400, res.text
    assert sent == []
