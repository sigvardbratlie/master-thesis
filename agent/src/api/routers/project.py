from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from models import AskAgentRequest
import json
import asyncio
from agent.utils import to_thread_config
import logging
from api.dependencies import get_current_user, get_pm
from langchain_core.runnables import RunnableConfig


logger = logging.getLogger(__name__)

router = APIRouter(prefix = "/project", tags = ["project"])


@router.post("/init-project")
async def init_project_endpoint(query: AskAgentRequest,
                                pm = Depends(get_pm),
                                user_id: str = Depends(get_current_user)):
    """
    Endpoint to initialize scanning and processing of attachments.
    """
    thread: RunnableConfig  = to_thread_config(query=query, user_id=user_id)
    init_graph = pm.compile_init_pipeline()
    async def gen():
        try:
            async for chunk in init_graph.astream({"query": query}, config=thread, stream_mode="custom"):
                yield f'data: {json.dumps(chunk)}\n\n'
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in init_stream_generator: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream")

@router.post("/update-project")
async def update_project_endpoint(query: AskAgentRequest,
                                pm = Depends(get_pm),
                                user_id: str = Depends(get_current_user)):
    """
    Endpoint to update the project with new input and attachments.
    """
    thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
    update_graph = pm.compile_update_pipeline()
    async def gen():
        try:
            async for chunk in update_graph.astream({"query": query}, config=thread, stream_mode="custom"):
                yield f'data: {json.dumps(chunk)}\n\n'
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in update_stream_generator: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream")

@router.post("/update-project-from-session")
async def update_project_from_session_endpoint(query: AskAgentRequest,
                                                pm = Depends(get_pm),
                                                user_id: str = Depends(get_current_user)):
    updated_query = await asyncio.to_thread(pm.mk_update_query_from_session, query=query)
    thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
    update_graph = pm.compile_update_pipeline()
    async def gen():
        
        try:
            async for chunk in update_graph.astream({"query": updated_query}, config=thread, stream_mode="custom"):
                yield f'data: {json.dumps(chunk)}\n\n'
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in update_stream_generator: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream")
