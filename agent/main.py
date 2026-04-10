from dotenv import load_dotenv
import logging
import os
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.tools import TOOLS
from agent.agent import Agent
from database import SupabaseManager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from auth import SupabaseAuth
from utils.config_utils import AppConfig
from utils.logging_utils import setup_logging
from database import BQVectorStore, GCSManager
from agent import ProjectPipeline, ProjectClean

load_dotenv()

noisy_packages = ["httpx", "httpcore", "hpack", "urllib3", 
                      "anthropic", "openai", "asyncio", "langsmith", "ocrmypdf", "PIL", 
                      "img2pdf", "botocore","textractor", "google_genai"]
def silence_loggers():
    noisy_packages =  [
        "httpx", "httpcore", 
        "urllib3", 
        "grpc",
        "hpack", 
        "google.cloud.firestore", 
        "google.cloud.bigquery", 
        "google.cloud.storage",
        "langchain", 
        "langchain_core", 
        "langchain_text_splitters",
        "langgraph", 
        "langchain_google_genai", 
        "langchain_google_community",
        "langchain_chroma", 
        "psycopg", 
        "psycopg_pool",
        "uvicorn.access",
        "langsmith"
        "httpx", "httpcore", "hpack", "urllib3", 
        "anthropic", "openai", "asyncio", "langsmith", "ocrmypdf", "PIL", 
        "img2pdf", "botocore","textractor", "google_genai"
    ]
    [logging.getLogger(_pkg).setLevel(logging.WARNING) for _pkg in noisy_packages]

    debug_packages = ["agent", "database", "documents"]
    [logging.getLogger(_pkg).setLevel(logging.DEBUG) for _pkg in debug_packages]

# ============= SETUP ============= 
config = AppConfig.from_toml("config.toml")
setup_logging(config)
silence_loggers()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize async resources on startup, cleanup on shutdown."""
    global agent, pool
    connection_string = os.getenv("SUPABASE_DB_URL")
    #logger.info(f"🔗 DB connection: {connection_string[:50]}...")
    pool = AsyncConnectionPool(
        conninfo=connection_string,
        open=False,
        min_size=2,
        max_size=5,
    )
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
    app.state.vectorstore = BQVectorStore(embedding_model=config.vectorstore.bigquery.embedding_model)
    app.state.gcs = GCSManager(config=config)

    silence_loggers()

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
        "http://localhost:3000", 
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
    from api.routers import agent, clean, project, vectorstore, storage
    app.include_router(agent.router)
    app.include_router(clean.router)
    app.include_router(vectorstore.router)
    app.include_router(project.router)
    app.include_router(storage.router)
    return app

app = include_routers(app)

@app.get("/", include_in_schema=False)
def root():
    return {"message": "Welcome to the CompanyAgent API, developed by Sibr AS."}


if __name__ == "__main__":
    port = int(os.getenv("PORT",8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
