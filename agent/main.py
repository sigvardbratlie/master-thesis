from dotenv import load_dotenv
import logging
import os
import asyncio
import json
import uvicorn
from contextlib import asynccontextmanager

load_dotenv()

from fastapi import FastAPI,HTTPException,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from agent.utils import PROMPT
from agent.tools import TOOLS
from agent.agent import Agent
from database import SupabaseManager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from auth import SupabaseAuth
from models import AskAgentRequest, CleanupElementsRequest
from utils.config_utils import AppConfig
from utils.logging_utils import setup_logging
from langchain_core.runnables import RunnableConfig
from agent.utils import to_thread_config, pick_llm
from database import BQVectorStore
from agent import ProjectPipeline, ProjectClean

def silence_loggers():
    noisy_packages =  [
        "httpx", "httpcore", "urllib3", "grpc",
        "google.cloud.firestore", "google.cloud.bigquery", "google.cloud.storage",
        "langchain", "langchain_core", "langchain_text_splitters",
        "langgraph", "langchain_google_genai", "langchain_google_community",
        "langchain_chroma", "psycopg", "psycopg_pool",
        "uvicorn.access",
    ]
    [logging.getLogger(_pkg).setLevel(logging.WARNING) for _pkg in noisy_packages]

    debug_packages = ["agent", "database", "documents"]
    [logging.getLogger(_pkg).setLevel(logging.DEBUG) for _pkg in debug_packages]

# ============= SETUP ============= 
config = AppConfig.from_toml("config.toml")
setup_logging(config)
silence_loggers()
logger = logging.getLogger(__name__)

# agent: Agent = None
# pm = ProjectPipeline(name = "ProjectPipeline", config=config,)
# clean = ProjectClean(name="ProjectClean", config=config,)
# pool: AsyncConnectionPool = None
# conversation_manager = SupabaseManager()
# auth = SupabaseAuth()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize async resources on startup, cleanup on shutdown."""
    global agent, pool
    connection_string = os.getenv("SUPABASE_DB_URL")
    #logger.info(f"🔗 DB connection: {connection_string[:50]}...")
    pool = AsyncConnectionPool(conninfo=connection_string, open=False)
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)

    try:
        await checkpointer.setup()
    except Exception as e:
        if "CONCURRENTLY" in str(e) or "already exists" in str(e):
            logger.info("⚙️  Checkpoint tables already exist — skipping setup")
        else:
            raise e

    agent = Agent(
        tools=TOOLS,
        prompt=PROMPT,
        checkpointer=checkpointer,
        config = config
    )
    logger.info("🚀 Agent ready — AsyncPostgresSaver checkpointer attached")

    app.state.config = AppConfig.from_toml("config.toml")
    app.state.agent = agent
    app.state.pool = pool
    app.state.pm = ProjectPipeline(name = "ProjectPipeline", config=config,)
    app.state.clean = ProjectClean(name="ProjectClean", config=config,)
    app.state.auth = SupabaseAuth()
    app.state.conversation_manager = SupabaseManager()
    app.state.vectorstore = BQVectorStore()

    yield

    # Cleanup on shutdown
    await pool.close()
    logger.info("🔌 Connection pool closed")

def setup_app():
    app = FastAPI(lifespan=lifespan)
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
    return app

app = setup_app()
def include_routers(app: FastAPI):
    from api.routers import agent, clean, database, project
    app.include_router(agent.router)
    app.include_router(clean.router)
    app.include_router(database.router)
    app.include_router(project.router)
    return app

app = include_routers(app)

@app.get("/", include_in_schema=False)
def root():
    return {"message": "Welcome to the CompanyAgent API, developed by Sibr AS."}


# # ================== API ENDPOINTS ==================
# # MAIN ENDPOINTS
# @app.post("/ask-agent")
# async def ask_agent_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
#     """
#     Frontend calls this endpoint. It returns a StreamingResponse
#     using our `stream_generator`.
#     """
    
#     async def stream_generator(query : AskAgentRequest,
#                            user_id: str = Depends(auth.get_current_user)):
#         """
#         Call the agent's streaming method and format output
#         for Server-Sent Events (SSE) expected by the frontend.
#         """
#         thread = to_thread_config(query=query, user_id=user_id)
#         try:
#             async for response_part in agent.stream_response(query = query,user_id = user_id):                                        
#                 data_string = json.dumps(response_part)
#                 yield f"data: {data_string}\n\n"
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in /ask-agent: {e}", exc_info=True)
#             raise HTTPException(status_code=500, detail=str(e))

#     return StreamingResponse(
#         stream_generator(query = query,user_id = user_id),
#         media_type="text/event-stream"
#     )

# # INITIALIZE & UPDATE PROJECT ENDPOINTS
# @app.post("/init-project")
# async def init_project_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
#     """
#     Endpoint to initialize scanning and processing of attachments.
#     """
#     thread: RunnableConfig  = to_thread_config(query=query, user_id=user_id)
#     init_graph = pm.compile_init_pipeline()
#     async def gen():
#         try:
#             async for chunk in init_graph.astream({"query": query}, config=thread, stream_mode="custom"):
#                 yield f'data: {json.dumps(chunk)}\n\n'
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in init_stream_generator: {e}", exc_info=True)
#             yield f'data: {json.dumps({"error": str(e)})}\n\n'

#     return StreamingResponse(gen(), media_type="text/event-stream")

# @app.post("/update-project")
# async def update_project_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
#     """
#     Endpoint to update the project with new input and attachments.
#     """
#     thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
#     update_graph = pm.compile_update_pipeline()
#     async def gen():
#         try:
#             async for chunk in update_graph.astream({"query": query}, config=thread, stream_mode="custom"):
#                 yield f'data: {json.dumps(chunk)}\n\n'
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in update_stream_generator: {e}", exc_info=True)
#             yield f'data: {json.dumps({"error": str(e)})}\n\n'
#     return StreamingResponse(gen(), media_type="text/event-stream")

# @app.post("/update-project-from-session")
# async def update_project_from_session_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
#     updated_query = await asyncio.to_thread(pm.mk_update_query_from_session, query=query)
#     thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
#     update_graph = pm.compile_update_pipeline()
#     async def gen():
        
#         try:
#             async for chunk in update_graph.astream({"query": updated_query}, config=thread, stream_mode="custom"):
#                 yield f'data: {json.dumps(chunk)}\n\n'
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in update_stream_generator: {e}", exc_info=True)
#             yield f'data: {json.dumps({"error": str(e)})}\n\n'
#     return StreamingResponse(gen(), media_type="text/event-stream")

# # CLEAN ENDPOINTS

# @app.post("/cleanup-all-metadata")
# async def cleanup_all_metadata_endpoint(query: AskAgentRequest, user_id: str = Depends(auth.get_current_user)):
#     thread = to_thread_config(query=query, user_id=user_id)
#     clean_meta = clean.compile_clean_metadata()
#     async def gen():    
#         try:
#             async for chunk in clean_meta.astream_events(query=query, config=thread):
#                 yield f'data: {json.dumps(chunk)}\n\n'
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in cleanup_all_metadata_endpoint: {e}", exc_info=True)
#             yield f'data: {json.dumps({"error": str(e)})}\n\n'
#     return StreamingResponse(gen(), media_type="text/event-stream")

# @app.post("/cleanup-project-elements")
# async def cleanup_project_elements_endpoint(query: CleanupElementsRequest, user_id: str = Depends(auth.get_current_user)):
#     thread: RunnableConfig = to_thread_config(query=query, user_id=user_id)
#     clean_element = clean.compile_clean_elements()
#     async def gen():
#         try:
#             async for chunk in clean_element.astream_events(query=query, config=thread):
#                 yield f'data: {json.dumps(chunk)}\n\n'
#                 await asyncio.sleep(0.01)
#         except Exception as e:
#             logger.error(f"Error in cleanup_project_elements_endpoint: {e}", exc_info=True)
#             yield f'data: {json.dumps({"error": str(e)})}\n\n'
#     return StreamingResponse(gen(), media_type="text/event-stream")

# #DATABASE ENDPOINTS
# @app.delete("/delete-vectorstore-project/{project_id}")
# async def delete_vectorstore_project_endpoint(project_id: str):
#     """Delete project from BigQuery vector store."""
#     try:
#         result = agent.delete_project_vectorstore(project_id)
#         return result
#     except Exception as e:
#         logger.error(f"Error in /delete-vectorstore-project: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Error deleting from vector store: {str(e)}")

# @app.delete("/delete-vectorstore-file/{file_id}")
# async def delete_vectorstore_file_endpoint(file_id: str):
#     """Delete file from BigQuery vector store."""
#     try:
#         agent.vs.delete_file(file_id)
#         return {"success": True, "file_id": file_id}
#     except Exception as e:
#         logger.error(f"Error in /delete-vectorstore-file: {e}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Error deleting file from vector store: {str(e)}")


# # READING FROM DB
# @app.get("/load-session-history/{session_id}")
# async def load_session_history(session_id: str):
#     return conversation_manager.load_session_history(session_id=session_id)

# @app.get("/load-user-sessions")
# async def load_user_sessions(user_id: str = Depends(auth.get_current_user)):
#     return conversation_manager.load_user_sessions(user_id=user_id)

# @app.get("/load-project/{project_id}")
# async def load_project(project_id: str):
#     return conversation_manager.load_project(project_id=project_id)

# @app.get("/load-projects")
# async def load_projects(user_id: str = Depends(auth.get_current_user)):
#     return conversation_manager.load_projects(user_id=user_id)

# @app.get("/load-project-sessions/{project_id}")
# async def load_project_sessions(project_id: str): 
#     return conversation_manager.load_project_sessions(project_id=project_id)



if __name__ == "__main__":
    port = int(os.getenv("PORT",8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
