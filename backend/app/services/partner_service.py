from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from typing import Optional

from app.models.user import User, UserRole, UserStatus
from app.models.company import Company
from app.schemas.user import UserCreateRequest, AdminUserUpdateRequest, UserResponse, UserListResponse
from app.core.security import hash_password, generate_token
from app.core.config import settings
from app.core.exceptions import NotFoundException, ConflictException, BadRequestException
from app.utils.audit import write_audit_log
from app.utils.email import send_template_email


async def create_partner_account(
    db: AsyncSession, data: UserCreateRequest, admin_user: User
) -> UserResponse:
    existing = await db.execute(
        select(User).where(User.email == data.email, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise ConflictException(code="EMAIL_EXISTS", message="A user with this email already exists")

    if data.role == "partner":
        if not data.company_id:
            raise BadRequestException(code="COMPANY_REQUIRED", message="Partner accounts must be associated with a company")

        company_result = await db.execute(
            select(Company).where(Company.id == data.company_id, Company.deleted_at.is_(None))
        )
        company = company_result.scalar_one_or_none()
        if not company:
            raise NotFoundException(code="COMPANY_NOT_FOUND", message="Company not found")
    else:
        company = None

    activation_token = generate_token()
    temp_hash = hash_password(activation_token[:16])

    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=temp_hash,
        role=UserRole(data.role),
        status=UserStatus.PENDING_ACTIVATION,
        job_title=data.job_title,
        phone=data.phone,
        company_id=data.company_id,
        activation_token=activation_token,
        activation_token_expires=datetime.now(timezone.utc) + timedelta(hours=settings.ACTIVATION_TOKEN_EXPIRE_HOURS),
    )
    db.add(user)
    await db.flush()

    await write_audit_log(db, admin_user.id, "CREATE", "user", user.id, {
        "email": data.email, "role": data.role, "company_id": data.company_id,
    })

    company_name = company.name if company else "Extravis"
    await send_template_email(
        to_emails=[user.email],
        subject="Welcome to Extravis Partner Portal",
        template_name="welcome",
        context={
            "name": user.full_name,
            "company_name": company_name,
            "activation_token": activation_token,
            "expire_hours": settings.ACTIVATION_TOKEN_EXPIRE_HOURS,
        },
    )

    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.value,
        status=user.status.value,
        job_title=user.job_title,
        phone=user.phone,
        company_id=user.company_id,
        company_name=company_name,
        is_superadmin=user.is_superadmin,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def get_partners(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    role: Optional[str] = None,
    scope_company_ids: Optional[list[int]] = None,
) -> tuple[list, int]:
    query = (
        select(User)
        .options(joinedload(User.company))
        .where(User.deleted_at.is_(None))
    )
    count_query = select(func.count(User.id)).where(User.deleted_at.is_(None))

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    # Channel-manager scope: restrict to partner users in managed companies.
    # Other admins (peers, the superadmin) are filtered out.
    if scope_company_ids is not None:
        query = query.where(
            User.company_id.in_(scope_company_ids),
            User.role == UserRole.PARTNER,
        )
        count_query = count_query.where(
            User.company_id.in_(scope_company_ids),
            User.role == UserRole.PARTNER,
        )

    if company_id:
        query = query.where(User.company_id == company_id)
        count_query = count_query.where(User.company_id == company_id)

    if status:
        query = query.where(User.status == status)
        count_query = count_query.where(User.status == status)

    if search:
        search_filter = User.full_name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    users = result.unique().scalars().all()

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    items = []
    for u in users:
        items.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role.value,
            "status": u.status.value,
            "job_title": u.job_title,
            "phone": u.phone,
            "company_id": u.company_id,
            "company_name": u.company.name if u.company else None,
            "is_superadmin": u.is_superadmin,
            "last_login_at": u.last_login_at,
            "created_at": u.created_at,
            "updated_at": u.updated_at,
        })

    return items, total


async def get_partner_detail(db: AsyncSession, user_id: int) -> UserResponse:
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.value,
        status=user.status.value,
        job_title=user.job_title,
        phone=user.phone,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        is_superadmin=user.is_superadmin,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def update_partner(
    db: AsyncSession, user_id: int, data: AdminUserUpdateRequest, admin_user: User
) -> UserResponse:
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data:
        update_data["status"] = UserStatus(update_data["status"])

    for key, value in update_data.items():
        setattr(user, key, value)

    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "user", user.id, {
        k: v.value if hasattr(v, 'value') else v for k, v in update_data.items()
    })

    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role.value,
        status=user.status.value,
        job_title=user.job_title,
        phone=user.phone,
        company_id=user.company_id,
        company_name=user.company.name if user.company else None,
        is_superadmin=user.is_superadmin,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def deactivate_partner(db: AsyncSession, user_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    user.status = UserStatus.INACTIVE
    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "user", user.id, {"status": "inactive"})

    company_name = user.company.name if user.company else "N/A"
    await send_template_email(
        to_emails=[user.email],
        subject="Your Extravis Partner Portal access has been suspended",
        template_name="suspension",
        context={
            "partner_name": user.full_name,
            "company_name": company_name,
            "support_email": settings.SUPPORT_EMAIL,
        },
    )


async def reactivate_partner(db: AsyncSession, user_id: int, admin_user: User) -> None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException(code="USER_NOT_FOUND", message="User not found")

    user.status = UserStatus.ACTIVE
    await db.flush()
    await write_audit_log(db, admin_user.id, "UPDATE", "user", user.id, {"status": "active"})


async def get_admins_list(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(User).where(
            User.role == UserRole.ADMIN,
            User.status == UserStatus.ACTIVE,
            User.deleted_at.is_(None),
        ).order_by(User.full_name)
    )
    admins = result.scalars().all()
    return [{"id": a.id, "full_name": a.full_name, "email": a.email} for a in admins]
