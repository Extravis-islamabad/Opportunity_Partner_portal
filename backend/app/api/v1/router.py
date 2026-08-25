from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    companies,
    partners,
    opportunities,
    knowledge_base,
    lms,
    doc_requests,
    notifications,
    dashboard,
    audit_logs,
    onboarding,
    bulk_import,
    bulk_import_opportunities,
    exports,
    commissions,
    ai,
    pocs,
    files,
    sales_activities,
    renewals,
    currencies,
    email_log,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(email_log.router)
# Bulk-import routers are registered BEFORE companies/opportunities so their
# static paths (…/bulk-import, …/bulk-import-template) match ahead of the
# `/{id:int}` param routes. Registered after, FastAPI matched
# "bulk-import-template" against `{opp_id}: int` and 422'd — the routes were
# unreachable.
api_router.include_router(bulk_import.router)
api_router.include_router(bulk_import_opportunities.router)
api_router.include_router(companies.router)
api_router.include_router(partners.router)
api_router.include_router(opportunities.router)
api_router.include_router(knowledge_base.router)
api_router.include_router(lms.router)
api_router.include_router(doc_requests.router)
api_router.include_router(notifications.router)
api_router.include_router(dashboard.router)
api_router.include_router(audit_logs.router)
api_router.include_router(onboarding.router)
api_router.include_router(exports.router)
api_router.include_router(commissions.router)
api_router.include_router(ai.router)
api_router.include_router(pocs.router)
api_router.include_router(files.router)
api_router.include_router(sales_activities.router)
api_router.include_router(renewals.router)
api_router.include_router(currencies.router)
