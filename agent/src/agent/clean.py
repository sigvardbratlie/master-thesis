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
from models import PipelineState, ProjectData

logger = logging.getLogger(__name__)


class ProjectClean:
    def __init__(self, name: str, config: AppConfig):
        self.name = name
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
    
    def compile_clean_elements(self,):
        """
        Compiles the cleanup results into a human-readable summary.
        """
        workflow = StateGraph(PipelineState)
        workflow.add_node("load_project", self._load_project_node)
        workflow.add_node("clean", self._clean_elements_node)
        workflow.add_node("save_results", self._save_elements_node)

        workflow.add_edge(START, "load_project")
        workflow.add_edge("load_project", "clean")
        workflow.add_edge("clean", "save_results")
        workflow.add_edge("save_results", END)
        return workflow.compile()
    
    def compile_clean_metadata(self,):
        """
        Compiles the cleanup results into a human-readable summary.
        """
        workflow = StateGraph(PipelineState)
        workflow.add_node("load_project", self._load_project_node)
        workflow.add_node("clean", self._clean_metadata_node)
        workflow.add_node("save_results", self._save_metadata_node)

        workflow.add_edge(START, "load_project")
        workflow.add_edge("load_project", "clean")
        workflow.add_edge("clean", "save_results")
        workflow.add_edge("save_results", END)
        return workflow.compile()
        
    # ========== HELPER METHODS =========
    def _process_element_types(self, state: PipelineState):
        pass
    
    
    # ======== NODE METHODS =========

    async def _clean_elements_node(self, state : PipelineState,):
        writer = get_stream_writer()
        query = state.query
        element_types = query.element_types
        project_data = state.input_

        results = await self.context_manager.clean_elements(element_types, project_data)
        writer({
            "type": "status",
            "phase": ["cleanup_elements"],
            "status": "complete",
            "data": {
                "element_types": element_types,
                "cleaned_counts": {et: len(items) for et, items in results.items()},
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        for et, cleaned in results.items():
            setattr(project_data.factsheet, et, cleaned)
        return {"input_":  project_data}

    async def _clean_metadata_node(self, state : PipelineState):
        writer = get_stream_writer()
        query = state.query
        project_data = state.input_
        writer({
            "type": "status",
            "phase": ["cleanup_metadata"],
            "status": "starting",
            "data": {"element_type": "metadata"},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        result = await self.context_manager.clean_all_metadata(project_data=project_data)
        writer({
            "type": "status",
            "phase": ["cleanup_metadata"],
            "status": "complete",
            "data": {"title": result.get("title"), "background": result.get("background")},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        project_data.factsheet.title = result.get("title", project_data.factsheet.title)
        project_data.factsheet.background = result.get("background", project_data.factsheet.background)
        return {"input_":  project_data}
        
    async def _load_project_node(self, state : PipelineState, ):
        query = state.query
        element_types = getattr(query, "element_types", [])
        writer = get_stream_writer()
        writer({
            "type": "status",
            "phase": ["loading-data"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if not project_data:
            raise ValueError(f"No project found for project_id={query.project_id}")
        if not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData."
            logger.error(error_msg)
            raise TypeError(error_msg)

        if element_types:
            original_counts = {
                et: len(project_data.factsheet.model_dump().get(et, []))
                for et in element_types
            }
            writer({
                "type": "status",
                "phase": ["cleanup_elements"],
                "status": "starting",
                "data": {"element_types": element_types, "original_counts": original_counts},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
        return {"input_" : project_data}

    async def _save_elements_node(self, state : PipelineState, ):
        writer = get_stream_writer()
        
        query = state.query
        element_types = query.element_types
        results = state.input_.factsheet.model_dump(include = set(element_types))
        
        # Save each element type to DB
        for et, cleaned in results.items():
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
            await asyncio.to_thread(self.conversation_manager.replace_project_element,
                data=cleaned,
                project_id=query.project_id,
                table_name=f"project_{et}",
            )
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })

        writer({"type": "result", "data": {"success": True, "element_types": element_types}})

    async def _save_metadata_node(self,state):
        query = state.query
        project_data = state.input_
        writer = get_stream_writer()
        result = project_data.factsheet.model_dump(include={"title", "background"})

        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "starting",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        self.conversation_manager.upsert_project(result["title"], element_type="title", project_id=query.project_id)
        self.conversation_manager.upsert_project(result["background"], element_type="background", project_id=query.project_id)
        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "complete",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        writer({"type": "result", "data": {"success": True, "element_types": ["title", "background"]}})

