"""QA fixes for the Knowledge Base, file upload and Document Request modules.

Each class pins one reported bug: doc-request list scoping for channel
managers, who is notified of a new request, KB versioning, partial KB edits,
the 500s that should have been 4xx, orphaned uploads, the category allowlist,
the company leak in fulfilled-request KB docs, and the download log bypass.
"""
import os

import pytest
from sqlalchemy import insert, select

from app.models.company import company_channel_managers
from app.models.doc_request import DocRequest
from app.models.kb_document import KBDocument, KBDownloadLog
from app.models.notification import Notification
from app.models.user import UserRole
from tests.conftest import (
    auth_header,
    make_company,
    make_doc_request,
    make_user,
    requires_db,
    unique,
)

pytestmark = [requires_db, pytest.mark.asyncio]

PDF = b"%PDF-1.4 fixture"
KB = "/api/v1/knowledge-base/documents"


@pytest.fixture(autouse=True)
def _no_mail(monkeypatch):
    async def _skip(**kwargs):
        return True

    monkeypatch.setattr("app.services.notification_service.send_template_email", _skip)


@pytest.fixture
def upload_dir(monkeypatch, tmp_path):
    """Uploads land in a private directory so a test can count what's on disk."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _files_on_disk(root) -> list[str]:
    return [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]


async def _upload(client, admin, *, title=None, category="PatchX", description=None,
                  name="sheet.pdf", content_type="application/pdf"):
    data = {"title": title or unique("Doc"), "category": category}
    if description is not None:
        data["description"] = description
    return await client.post(
        KB, headers=auth_header(admin), data=data,
        files={"file": (name, PDF, content_type)},
    )


async def _two_companies(db):
    superadmin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
    manager_a = await make_user(db, role=UserRole.ADMIN)
    manager_b = await make_user(db, role=UserRole.ADMIN)
    company_a = await make_company(db, channel_manager_id=manager_a.id)
    company_b = await make_company(db, channel_manager_id=manager_b.id)
    partner_a = await make_user(db, role=UserRole.PARTNER, company_id=company_a.id)
    partner_b = await make_user(db, role=UserRole.PARTNER, company_id=company_b.id)
    return superadmin, manager_a, manager_b, company_a, company_b, partner_a, partner_b


# ---------------------------------------------------------------------------
# 1. Doc-request list scoping
# ---------------------------------------------------------------------------

class TestDocRequestListScope:
    async def test_channel_manager_sees_only_managed_companies(self, client, db):
        sa, mgr_a, _, co_a, co_b, p_a, p_b = await _two_companies(db)
        req_a = await make_doc_request(db, company_id=co_a.id, requested_by=p_a.id)
        req_b = await make_doc_request(db, company_id=co_b.id, requested_by=p_b.id)
        ids = (req_a.id, req_b.id)
        await db.commit()

        r = await client.get("/api/v1/doc-requests?page_size=100", headers=auth_header(mgr_a))
        assert r.status_code == 200
        seen = {i["id"] for i in r.json()["items"]}
        assert ids[0] in seen
        assert ids[1] not in seen

        # Superadmin still sees every company. Filter by company so the page
        # isn't crowded out by rows other tests left in the shared database.
        for co, rid in ((co_a.id, ids[0]), (co_b.id, ids[1])):
            r = await client.get(
                f"/api/v1/doc-requests?company_id={co}", headers=auth_header(sa)
            )
            assert rid in {i["id"] for i in r.json()["items"]}

    async def test_manager_of_nothing_sees_nothing(self, client, db):
        _, _, _, co_a, _, p_a, _ = await _two_companies(db)
        await make_doc_request(db, company_id=co_a.id, requested_by=p_a.id)
        loner = await make_user(db, role=UserRole.ADMIN)
        await db.commit()

        r = await client.get("/api/v1/doc-requests", headers=auth_header(loner))
        assert r.status_code == 200
        assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# 2. Who is notified of a new request
# ---------------------------------------------------------------------------

class TestDocRequestNotifications:
    async def test_company_managers_and_superadmins_only(self, client, db):
        sa, mgr_a, mgr_b, co_a, _, p_a, _ = await _two_companies(db)
        extra_cm = await make_user(db, role=UserRole.ADMIN)
        await db.execute(insert(company_channel_managers).values(
            company_id=co_a.id, user_id=extra_cm.id,
        ))
        ids = {"sa": sa.id, "a": mgr_a.id, "b": mgr_b.id, "x": extra_cm.id}
        await db.commit()

        r = await client.post(
            "/api/v1/doc-requests", headers=auth_header(p_a),
            json={"description": unique("Need a datasheet")},
        )
        assert r.status_code == 201
        req_id = r.json()["id"]

        rows = (await db.execute(
            select(Notification.user_id).where(
                Notification.entity_type == "doc_request",
                Notification.entity_id == req_id,
            )
        )).scalars().all()
        assert ids["a"] in rows
        assert ids["x"] in rows
        assert ids["sa"] in rows
        assert ids["b"] not in rows
        # Deduplicated: nobody hears twice.
        assert len(rows) == len(set(rows))


# ---------------------------------------------------------------------------
# 3. KB versioning
# ---------------------------------------------------------------------------

class TestKBVersioning:
    async def test_new_version_keeps_the_old_one_intact(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        partner_co = await make_company(db, channel_manager_id=admin.id)
        partner = await make_user(db, role=UserRole.PARTNER, company_id=partner_co.id)
        await db.commit()

        r = await _upload(client, admin, title="Version one", name="v1.pdf")
        assert r.status_code == 201, r.text
        doc_id = r.json()["id"]

        r = await client.put(
            f"{KB}/{doc_id}", headers=auth_header(admin),
            data={"title": "Version two"},
            files={"file": ("v2.pdf", PDF, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        current = r.json()
        assert current["title"] == "Version two"
        assert current["version"] == 2
        old_id = current["previous_version_id"]
        assert old_id

        old = (await db.execute(select(KBDocument).where(KBDocument.id == old_id))).scalar_one()
        assert old.title == "Version one"
        assert old.file_name == "v1.pdf"
        assert old.is_archived == 1
        # The raw stored path, not a signed (and expiring) URL.
        assert old.file_url.startswith("/uploads/knowledge-base/")

        # The old file is still downloadable by an admin.
        r = await client.post(f"{KB}/{old_id}/download", headers=auth_header(admin))
        assert r.status_code == 200
        r = await client.get(r.json()["file_url"])
        assert r.status_code == 200
        assert r.content == PDF

        # Never surfaced as a current document.
        r = await client.get(f"{KB}/{old_id}", headers=auth_header(partner))
        assert r.status_code == 404
        r = await client.post(f"{KB}/{old_id}/download", headers=auth_header(partner))
        assert r.status_code == 404
        r = await client.get(f"{KB}?search=Version&page_size=100", headers=auth_header(partner))
        listed = {i["id"] for i in r.json()["items"]}
        assert doc_id in listed
        assert old_id not in listed

    async def test_archived_version_is_not_editable(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        doc_id = (await _upload(client, admin)).json()["id"]
        r = await client.put(
            f"{KB}/{doc_id}", headers=auth_header(admin),
            files={"file": ("v2.pdf", PDF, "application/pdf")},
        )
        old_id = r.json()["previous_version_id"]
        r = await client.put(f"{KB}/{old_id}", headers=auth_header(admin), data={"title": "x"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# 4. Partial KB update
# ---------------------------------------------------------------------------

class TestKBPartialUpdate:
    async def test_only_category_leaves_the_rest_alone(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, title="Keep me", description="Keep this too")
        doc_id = r.json()["id"]

        r = await client.put(f"{KB}/{doc_id}", headers=auth_header(admin), data={"category": "MonetX"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["category"] == "MonetX"
        assert body["title"] == "Keep me"
        assert body["description"] == "Keep this too"

    async def test_empty_title_is_rejected(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        doc_id = (await _upload(client, admin, title="Has a title")).json()["id"]

        for blank in ("", "   "):
            r = await client.put(f"{KB}/{doc_id}", headers=auth_header(admin), data={"title": blank})
            assert r.status_code == 422, (blank, r.text)

    async def test_empty_description_clears_it(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        doc_id = (await _upload(client, admin, description="temporary")).json()["id"]
        r = await client.put(f"{KB}/{doc_id}", headers=auth_header(admin), data={"description": ""})
        assert r.status_code == 200
        assert r.json()["description"] is None


# ---------------------------------------------------------------------------
# 5. 500s that should be 4xx
# ---------------------------------------------------------------------------

class TestNoMore500s:
    async def test_bogus_status_filter(self, client, db):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await client.get("/api/v1/doc-requests?status=bogus", headers=auth_header(admin))
        assert r.status_code == 422

    async def test_long_filename_is_truncated_keeping_extension(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, name="a" * 600 + ".pdf")
        assert r.status_code == 201, r.text
        name = r.json()["file_name"]
        assert len(name) <= 255
        assert name.endswith(".pdf")

    async def test_long_content_type_header(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, content_type="application/pdf" + "x" * 150)
        assert r.status_code == 201, r.text
        # Stored type comes from the sniffed bytes, not the header.
        assert r.json()["content_type"] == "application/pdf"

    async def test_create_validation_is_a_clean_422(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, title="t" * 501)
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert "title" in body["message"]
        assert "pydantic" not in r.text.lower()

    async def test_fulfil_with_overlong_category(self, client, db, upload_dir):
        sa, _, _, co_a, _, p_a, _ = await _two_companies(db)
        req = await make_doc_request(db, company_id=co_a.id, requested_by=p_a.id)
        req_id = req.id
        await db.commit()
        r = await client.post(
            f"/api/v1/doc-requests/{req_id}/fulfill",
            params={"add_to_kb": "true", "kb_category": "c" * 150},
            headers=auth_header(sa),
            files={"file": ("f.pdf", PDF, "application/pdf")},
        )
        assert r.status_code == 422
        assert _files_on_disk(upload_dir) == []

    async def test_fulfil_with_long_description_and_no_title(self, client, db, upload_dir):
        sa, _, _, co_a, _, p_a, _ = await _two_companies(db)
        req = DocRequest(company_id=co_a.id, requested_by=p_a.id, description="d" * 900)
        db.add(req)
        await db.flush()
        req_id = req.id
        await db.commit()
        r = await client.post(
            f"/api/v1/doc-requests/{req_id}/fulfill",
            params={"add_to_kb": "true"},
            headers=auth_header(sa),
            files={"file": ("f.pdf", PDF, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        kb = (await db.execute(
            select(KBDocument).where(KBDocument.file_url == (await db.execute(
                select(DocRequest.fulfilled_file_url).where(DocRequest.id == req_id)
            )).scalar_one())
        )).scalar_one()
        assert len(kb.title) <= 500
        assert kb.category == "Requested Documents"


# ---------------------------------------------------------------------------
# 6. Orphaned uploads
# ---------------------------------------------------------------------------

class TestNoOrphanFiles:
    async def test_rejected_metadata_writes_nothing(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, category=unique("Nope"))
        assert r.status_code == 422
        r = await _upload(client, admin, title="t" * 501)
        assert r.status_code == 422
        assert _files_on_disk(upload_dir) == []

    async def test_failed_update_removes_the_new_file(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await client.put(
            f"{KB}/999999999", headers=auth_header(admin),
            files={"file": ("v2.pdf", PDF, "application/pdf")},
        )
        assert r.status_code == 404
        assert _files_on_disk(upload_dir) == []


# ---------------------------------------------------------------------------
# 7. Category allowlist
# ---------------------------------------------------------------------------

class TestKBCategories:
    async def test_unknown_category_is_rejected(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, category=unique("Made up"))
        assert r.status_code == 422
        assert r.json()["code"] == "INVALID_KB_CATEGORY"

    async def test_canonical_is_normalised(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        r = await _upload(client, admin, category="patchx")
        assert r.status_code == 201
        assert r.json()["category"] == "PatchX"

    async def test_category_already_in_use_stays_valid(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        legacy = unique("Legacy")
        db.add(KBDocument(
            title="Old", category=legacy, file_name="o.pdf",
            file_url="/uploads/knowledge-base/o.pdf", uploaded_by=admin.id,
        ))
        await db.commit()
        r = await _upload(client, admin, category=legacy)
        assert r.status_code == 201, r.text

    async def test_unknown_category_on_update(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        await db.commit()
        doc_id = (await _upload(client, admin)).json()["id"]
        r = await client.put(f"{KB}/{doc_id}", headers=auth_header(admin), data={"category": unique("Nope")})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 8. Fulfilled-request KB doc does not name the company
# ---------------------------------------------------------------------------

class TestFulfilledKBDescription:
    async def test_neutral_description(self, client, db, upload_dir):
        sa, _, _, co_a, _, p_a, _ = await _two_companies(db)
        req = await make_doc_request(db, company_id=co_a.id, requested_by=p_a.id)
        req_id, co_id, co_name = req.id, co_a.id, co_a.name
        await db.commit()
        r = await client.post(
            f"/api/v1/doc-requests/{req_id}/fulfill",
            params={"add_to_kb": "true", "kb_title": unique("Fulfilled"), "kb_category": "PatchX"},
            headers=auth_header(sa),
            files={"file": ("f.pdf", PDF, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        url = (await db.execute(
            select(DocRequest.fulfilled_file_url).where(DocRequest.id == req_id)
        )).scalar_one()
        kb = (await db.execute(select(KBDocument).where(KBDocument.file_url == url))).scalar_one()
        assert str(co_id) not in (kb.description or "")
        assert co_name not in (kb.description or "")
        assert kb.category == "PatchX"


# ---------------------------------------------------------------------------
# 9. Only the download endpoint hands out a file URL
# ---------------------------------------------------------------------------

class TestKBDownloadLog:
    async def test_url_only_from_download_and_it_is_logged(self, client, db, upload_dir):
        admin = await make_user(db, role=UserRole.ADMIN, is_superadmin=True)
        co = await make_company(db, channel_manager_id=admin.id)
        partner = await make_user(db, role=UserRole.PARTNER, company_id=co.id)
        partner_id = partner.id
        await db.commit()

        title = unique("Logged")
        r = await _upload(client, admin, title=title)
        assert r.json()["file_url"] is None
        doc_id = r.json()["id"]

        r = await client.get(f"{KB}/{doc_id}", headers=auth_header(partner))
        assert r.status_code == 200
        assert r.json()["file_url"] is None
        r = await client.get(f"{KB}?search={title}", headers=auth_header(partner))
        assert all(i["file_url"] is None for i in r.json()["items"])

        r = await client.post(f"{KB}/{doc_id}/download", headers=auth_header(partner))
        assert r.status_code == 200
        assert r.json()["file_url"].startswith("/api/v1/files/download?token=")
        logs = (await db.execute(
            select(KBDownloadLog).where(
                KBDownloadLog.document_id == doc_id, KBDownloadLog.user_id == partner_id,
            )
        )).scalars().all()
        assert len(logs) == 1
