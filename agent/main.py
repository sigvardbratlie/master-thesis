from dotenv import load_dotenv
load_dotenv()
import os
from pathlib import Path
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
from fastapi import FastAPI,HTTPException,status,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from langchain_openai import ChatOpenAI
from google.cloud import firestore

from agent.agent import Agent,PROMPT,llms
from agent.utils import TOOLS
from agent.langchain_firestore import FirestoreSaver
from agent.google_auth import GoogleAuth
    



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
db = firestore.Client(project=project_id,database="(default)")
checkpointer = FirestoreSaver(project_id=project_id,database_id="(default)")
auth = GoogleAuth(secret_key=os.getenv("SECRET_KEY"), db = db)


agent = Agent(
    tools=TOOLS,
    llms=llms,
    prompt=PROMPT,
    checkpointer=checkpointer,
    db = db,
    domain="company",
)

class Attachment(BaseModel):
    filename: str
    file_id: str
    content: str  # Base64 encoded content
    file_type: str
    size: int

class Query(BaseModel):
    question: str
    attachments: Optional[list[Attachment]] = None
    session_id: str
    domain: str
    project_id: Optional[str] = None
    agent_type: str # Literal["fast","expert"]
    llm_provider: str #Literal["google","openai","claude"]
    query_id: str

class StreamlitUserInfo(BaseModel):
    sub: str  # Unique Google ID
    email: str
    name: str
    picture: Optional[str] = None

async def stream_generator(question: str, attachments: list[Attachment], session_id: str, agent_type: str, llm_provider: str, domain: str, query_id: str, user_id: str = Depends(auth.get_current_user)):
    """
    Call the agent's streaming method and format output
    for Server-Sent Events (SSE) expected by the frontend.
    """

    # if domain=="company":
    #     agent = company_agent
    # else:
    #     raise ValueError(f'Invalid domain: {domain}. Expecting "company"')

    async for response_part in agent.stream_response(user_input = question, 
                                                     attachments = attachments, 
                                                     session_id = session_id, 
                                                     user_id = user_id,
                                                     agent_type = agent_type, 
                                                     llm_provider = llm_provider, 
                                                     query_id = query_id):
        data_string = json.dumps(response_part)
        yield f"data: {data_string}\n\n"
        await asyncio.sleep(0.01)

@app.post("/ask-agent")
async def ask_agent_endpoint(query: Query, user_id: str = Depends(auth.get_current_user)):
    """
    Frontend calls this endpoint. It returns a StreamingResponse
    using our `stream_generator`.
    """
    # print(f'Received /ask-agent request:')
    # print(f"Question: {query.question}")
    # print(f'Attachments content : {[(att.filename, att.content[:30] + "...") for att in query.attachments] if query.attachments else "None"}')
    attachments = [att.model_dump() for att in query.attachments] if query.attachments else None
    try:
        return StreamingResponse(
            stream_generator(question = query.question,
                             attachments = attachments,
                            session_id = query.session_id,
                            user_id = user_id,
                            agent_type = query.agent_type,
                            llm_provider = query.llm_provider,
                            domain = query.domain,
                            query_id = query.query_id
                            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Error in /ask-agent: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/load-session-history/{user_id}/{session_id}")
async def load_session_history(user_id: str, session_id: str):
    try:
        session_ref = (
            db.collection("chat_history")
              .document(user_id)
              .collection("sessions")
              .document(session_id)
        )
        
        session_doc = session_ref.get()
        
        if not session_doc.exists:
            logger.warning(f"No session found for session_id: {session_id}")
            return {
                "events": [],
                "title": "Ny samtale",
                "domain": "company"
            }
        
        session_data = session_doc.to_dict()
        
        events = session_data.get("events", [])
        title = session_data.get("title", "")
        
        if not events:
            return {
                "events": [],
                "title": "Ny samtale",
                "domain": session_data.get("domain", "company")
            }
        
        return {
            "events": events,  
            "title": title, 
            "domain": session_data.get("domain", "company"),
            "agent_type": session_data.get("agent_type"),
            "llm_provider": session_data.get("llm_provider"),
            "last_updated": session_data.get("last_updated"),
        }
    
    except Exception as e:
        logger.error(f"Error loading session history: {e}")
        return {"error": str(e)}

@app.get("/load-user-sessions/{user_id}/{domain}")
async def load_user_sessions(user_id: str, domain: str):
    try:
        # Hent alle sessions for brukeren
        sessions_ref = (
            db.collection("chat_history")
              .document(user_id)
              .collection("sessions")
        )
        
        sessions_docs = sessions_ref.stream()
        
        all_sessions = []
        
        for session_doc in sessions_docs:
            session_data = session_doc.to_dict()
            #print(f'Session data: {session_data}')
            session_id = session_doc.id
            
            # Sjekk om session har events
            events = session_data.get("events", [])
            title = session_data.get("title", "")
            if not events:
                continue  # Skip tomme sessions
            
            # Filter by domain
            session_domain = session_data.get("domain", "company")
            if session_domain != domain:
                continue
            
            # Hent timestamp for sortering
            timestamp = session_data.get("last_updated")
            
            all_sessions.append({
                "session_id": session_id,
                "title": title,
                "timestamp": timestamp,
                "agent_type": session_data.get("agent_type"),
                "llm_provider": session_data.get("llm_provider"),
            })
        
        # Sorter etter timestamp (nyeste først)
        all_sessions.sort(
            key=lambda x: x.get("timestamp") or "", 
            reverse=True
        )
        
        # Fjern timestamp fra response (ikke nødvendig for UI)
        for session in all_sessions:
            session.pop("timestamp", None)
        
        return all_sessions
    
    except Exception as e:
        logger.error(f'Could not load sessions for user {user_id}: {e}')
        raise HTTPException(status_code=500, detail=str(e))

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
        user_id = auth.get_or_create_user(google_user_info_mock)
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
