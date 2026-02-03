from dotenv import load_dotenv
import logging
import os
import asyncio
import json
import uvicorn

load_dotenv()

from fastapi import FastAPI,HTTPException,status,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from agent.utils import PROMPT
from agent.tools import TOOLS
from agent import Agent
from database import FirestoreSaver,FirestoreManager,SupabaseManager
from auth import SupabaseAuth
from agent.basemodels import AskAgentRequest

logging.basicConfig(level=logging.INFO)
logging.getLogger("agent.agent").setLevel(logging.DEBUG)
logging.getLogger("agent.agent_modules").setLevel(logging.DEBUG)
logging.getLogger("database.database_modules").setLevel(logging.DEBUG)
logging.getLogger("database.storage_modules").setLevel(logging.DEBUG)
logging.getLogger("database.vectorstore_modules").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
    
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

agent = Agent(
    tools=TOOLS,
    #llms=llms,
    prompt=PROMPT,
    checkpointer=checkpointer,
)
firestore_manager = FirestoreManager()
conversation_manager = SupabaseManager()
auth = SupabaseAuth()

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


# INITIALIZE & UPDATE PROJECT ENDPOINTS
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

@app.post("/cleanup-factsheet")
async def cleanup_factsheet_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
    try:
        result = await agent.cleanup_factsheet(
            query = query,
            user_id = user_id,)
        return result if result else {"message": "No cleanup needed."}
    except Exception as e:
        logger.error(f"Error in /cleanup-factsheet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in /cleanup-factsheet: {str(e)}")

@app.post("/cleanup-project-element/{element_type}")
async def cleanup_project_element_endpoint(query: AskAgentRequest, element_type : str):
    try:
        result = await agent.cleanup_element(
            query = query,
            element_type = element_type)
        return result if result else {"message": "No cleanup needed."}
    except Exception as e:
        logger.error(f"Error in /cleanup-project-element: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in /cleanup-project-element: {str(e)}")


# READING FROM DB
@app.get("/load-session-history/{session_id}")
async def load_session_history(session_id: str):
    return conversation_manager.load_session_history(session_id=session_id)

@app.get("/load-user-sessions")
async def load_user_sessions(user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_user_sessions(user_id=user_id)

@app.get("/load-project/{project_id}")
async def load_project(project_id: str):
    return conversation_manager.load_project(project_id=project_id)

@app.get("/load-projects")
async def load_projects(user_id: str = Depends(auth.get_current_user)):
    return conversation_manager.load_projects(user_id=user_id)

@app.get("/load-project-sessions/{project_id}")
async def load_project_sessions(project_id: str): 
    return conversation_manager.load_project_sessions(project_id=project_id)


@app.get("/", include_in_schema=False)
def root():
    return {"message": "Welcome to the CompanyAgent API, developed by Sibr AS."}


if __name__ == "__main__":
    port = int(os.getenv("PORT",8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
