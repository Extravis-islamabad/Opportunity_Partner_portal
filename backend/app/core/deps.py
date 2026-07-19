from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.core.database import get_db
from app.core.security import decode_token
from app.core.redis import redis_client
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.models.user import User, UserRole
from sqlalchemy import select


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException(message="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]

    is_blacklisted = await redis_client.get(f"token:blacklist:{token}")
    if is_blacklisted:
        raise UnauthorizedException(code="TOKEN_REVOKED", message="Token has been revoked")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedException(code="INVALID_TOKEN", message="Invalid or expired access token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException(code="INVALID_TOKEN", message="Invalid token payload")

    # Eager-load .company so any downstream endpoint that touches
    # current_user.company doesn't trigger an async lazy-load (which fails
    # outside the greenlet context with MissingGreenlet).
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == int(user_id), User.deleted_at.is_(None))
    )
    user = result.unique().scalar_one_or_none()

    if not user:
        raise UnauthorizedException(code="USER_NOT_FOUND", message="User account not found")

    if user.status != "active":
        raise UnauthorizedException(code="ACCOUNT_INACTIVE", message="Account is not active")

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(message="Admin access required")
    return current_user


async def get_current_partner(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.PARTNER:
        raise ForbiddenException(message="Partner access required")
    return current_user


async def get_current_superadmin(
    current_user: User = Depends(get_current_admin),
) -> User:
    if not current_user.is_superadmin:
        raise ForbiddenException(message="This action requires superadmin access")
    return current_user


async def get_admin_or_channel_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(message="Admin access required")
    return current_user


async def deny_sales_rep(
    current_user: User = Depends(get_current_user),
) -> User:
    """Router-level guard for modules that have no sales-rep concept at all
    (commissions, scorecards, …).

    These modules were written when every user was either a partner or an
    admin, so they branch `if partner: scope to company; else: show
    everything`. A sales rep would land in the else and read the whole
    dataset. Denying at the router keeps that impossible without auditing
    every handler.
    """
    if current_user.role == UserRole.SALES_REP:
        raise ForbiddenException(
            message="Sales reps do not have access to this area"
        )
    return current_user


async def get_current_sales_rep(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.SALES_REP:
        raise ForbiddenException(message="Sales rep access required")
    return current_user


async def get_poc_editor(
    current_user: User = Depends(get_current_user),
) -> User:
    """Who may write POC / deployment / licence data: admins (incl.
    superadmins) and sales reps.

    This only gates *reaching* the endpoint. A sales rep is still restricted
    to their own opportunities — the per-record check is
    assert_can_access_opportunity, which every POC endpoint must call.
    """
    if current_user.role not in (UserRole.ADMIN, UserRole.SALES_REP):
        raise ForbiddenException(message="Admin or sales rep access required")
    return current_user


async def assert_manages_company(
    db: AsyncSession,
    admin: User,
    company_id: int,
    action: str = "access",
) -> None:
    """Channel-manager scope for a single company.

    Superadmins pass. A non-superadmin admin must channel-manage the company.

    Every {company_id} route must call this — read *and* write. The read
    routes had this check inline while `PUT /companies/{id}` did not, which
    let a channel manager POST themselves into `channel_manager_id` on a
    company they didn't manage and thereby widen their own scope.
    """
    if admin.is_superadmin:
        return

    from app.models.company import Company
    result = await db.execute(
        select(Company.id).where(
            Company.id == company_id,
            Company.channel_manager_id == admin.id,
            Company.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise ForbiddenException(
            message=f"You can only {action} companies you manage"
        )


async def assert_can_view_user(
    db: AsyncSession,
    viewer: User,
    target: User,
) -> None:
    """Per-record authorisation for reading a user account.

    - superadmin           → anyone
    - admin                → users belonging to a company they channel-manage
    - partner / sales_rep  → only themselves

    Without this, `GET /users/{id}` returned any account to any authenticated
    caller — a partner could enumerate ids and harvest every user's email and
    phone, including admins and the superadmin, even though `GET /users`
    (list) is scoped.
    """
    if viewer.is_superadmin or viewer.id == target.id:
        return

    if viewer.role == UserRole.ADMIN:
        scope = await get_admin_scope(db, viewer)
        # scope is None only for superadmins, already handled above.
        if target.company_id is not None and target.company_id in (scope or []):
            return
        raise ForbiddenException(
            message="You can only view users belonging to companies you manage"
        )

    # Partners and sales reps get themselves and nobody else.
    raise ForbiddenException(message="You can only view your own account")


async def assert_can_manage_user(
    db: AsyncSession,
    admin: User,
    target: User,
) -> None:
    """Per-record authorisation for mutating a user (update / deactivate /
    reactivate).

    - superadmin → anyone
    - admin      → only users inside a company they channel-manage

    Stricter than assert_can_view_user in one respect: an admin may never
    mutate another admin or the superadmin, because those accounts have no
    company_id and so belong to nobody's scope. Previously any admin could
    deactivate a peer admin — or the superadmin — by id.
    """
    if admin.is_superadmin:
        return

    if target.company_id is None:
        raise ForbiddenException(
            message="Only superadmins can modify admin accounts"
        )

    scope = await get_admin_scope(db, admin)
    if target.company_id not in (scope or []):
        raise ForbiddenException(
            message="You can only modify users belonging to companies you manage"
        )


async def assert_can_access_doc_request(
    db: AsyncSession,
    user: User,
    doc_request,
) -> None:
    """Per-record authorisation for a document request.

    - superadmin → anything
    - admin      → requests for companies they channel-manage
    - partner    → only requests they raised (matches the list route, which
                   scopes on requested_by rather than company)
    - sales_rep  → nothing; doc requests are a partner/admin workflow
    """
    if user.is_superadmin:
        return

    if user.role == UserRole.PARTNER:
        if doc_request.requested_by != user.id:
            raise ForbiddenException(
                message="You can only view your own document requests"
            )
        return

    if user.role == UserRole.ADMIN:
        scope = await get_admin_scope(db, user)
        if scope is not None and doc_request.company_id not in scope:
            raise ForbiddenException(
                message="You can only view document requests for companies you manage"
            )
        return

    raise ForbiddenException(
        message="Sales reps do not have access to document requests"
    )


async def assert_can_access_opportunity(
    db: AsyncSession,
    user: User,
    opportunity,
) -> None:
    """Per-record authorisation for an opportunity's POC / licence data.

    - superadmin  → anything
    - admin       → opportunities for companies they channel-manage
    - sales_rep   → only opportunities they are assigned to
    - partner     → only opportunities they submitted

    Raises ForbiddenException rather than returning a bool so a forgotten
    `if` can't silently authorise.
    """
    if user.is_superadmin:
        return

    if user.role == UserRole.SALES_REP:
        if opportunity.sales_rep_id != user.id:
            raise ForbiddenException(
                message="You can only access opportunities assigned to you"
            )
        return

    if user.role == UserRole.ADMIN:
        scope = await get_admin_scope(db, user)
        if scope is not None and opportunity.company_id not in scope:
            raise ForbiddenException(
                message="You can only access opportunities for companies you manage"
            )
        return

    if user.role == UserRole.PARTNER:
        if opportunity.submitted_by != user.id:
            raise ForbiddenException(
                message="You can only access your own opportunities"
            )
        return

    raise ForbiddenException(message="Not authorised for this opportunity")


async def get_admin_scope(
    db: AsyncSession,
    user: User,
) -> Optional[list[int]]:
    """
    Determine which company IDs an admin is allowed to see.

    Returns:
      - None  → superadmin (no scope, sees everything globally)
      - [...] → channel manager scoped to these company ids (may be empty
                if the admin manages zero companies, in which case they see
                no operational data)

    Partners should not call this — they have their own scoping by
    submitted_by / company_id at the endpoint level.
    """
    if user.is_superadmin:
        return None
    from app.models.company import Company
    result = await db.execute(
        select(Company.id).where(
            Company.channel_manager_id == user.id,
            Company.deleted_at.is_(None),
        )
    )
    return [row[0] for row in result.all()]
