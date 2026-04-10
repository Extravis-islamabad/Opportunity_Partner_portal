import asyncio
from sqlalchemy import select
from app.core.database import async_session_factory
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
import structlog

logger = structlog.get_logger()


async def create_superadmin() -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == settings.SUPERADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            logger.info("superadmin_exists", email=settings.SUPERADMIN_EMAIL)
            return

        superadmin = User(
            full_name=settings.SUPERADMIN_NAME,
            email=settings.SUPERADMIN_EMAIL,
            password_hash=hash_password(settings.SUPERADMIN_PASSWORD),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_superadmin=True,
        )
        session.add(superadmin)
        await session.commit()
        logger.info("superadmin_created", email=settings.SUPERADMIN_EMAIL)


if __name__ == "__main__":
    asyncio.run(create_superadmin())
