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
                 clean_rate: int = None):
        self.data = data
        self.llm_model = llm_model
        self.agent_type: Literal["custom", "baseline", "baseline_rag"] = agent_type
        self.dataclass = Dataset(name=data.dataset_name)
        self.config = config or AppConfig()
        self.clean_rate = clean_rate

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
                       ) -> GatheredResultPayload:
        base_project_id = self.data.project_id 
        eval_run_id = str(uuid.uuid4())
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

        # Baseline agents never call initialize_project, so the project row is never created.
        # Create a minimal project entry now to satisfy the FK constraint in save_stream.
        #if self.agent_type == "baseline_rag":
            # await asyncio.to_thread(
            #     agent_class.conversation_manager.save_project,
            #     factsheet=FactSheet(events=[]),
            #     attachments=[],
            #     user_id=self.data.user_id,
            #     project_id=eval_run_id,
            #     query_id = str(uuid.uuid4()),
            #     session_id=str(uuid.uuid4()),
            # ) #saving a empty project for BASELINE + RAG for the purpose of using vector store on project_id
            # logger.info(f"Baseline Rag agent: created minimal project entry for {eval_run_id}")

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
                attachments = []
                docs = []
                for att in session.attachments:
                    att_model = self.parse_attachments(
                        attachment_path=att,
                        query_id=query_id,
                        session_id=runtime_session_id,
                        user_id=self.data.user_id,
                    )
                    attachments.append(att_model)

                    doc = self.dp.parse(content=b64decode(att_model.content), 
                                        file_type=att_model.file_type, 
                                        #force_metadata_model=False,
                                        metadata={"file_id": att_model.file_id, 
                                                  "session_id": runtime_session_id,
                                                  "project_id": eval_run_id,
                                                  "query_id": query_id,
                                                  "filename": att_model.filename,
                                                  "file_type": att_model.file_type,
                                                  "size": att_model.size,
                                                  "user_id": self.data.user_id,
                                                  })
                    att_model.body = self.dp.to_plain_text(doc)
                    docs.extend(doc)

                
                if self.agent_type == "custom":
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
                    
                    if idx % 2 != 0 or idx == len(self.data.sessions) - 1: #Clean after every 2 sessions or after the last session
                        cleanup_query = CleanupElementsRequest(
                                **input_obj.model_dump(),
                                element_types=["events", "claims"],)
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
                    logger.info(f'Embed documents for the purpose of the RAG run')
                    self.vs.add_documents(docs)
                    session.conversation[0].input = f"Project-Id: {eval_run_id}\n" + (str(session.init_query) if session.init_query else "") + "\n" + session.conversation[0].input

                
                else:
                    logger.info(f"Running session {idx} with agent type {self.agent_type} without initialization or cleanup as per configuration")
                    # if self.agent_type in ["baseline_rag"] and not include_init_query:
                    #     logger.info(f"Skipping initial query for session {idx} for agent type {self.agent_type} as per configuration")
                    # else:
                    #     conv_query_id = session.init_query_id or str(uuid.uuid4())
                    #     init_query = session.init_query or f"{session.session_name}. Se vedlagte dokumenter"
                    #     with tracing_context(metadata={"query_id": conv_query_id}):
                    #         await self.run_conv(
                    #             conv=ConversationTurn(input=init_query, answer=""),
                    #             agent_class=agent_class,
                    #             project_id=eval_run_id if self.agent_type in ["custom","baseline_rag"] else None,
                    #             session_id=runtime_session_id,
                    #             query_id=conv_query_id,
                    #             user_id=self.data.user_id,
                    #             attachments=attachments,
                    #             session_date=session.date,
                    #         )
                    attachments_text = f"Attachments for session {session.session_name} | Date {session.date}\n"
                    for att in attachments:
                        attachments_text += f"- {att.filename} ({att.file_type}, {att.size} bytes)\n"
                        attachments_text += f"{att.body}\n"
                    session.conversation[0].input = attachments_text + (str(session.init_query) if session.init_query else "") + "\n" + session.conversation[0].input
                

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
                        "clean_rate" : self.clean_rate,
                        "minimal_context" : self.config.agent.minimal_context}
        )