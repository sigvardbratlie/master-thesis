from langgraph.graph import StateGraph, END, START
from typing_extensions import Annotated
from models import AskAgentRequest, InitialInput, FactSheet, AttachmentModel, EmailModel
import operator
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer,get_config
from documents import DocumentProcessor, EmailHandler
import logging
import asyncio
from utils import AppConfig
from .context_manager import ContextManager
from datetime import datetime
from database import SupabaseStorageManager, SupabaseManager, BQVectorStore
from models import PipelineState, ProjectData, Claim, Damage, Event, Deadline, Party

from agent.utils import pick_llm

logger = logging.getLogger(__name__)


class ProjectClean:
    def __init__(self, name: str, config: AppConfig):
        self.name = name
        self.config = config or AppConfig()
        self.context_manager = ContextManager()
        self.document_processor = DocumentProcessor(config=self.config)
        self._semaphore = asyncio.Semaphore(self.config.async_tasks.max_concurrent_requests)
        self.storage = SupabaseStorageManager()
        self.vs = BQVectorStore(embedding_model=self.config.vectorstore.bigquery.embedding_model)
        self.conversation_manager = SupabaseManager()

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
        thread = get_config()
        llm_model = thread.get("configurable", {}).get("llm_model")
        self.context_manager.llm = pick_llm(llm_model, self.config)
        original_counts = {
            et: len(project_data.factsheet.model_dump().get(et, []))
            for et in element_types
        }
        logger.info(f'🧹 Starting clean for {element_types} | project={query.project_id} | model={llm_model}')
        logger.debug(f'Original counts: {original_counts}')

        results = await self.context_manager.clean_elements(element_types, project_data)

        cleaned_counts = {et: len(items) for et, items in results.items()}
        logger.info(f'✅ Clean complete | original={original_counts} → cleaned={cleaned_counts}')

        writer({
            "type": "status",
            "phase": ["cleanup_elements"],
            "status": "complete",
            "data": {
                "element_types": element_types,
                "original_counts": original_counts,
                "cleaned_counts": cleaned_counts,
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        _ET_TO_MODEL = {
            "claims": Claim, "damages": Damage, "events": Event,
            "deadlines": Deadline, "parties": Party,
        }
        for et, cleaned in results.items():
            model_cls = _ET_TO_MODEL.get(et)
            setattr(project_data.factsheet, et, [model_cls(**item) for item in cleaned] if model_cls else cleaned)
        return {"input_":  project_data}

    async def _clean_metadata_node(self, state : PipelineState):
        writer = get_stream_writer()
        query = state.query
        project_data = state.input_
        logger.info(f'🧹 Starting metadata clean | project={query.project_id}')
        writer({
            "type": "status",
            "phase": ["cleanup_metadata"],
            "status": "starting",
            "data": {"element_type": "metadata"},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        result = await self.context_manager.clean_metadata(project_data=project_data)
        if not result:
            logger.warning(f'clean_all_metadata returned empty result for project={query.project_id}')
        logger.info(f'✅ Metadata clean complete | title={bool(result.get("title"))} background={bool(result.get("background"))}')
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
        thread = get_config()
        llm_model = thread.get("configurable", {}).get("llm_model")
        self.context_manager.llm = pick_llm(llm_model, self.config)
        logger.info(f'📂 Loading project={query.project_id} | element_types={element_types} | model={llm_model}')

        writer({
            "type": "status",
            "phase": ["loading-data"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        # project_data = await asyncio.to_thread(
        #     self.conversation_manager.load_project,
        #     project_id=query.project_id
        # )
        factsheet = await asyncio.to_thread(
            self.conversation_manager.load_factsheet,
            project_id=query.project_id
        )
        project_data = ProjectData(factsheet=factsheet,
                                   attachments=[],
                                   emails=[])
        if not project_data:
            logger.error(f'No project found for project_id={query.project_id}')
            raise ValueError(f"No project found for project_id={query.project_id}")
        if not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData."
            logger.error(error_msg)
            raise TypeError(error_msg)

        logger.debug(f'Project loaded: attachments={len(project_data.attachments or [])}, emails={len(project_data.emails or [])}')

        if element_types:
            original_counts = {
                et: len(project_data.factsheet.model_dump().get(et, []))
                for et in element_types
            }
            logger.debug(f'Pre-clean counts: {original_counts}')
            writer({
                "type": "status",
                "phase": ["cleanup_elements"],
                "status": "starting",
                "data": {"element_types": element_types,
                         "original_counts": original_counts},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
        return {"input_" : project_data}

    async def _save_elements_node(self, state : PipelineState, ):
        writer = get_stream_writer()
        query = state.query
        element_types = query.element_types
        results = state.input_.factsheet.model_dump(include=set(element_types))
        logger.info(f'💾 Saving {element_types} to DB | project={query.project_id}')

        for et, cleaned in results.items():
            logger.debug(f'  Replacing {et}: {len(cleaned)} items')
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
            await asyncio.to_thread(self.conversation_manager.upsert_replace_project_element,
                data=cleaned,
                project_id=query.project_id,
                table_name=f"project_{et}",
                llm_model=query.llm_model,
            )
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })

        logger.info(f'✅ Save complete for {element_types} | project={query.project_id}')
        writer({"type": "result", "data": {"success": True, "element_types": element_types}})

    async def _save_metadata_node(self, state):
        query = state.query
        project_data = state.input_
        writer = get_stream_writer()
        result = project_data.factsheet.model_dump(include={"title", "background"})
        logger.info(f'💾 Saving metadata | project={query.project_id}')

        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "starting",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        self.conversation_manager.upsert_project(result["title"], element_type="title", project_id=query.project_id, llm_model=query.llm_model)
        self.conversation_manager.upsert_project(result["background"], element_type="background", project_id=query.project_id, llm_model=query.llm_model)
        logger.debug(f'Metadata saved: title={bool(result.get("title"))}, background={bool(result.get("background"))}')
        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "complete",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        logger.info(f'✅ Metadata save complete | project={query.project_id}')
        writer({"type": "result", "data": {"success": True, "element_types": ["title", "background"]}})

