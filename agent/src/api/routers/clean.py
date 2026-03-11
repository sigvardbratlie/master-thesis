

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from models import AskAgentRequest, CleanupElementsRequest
import json
import asyncio
from agent.utils import to_thread_config
import logging
from api.dependencies import get_current_user, get_clean
from langchain_core.runnables import RunnableConfig


logger = logging.getLogger(__name__)

router = APIRouter(prefix = "/project", tags = ["project"])


@router.post("/cleanup-all-metadata")
async def cleanup_all_metadata_endpoint(query: AskAgentRequest, 
                                        clean = Depends(get_clean),
                                        user_id: str = Depends(get_current_user),
                                        ):
                                        
    thread = to_thread_config(query=query, user_id=user_id)
    clean_meta = clean.compile_clean_metadata()
    async def gen():    
        try:
            async for chunk in clean_meta.astream_events(query=query, config=thread):
                yield f'data: {json.dumps(chunk)}\n\n'
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in cleanup_all_metadata_endpoint: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream")

@router.post("/cleanup-project-elements")
async def cleanup_project_elements_endpoint(query: CleanupElementsRequest, 
                                            clean = Depends(get_clean),
                                            user_id: str = Depends(get_current_user)
                                            ):
    thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
    clean_element = clean.compile_clean_elements()
    async def gen():
        try:
            async for chunk in clean_element.astream_events(query=query, config=thread):
                yield f'data: {json.dumps(chunk)}\n\n'
                await asyncio.sleep(0.01)
        except Exception as e:
            logger.error(f"Error in cleanup_project_elements_endpoint: {e}", exc_info=True)
            yield f'data: {json.dumps({"error": str(e)})}\n\n'
    return StreamingResponse(gen(), media_type="text/event-stream")