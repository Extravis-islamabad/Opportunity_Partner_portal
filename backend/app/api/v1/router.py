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
    exports,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
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
api_router.include_router(bulk_import.router)
api_router.include_router(exports.router)
