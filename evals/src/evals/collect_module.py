import asyncio
import logging
from datetime import datetime
import uuid
from base64 import b64encode, b64decode
from typing import Literal
import os

from langsmith.run_helpers import tracing_context
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from agent.agent import Agent
from agent import ProjectPipeline, ProjectClean
from models import AskAgentRequest, AttachmentModel, CleanupElementsRequest
from models.project_models import FactSheet
from agent.utils import to_thread_config
from agent.tools import TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS
from .dataset_module import Dataset
from .models import ConversationTurn, DatasetPayload, GatheredResultPayload, TimeCount
from utils import AppConfig
from database import BQVectorStore
from documents import DocumentProcessor

logger = logging.getLogger(__name__)



_TOOLS_MAP = {
    "custom": TOOLS,
    "baseline": BASELINE_TOOLS,
    "baseline_rag": BASELINE_RAG_TOOLS,
}


class CollectAgentResult:
    def __init__(self, data: DatasetPayload, 
                llm_model: str = "google_gemini-2.5-pro", 
                 agent_type: Literal["custom", "baseline", "baseline_rag"] = "custom",
                 config : AppConfig = None,
                 ):
        self.data = data
        self.llm_model = llm_model
        self.agent_type: Literal["custom", "baseline", "baseline_rag"] = agent_type
        self.dataclass = Dataset(name=data.dataset_name)
        self.config = config or AppConfig()

        self.vs = BQVectorStore()
        self.dp = DocumentProcessor(config=self.config)

    async def init_agent(self, 
                         tools=None,):
        connection_string = os.getenv("SUPABASE_DB_URL")
        pool = AsyncConnectionPool(conninfo=connection_string, open=False, min_size=1, max_size=2,
                                   kwargs={"autocommit": True, "prepare_threshold": 0})
        await pool.open(wait=True, timeout=15.0)
        checkpointer = AsyncPostgresSaver(pool)
        agent = Agent(
            tools=tools,
            checkpointer=checkpointer,
            config=self.config,
        )
        logger.info("Agent initialized with AsyncPostgresSaver checkpointer")
        return agent

    def init_pipeline(self,):
        pm = ProjectPipeline(name="ProjectPipeline", config=self.config)
        clean = ProjectClean(name="ProjectClean", config=self.config)
        return pm, clean

    def file_type_map(self, blob_path: str):
        mapping = {
            "txt": "text/plain",
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "md": "text/markdown",
            "eml": "message/rfc822",
        }
        return mapping.get(blob_path.split(".")[-1], None)

    def parse_attachments(self, attachment_path: str, query_id: str, session_id: str, user_id: str):
        bytes_content = self.dataclass.bucket.blob(attachment_path).download_as_bytes()
        content = b64encode(bytes_content).decode("utf-8")
        file_id = str(uuid.uuid4())
        return AttachmentModel(
            filename=attachment_path,
            file_type=self.file_type_map(attachment_path),
            content=content,
            file_id=file_id,
            path=f"{user_id}/{session_id}/{file_id}.{attachment_path.split('.')[-1]}",
            size=len(content),
            query_id=query_id,
        )

    async def run_conv(self, conv: ConversationTurn, agent_class, project_id, session_id, query_id, user_id, attachments=[], session_date=None):
        turn_starttime = datetime.now() 
        input_obj = AskAgentRequest(
            question= f"Dato : {session_date} \n" + conv.input,
            session_id=session_id,
            llm_model=self.llm_model,
            query_id=query_id,
            project_id=project_id,
            attachments=attachments,
        )
        answer = "No content"
        async for response in agent_class.stream_response(query=input_obj, user_id=user_id):
            if response.get("type") == "ai":
                answer = response.get("data", {}).get("token_stream", "No content")
        conv.model_response = answer
        turn_endtime = datetime.now()
        conv.time_counts = TimeCount(
            starttime=turn_starttime,
            endtime=turn_endtime,
            duration_seconds=(turn_endtime - turn_starttime).total_seconds(),
        )

    async def run_agent(self, 
                       eval_run_id_reuse : str = None,
                       clean_rate : int = 2) -> GatheredResultPayload:
        base_project_id = self.data.project_id 
        eval_run_id = eval_run_id_reuse or str(uuid.uuid4())
        tools = _TOOLS_MAP[self.agent_type]

        agent_class = await self.init_agent(
            tools=tools,
        )
        pm, clean = self.init_pipeline(
        )
        logger.info("=========== Running agent ===========")
        logger.info(
            f'Dataset: {self.data.dataset_name} | '
            f'LLM Model: {self.llm_model} | '
            f'Agent Type: {self.agent_type} | '
            f'Sessions: {len(self.data.sessions)} | '
            f'Project (runtime): {eval_run_id} | '
            f'User: {self.data.user_id}\n\n'
        )

        semaphore = asyncio.Semaphore(self.config.async_tasks.storage.max_concurrent_requests)

        async def download_and_parse(att_path, query_id, session_id, project_id, user_id):
            async with semaphore:
                att_model = await asyncio.to_thread(
                    self.parse_attachments,
                    attachment_path=att_path,
                    query_id=query_id,
                    session_id=session_id,
                    user_id=user_id,
                )
                doc = await asyncio.to_thread(
                    self.dp.parse_to_docs,
                    content=b64decode(att_model.content),
                    file_type=att_model.file_type,
                    metadata={
                        "file_id": att_model.file_id,
                        "session_id": session_id,
                        "project_id": project_id,
                        "query_id": query_id,
                        "filename": att_model.filename,
                        "file_type": att_model.file_type,
                        "size": att_model.size,
                        "user_id": user_id,
                    },
                )
                att_model.body = self.dp.to_plain_text(doc)
                return att_model, doc

        starttime = datetime.now()
        with tracing_context(
            tags=[eval_run_id],
            metadata={"eval_run_id": eval_run_id, "llm_model": self.llm_model, "agent_type": self.agent_type, "project_id": base_project_id},
        ):
            for idx, session in enumerate(self.data.sessions):
                runtime_session_id = str(uuid.uuid4())
                session_starttime = datetime.now()
                session.runtime_session_id = runtime_session_id
                logger.info(
                    f"Session {idx} | {session.date} | "
                    f"{session.session_name} | "
                    f"{len(session.attachments)} attachments"
                )
                query_id = session.init_query_id if session.init_query_id else str(uuid.uuid4())

                parsed_results = await asyncio.gather(*[
                    download_and_parse(att, query_id, runtime_session_id, eval_run_id, self.data.user_id)
                    for att in session.attachments
                ])
                attachments = [att_model for att_model, _ in parsed_results]
                docs = [d for _, doc_list in parsed_results for d in doc_list]

                if self.agent_type == "custom" and not eval_run_id_reuse:
                    input_obj = AskAgentRequest(
                    question=session.init_query,
                    session_id=runtime_session_id,
                    llm_model=self.llm_model,
                    query_id=query_id,
                    project_id=eval_run_id if self.agent_type in ["custom",] else None,
                    attachments=attachments,
                    )
                    if idx == 0:
                        thread = to_thread_config(query=input_obj, user_id=self.data.user_id)
                        init_graph = pm.compile_init_pipeline()
                        async for chunk in init_graph.astream({"query": input_obj}, config=thread, stream_mode="custom"):
                            logger.debug(f"Init response: {chunk}")
                    else:
                        thread = to_thread_config(query=input_obj, user_id=self.data.user_id)
                        update_graph = pm.compile_update_pipeline()
                        async for chunk in update_graph.astream({"query": input_obj}, config=thread, stream_mode="custom"):
                            logger.debug(f"Update response: {chunk}")
                    
                    if idx % clean_rate != 0 or idx == len(self.data.sessions) - 1: 
                        cleanup_query = CleanupElementsRequest(
                                **input_obj.model_dump(),
                                element_types=["events", "claims", "damages"],)
                        clean_thread = to_thread_config(query=cleanup_query, user_id=self.data.user_id)
                        clean_graph = clean.compile_clean_elements()
                        async for chunk in clean_graph.astream({"query": cleanup_query}, config=clean_thread, stream_mode="custom"):
                            logger.debug(f"Cleanup response: {chunk}")


                    
                    endtime_init = datetime.now()
                    session.init_query_time_count = TimeCount(
                        starttime=session_starttime,
                        endtime=endtime_init,
                        duration_seconds=(endtime_init - session_starttime).total_seconds(),
                    )
                    logger.debug(f"Session {idx} initialization completed in {session.init_query_time_count.duration_seconds:.2f} seconds")
                
                elif self.agent_type == "baseline_rag":
                    if not eval_run_id_reuse:
                        logger.info(f'Embed documents for the purpose of the RAG run')
                        await asyncio.to_thread(self.vs.add_documents, docs)
                    session.conversation[0].input = f"Project-Id: {eval_run_id}\n" + (str(session.init_query) if session.init_query else "") + "\n" + session.conversation[0].input

                
                else:
                    logger.info(f"Running session {idx} with agent type {self.agent_type} without initialization or cleanup as per configuration")
                    

                for conv in session.conversation:
                    conv_query_id = conv.query_id or str(uuid.uuid4())
                    with tracing_context(metadata={"query_id": conv_query_id}):
                        await self.run_conv(
                            conv=conv,
                            agent_class=agent_class,
                            project_id=eval_run_id if self.agent_type in ["custom",] else None,
                            session_id=runtime_session_id,
                            query_id=conv_query_id,
                            user_id=self.data.user_id,
                            session_date=session.date,
                            )
                session_endtime = datetime.now()
                session.time_counts = TimeCount(
                    starttime=session_starttime,
                    endtime=session_endtime,
                    duration_seconds=(session_endtime - session_starttime).total_seconds(),
                )
                logger.debug(f"Session {idx} completed in {session.time_counts.duration_seconds:.2f} seconds")
        endtime = datetime.now()
        return GatheredResultPayload(
            dataset_name=self.data.dataset_name,
            project_id=self.data.project_id,
            user_id=self.data.user_id,
            sessions=self.data.sessions,
            eval_run_id=eval_run_id,
            llm_model=self.llm_model,
            agent_type=self.agent_type,
            time_counts=TimeCount(
                starttime=starttime,
                endtime=endtime,
                duration_seconds=(endtime - starttime).total_seconds(),
            ),
            metadata = {"significance" : self.config.agent.significance, 
                        "eval_run_id_reuse" : eval_run_id_reuse,
                        "minimal_context" : self.config.agent.minimal_context}
        )