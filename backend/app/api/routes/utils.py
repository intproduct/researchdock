from fastapi import APIRouter, Depends, HTTPException
from pydantic.networks import EmailStr
from sqlalchemy import text

from app.api.deps import SessionDep, get_current_active_superuser
from app.models import Message
from app.utils import generate_test_email, send_email

router = APIRouter(prefix="/utils", tags=["utils"])


@router.post(
    "/test-email/",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=201,
)
def test_email(email_to: EmailStr) -> Message:
    """
    Test emails.
    """
    email_data = generate_test_email(email_to=email_to)
    send_email(
        email_to=email_to,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    return Message(message="Test email sent")


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/readiness/")
def readiness(session: SessionDep) -> dict[str, str]:
    """Report real database connectivity, not just that the process started."""
    try:
        session.exec(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 -- surface any driver error as 503
        raise HTTPException(503, "database unavailable") from exc
    return {"database": "ok"}
