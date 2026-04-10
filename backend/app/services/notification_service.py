from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import structlog

from app.models.notification import Notification
from app.models.user import User, UserRole
from app.utils.email import send_template_email
from app.core.config import settings

logger = structlog.get_logger()


async def create_notification(
    db: AsyncSession,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notification)
    await db.flush()
    return notification


async def notify_all_admins(
    db: AsyncSession,
    notification_type: str,
    title: str,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    send_email_flag: bool = True,
) -> List[Notification]:
    result = await db.execute(
        select(User).where(
            User.role == UserRole.ADMIN,
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )
    admins = result.scalars().all()

    notifications = [
        Notification(
            user_id=admin.id,
            type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        for admin in admins
    ]
    admin_emails = [admin.email for admin in admins]

    if notifications:
        db.add_all(notifications)
        await db.flush()

    if send_email_flag and admin_emails:
        await send_template_email(
            to_emails=admin_emails,
            subject=f"{settings.APP_NAME} - {title}",
            template_name="notification",
            context={
                "name": "Admin",
                "title": title,
                "message": message,
                "action_url": f"{settings.FRONTEND_URL}/{entity_type}s/{entity_id}" if entity_type and entity_id else None,
            },
        )

    return notifications


async def notify_user(
    db: AsyncSession,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    send_email_flag: bool = True,
) -> Notification:
    notif = await create_notification(
        db, user_id, notification_type, title, message, entity_type, entity_id
    )

    if send_email_flag:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            await send_template_email(
                to_emails=[user.email],
                subject=f"{settings.APP_NAME} - {title}",
                template_name="notification",
                context={
                    "name": user.full_name,
                    "title": title,
                    "message": message,
                    "action_url": f"{settings.FRONTEND_URL}/{entity_type}s/{entity_id}" if entity_type and entity_id else None,
                },
            )

    return notif


async def notify_channel_manager(
    db: AsyncSession,
    company_id: int,
    notification_type: str,
    title: str,
    message: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> Optional[Notification]:
    from app.models.company import Company
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.deleted_at.is_(None))
    )
    company = result.scalar_one_or_none()
    if not company:
        return None

    return await notify_user(
        db, company.channel_manager_id, notification_type, title, message,
        entity_type, entity_id,
    )


async def get_user_notifications(
    db: AsyncSession,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.user_id == user_id)
    count_query = select(func.count(Notification.id)).where(Notification.user_id == user_id)

    if unread_only:
        query = query.where(Notification.read == False)
        count_query = count_query.where(Notification.read == False)

    query = query.order_by(Notification.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    notifications = list(result.scalars().all())

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return notifications, total


async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.read == False,
        )
    )
    return result.scalar() or 0


async def mark_notifications_read(db: AsyncSession, user_id: int, notification_ids: list[int]) -> int:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.id.in_(notification_ids),
            Notification.user_id == user_id,
        )
        .values(read=True)
    )
    return result.rowcount


async def mark_all_read(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read == False)
        .values(read=True)
    )
    return result.rowcount
