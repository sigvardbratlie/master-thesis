from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from models import AskAgentRequest
import json
import asyncio
import logging
from api.dependencies import get_agent, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["agent"])

@router.post("/chat")
async def chat_endpoint(
    query: AskAgentRequest,
    agent=Depends(get_agent),
    user_id: str = Depends(get_current_user),
):
    """
    Endpoint to handle the initial chat query and return a streaming response.
    """
    async def gen():
        try:
            async for response_part in agent.stream_response(query=query, user_id=user_id):
                data_string = json.dumps(response_part)
                yield f"data: {data_string}\n\n"
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in /agent/chat: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(gen(), media_type="text/event-stream")