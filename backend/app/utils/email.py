import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
import structlog

from app.core.config import settings

logger = structlog.get_logger()

template_dir = Path(__file__).parent.parent / "templates" / "email"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)


async def send_email(
    to_emails: List[str],
    subject: str,
    html_body: str,
    attachments: Optional[List[dict]] = None,
) -> bool:
    if not settings.SMTP_PASSWORD:
        logger.warning("email_skipped", reason="SMTP_PASSWORD not configured", to=to_emails, subject=subject)
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    if attachments:
        for attachment in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment["content"])
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment["filename"]}"')
            msg.attach(part)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_TLS,
        )
        logger.info("email_sent", to=to_emails, subject=subject)
        return True
    except Exception as e:
        logger.error("email_send_failed", error=str(e), to=to_emails, subject=subject)
        return False


async def send_template_email(
    to_emails: List[str],
    subject: str,
    template_name: str,
    context: dict,
    attachments: Optional[List[dict]] = None,
) -> bool:
    try:
        template = jinja_env.get_template(f"{template_name}.html")
    except Exception:
        template = jinja_env.get_template("base.html")
        context["content"] = context.get("content", subject)

    html_body = template.render(**context, app_name=settings.APP_NAME, frontend_url=settings.FRONTEND_URL)
    return await send_email(to_emails, subject, html_body, attachments)
