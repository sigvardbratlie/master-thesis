from langgraph.graph import StateGraph, END, START
from typing_extensions import Annotated
from models import AskAgentRequest, InitialInput, FactSheet, AttachmentModel, EmailModel
import operator
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from documents import DocumentProcessor, EmailHandler
import logging
import asyncio
from utils import AppConfig
from .context_manager import ContextManager
from datetime import datetime
import base64
import email as python_email
from database import SupabaseStorageManager, SupabaseManager, BQVectorStore
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from .utils import PipelineState

logger = logging.getLogger(__name__)


class ProjectCleanUp:
    def __init__(self, name: str, config: AppConfig, llm: BaseChatModel):
        self.name = name
        self.llm = llm
        self.config = config or AppConfig()
        self.context_manager = ContextManager()
        self.document_processor = DocumentProcessor()
        self._semaphore = asyncio.Semaphore(self.config.async_tasks.max_concurrent_tasks)
        self.storage = SupabaseStorageManager()
        self.vs = BQVectorStore()
        self.conversation_manager = SupabaseManager()
        self.embed_to_vectorstore = self.config.pipeline.embed_to_vectorstore
        self.save_to_storage = self.config.pipeline.save_to_storage

    # ======== COMPILE METHODS =========
    
    def compile_cleanup(self, state: PipelineState) -> str:
        """
        Compiles the cleanup results into a human-readable summary.
        """
        workflow = StateGraph(PipelineState)
        workflow.add_node("load_project", self._load_project_node)
        workflow.add_node("process_element", self._process_element_types)
        workflow.add_node("clean_element", self._clean_element_node)
        workflow.add_node("save_results", self._save_node)

        workflow.add_edge(START, "load_project")
        workflow.add_edge("load_project", "process_element")
        workflow.add_edge("process_element", "clean_element")
        workflow.add_edge("clean_element", "save_results")
        workflow.add_edge("save_results", END)
        return workflow.compile()
        


    
    # ========== HELPER METHODS =========

    def _process_element_types(self, state: PipelineState):
        pass
    
    
    # ======== NODE METHODS =========

    async def _clean_element_node(self, state : PipelineState, ):
        pass

    async def _load_project_node(self, state : PipelineState, ):
        pass

    async def _save_node(self, state : PipelineState, ):
        pass


