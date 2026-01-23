from dotenv import load_dotenv
load_dotenv()
import os
from pathlib import Path
from typing import Optional,Literal
import asyncio
import json
from pydantic import BaseModel
import uvicorn

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI,HTTPException,status,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from langchain_openai import ChatOpenAI
from google.cloud import firestore

from agent.utils import PROMPT
from agent.tools import TOOLS
from agent import Agent
from database import FirestoreSaver,FirestoreManager,SupabaseManager
from auth import GoogleAuth
from agent.basemodels import AttachmentModel,AskAgentRequest, StreamlitUserInfo
    
# ===== SETUP FASTAPI & AGENT =======
app = FastAPI()

origins = [
    # Lokal utvikling
    "http://localhost",
    "http://localhost:5173",  # Standard for Vite
    "http://localhost:63342",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
checkpointer = FirestoreSaver(project_id=project_id,database_id="(default)")
auth = GoogleAuth(secret_key=os.getenv("SECRET_KEY"))


agent = Agent(
    tools=TOOLS,
    #llms=llms,
    prompt=PROMPT,
    checkpointer=checkpointer,
)
firestore_manager = FirestoreManager()
conversation_manager = SupabaseManager()

async def stream_generator(query : AskAgentRequest,
                           user_id: str = Depends(auth.get_current_user)):
    """
    Call the agent's streaming method and format output
    for Server-Sent Events (SSE) expected by the frontend.
    """


    async for response_part in agent.stream_response(query = query,user_id = user_id):
                                                     
        data_string = json.dumps(response_part)
        yield f"data: {data_string}\n\n"
        await asyncio.sleep(0.01)

# ================== API ENDPOINTS ==================
# MAIN ENDPOINTS
@app.post("/ask-agent")
async def ask_agent_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
    """
    Frontend calls this endpoint. It returns a StreamingResponse
    using our `stream_generator`.
    """
    
    #attachments = [att.model_dump() for att in query.attachments] if query.attachments else None
    try:
        return StreamingResponse(
            stream_generator(query = query,user_id = user_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Error in /ask-agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/init-project")
async def init_scan_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
    """
    Endpoint to initialize scanning and processing of attachments.
    """
    #attachments = [att.model_dump() for att in query.attachments] if query.attachments else None
    try:
        scan_result = await agent.initialize_project(
            query=query,
            user_id=user_id,
        )
        return scan_result
    except Exception as e:
        logger.error(f"Error in /init-scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/update-project")
async def update_project_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
    """
    Endpoint to update the project with new input and attachments.
    """
    #attachments = [att.model_dump() for att in query.attachments] if query.attachments else None
    try:
        update_result = await agent.update_project(
            query = query,
            user_id = user_id,
        )
        return update_result
    except Exception as e:
        logger.error(f"Error in /update-project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in /update-project: {str(e)}")


# READING FROM FIRESTORE
@app.get("/load-session-history/{session_id}")
async def load_session_history(session_id: str, user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_session_history(user_id=user_id, session_id=session_id)

@app.get("/load-user-sessions")
async def load_user_sessions(user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_user_sessions(user_id=user_id)

@app.get("/load-project/{project_id}")
async def load_project(project_id: str, user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_project(user_id=user_id, project_id=project_id)

@app.get("/load-projects")
async def load_projects(user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_projects(user_id=user_id)

@app.get("/load-project-sessions/{project_id}")
async def load_project_sessions(project_id: str, user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_project_sessions(user_id=user_id, project_id=project_id)

# AUTHENTICATION ENDPOINTS
@app.post("/token-from-streamlit")
async def generate_token_from_streamlit(user_info: StreamlitUserInfo):
    """
    Generate an internal JWT token from verified user info
    coming from the Streamlit frontend.
    """
    try:
        # Build a dict matching get_or_create_user expectations
        google_user_info_mock = {
            'sub': user_info.sub,
            'email': user_info.email,
            'name': user_info.name,
            'picture': user_info.picture
        }
        logger.debug(f'Received user info from streamlit: {google_user_info_mock}')

        # Use existing logic to get or create the user
        user_id = firestore_manager.get_or_create_user(google_user_info_mock)
        logger.debug(f'Obtained user_id: {user_id}')

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not get or create user."
            )

        # Create the internal access token
        access_token = auth.create_access_token(data={"sub": user_id},)  
        logger.debug(f'Generated access token: {access_token}')
                 
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_id": user_id,
            "user_name": user_info.name
        }

    except Exception as e:
        logger.error(f"Error generating token from streamlit user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process user info: {e}"
        )



@app.get("/", include_in_schema=False)
def root():
    return {"message": "Welcome to the CompanyAgent API, developed by Sibr AS."}


if __name__ == "__main__":
    port = int(os.getenv("PORT",8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
