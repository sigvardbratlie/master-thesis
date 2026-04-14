
from fastapi import APIRouter, Depends
import logging
from api.dependencies import get_current_user, get_conversation_manager, get_email_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/document", tags=["document"])

@router.post("/expand-email")
async def expand_email_endpoint(email_ids: list[str],
                                conversation_manager = Depends(get_conversation_manager),
                                email_parser = Depends(get_email_parser),
                                user_id: str = Depends(get_current_user),
                                ):
    response = conversation_manager.supabase.table("project_emails") \
        .select("email_id, body, from_addr, to, cc, date, subject") \
        .in_("email_id", email_ids).execute()

    parsed_res = {}
    for row in response.data:
        parts = email_parser.expand_email_from_db(
            body_text=row.get("body") or "",
            from_addr=row.get("from_addr"),
            to=row.get("to"),
            cc=row.get("cc"),
            date=row.get("date"),
            subject=row.get("subject"),
        )
        parsed_res[row["email_id"]] = [p.model_dump(mode="json") for p in parts]

    return parsed_res
