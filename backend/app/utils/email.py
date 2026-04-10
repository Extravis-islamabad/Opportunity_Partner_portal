import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from pathlib import Path
from typing import List, Optional
from jinja2 import Environment, FileSystemLoader
import structlog

from app.core.config import settings

logger = structlog.get_logger()

template_dir = Path(__file__).parent.parent / "templates" / "email"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)

# Brand logo embedded inline via Content-ID. Templates reference it as
# <img src="cid:extravis-logo">. Loaded once at import time.
LOGO_PATH = template_dir / "assets" / "extravis-logo.png"
LOGO_CID = "extravis-logo"
try:
    _LOGO_BYTES: Optional[bytes] = LOGO_PATH.read_bytes()
except FileNotFoundError:
    _LOGO_BYTES = None
    logger.warning("email_logo_missing", path=str(LOGO_PATH))


async def send_email(
    to_emails: List[str],
    subject: str,
    html_body: str,
    attachments: Optional[List[dict]] = None,
) -> bool:
    if not settings.SMTP_PASSWORD:
        logger.warning("email_skipped", reason="SMTP_PASSWORD not configured", to=to_emails, subject=subject)
        return False

    # Use multipart/related so the inline logo image (referenced by cid:) is
    # rendered by mail clients alongside the HTML body. File attachments are
    # added at the outer level as a sibling part.
    if attachments:
        msg = MIMEMultipart("mixed")
        related = MIMEMultipart("related")
    else:
        msg = MIMEMultipart("related")
        related = msg

    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject

    related.attach(MIMEText(html_body, "html", "utf-8"))

    if _LOGO_BYTES is not None:
        logo_part = MIMEImage(_LOGO_BYTES, _subtype="png")
        logo_part.add_header("Content-ID", f"<{LOGO_CID}>")
        logo_part.add_header("Content-Disposition", "inline", filename="extravis-logo.png")
        related.attach(logo_part)

    if attachments:
        msg.attach(related)
        for attachment in attachments:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment["content"])
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{attachment["filename"]}"')
            msg.attach(part)

    # Port 587 uses STARTTLS (upgrade plain connection); port 465 uses
    # implicit TLS from the start. Office365/SendGrid both need STARTTLS on 587.
    use_implicit_tls = settings.SMTP_PORT == 465
    use_starttls = settings.SMTP_TLS and not use_implicit_tls

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=use_implicit_tls,
            start_tls=use_starttls,
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
