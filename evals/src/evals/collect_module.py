import logging
from datetime import datetime
import uuid
from base64 import b64encode
from typing import Literal
import os

from langsmith.run_helpers import tracing_context
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from agent.agent import Agent
from models import AskAgentRequest, AttachmentModel,CleanupElementsRequest
from agent.utils import PROMPT, PROMPT_BASELINE, PROMPT_BASELINE_RAG
from agent.tools import TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS
from .dataset_module import Dataset
from .models import ConversationTurn, DatasetPayload, GatheredResultPayload, TimeCount

logger = logging.getLogger(__name__)



_TOOLS_MAP = {
    "custom": TOOLS,
    "baseline": BASELINE_TOOLS,
    "baseline_rag": BASELINE_RAG_TOOLS,
}

_PROMPT_MAP = {
    "custom": PROMPT,
    "baseline": PROMPT_BASELINE,
    "baseline_rag": PROMPT_BASELINE_RAG,
}


class CollectAgentResult:
    def __init__(self, data: DatasetPayload, llm_model: str = "google_gemini-2.5-pro", agent_type: Literal["custom", "baseline", "baseline_rag"] = "custom"):
        self.data = data
        self.llm_model = llm_model
        self.agent_type: Literal["custom", "baseline", "baseline_rag"] = agent_type
        self.dataclass = Dataset(name=data.dataset_name)

    async def init_agent(self, use_factsheet: bool = True, save_to_storage: bool = True, embed_to_vectorstore: bool = True, tools=None, prompt: str = None):
        connection_string = os.getenv("SUPABASE_DB_URL")
        pool = AsyncConnectionPool(conninfo=connection_string, open=False, min_size=1, max_size=2)
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        agent = Agent(
            use_factsheet=use_factsheet,
            save_to_storage=save_to_storage,
            embed_to_vectorstore=embed_to_vectorstore,
            tools=tools,
            prompt=prompt,
            checkpointer=checkpointer,
        )
        logger.info("Agent initialized with AsyncPostgresSaver checkpointer")
        return agent

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

    async def run_conv(self, conv: ConversationTurn, agent_class, project_id, session_id, query_id, user_id, attachments=[]):
        turn_starttime = datetime.now() 
        input_obj = AskAgentRequest(
            question=conv.input,
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

    async def run_agent(self, embed_to_vectorstore: bool = True, save_to_storage: bool = True) -> GatheredResultPayload:
        use_factsheet = self.agent_type == "custom"

        base_project_id = self.data.project_id  # original case ID from dataset
        # eval_run_id doubles as the Supabase project_id for this run,
        # ensuring full isolation: N identical runs never share a project row.
        eval_run_id = str(uuid.uuid4())

        tools = _TOOLS_MAP[self.agent_type]
        prompt = _PROMPT_MAP[self.agent_type]

        agent_class = await self.init_agent(
            use_factsheet=use_factsheet,
            save_to_storage=save_to_storage,
            embed_to_vectorstore=embed_to_vectorstore,
            tools=tools,
            prompt=prompt,
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
                query_id = session.init_query_id
                attachments = [
                    self.parse_attachments(
                        attachment_path=att,
                        query_id=query_id,
                        session_id=runtime_session_id,
                        user_id=self.data.user_id,
                    )
                    for att in session.attachments
                ]

                input_obj = AskAgentRequest(
                    question=session.init_query,
                    session_id=runtime_session_id,
                    llm_model=self.llm_model,
                    query_id=query_id,
                    project_id=eval_run_id,
                    attachments=attachments,
                )
                if use_factsheet:
                    if idx == 0:
                        async for response in agent_class.initialize_project(
                            query=input_obj, user_id=self.data.user_id
                        ):
                            logger.debug(f"Init response: {response}")
                    else:
                        if idx % 2 == 0: #cleanup every 2 sessions to avoid too much context buildup, which can lead to token limits being hit and increased costs
                            cleanup_query = CleanupElementsRequest(
                                **input_obj.model_dump(),
                                element_types = ["parties", "events", "damages"])
                            async for response in agent_class.cleanup_elements(
                                query = cleanup_query):
                                logger.debug(f"Cleanup response: {response}")

                        async for response in agent_class.update_project(
                            query=input_obj, user_id=self.data.user_id
                        ):
                            logger.debug(f"Update response: {response}")
                    endtime_init = datetime.now()
                    session.init_query_time_count = TimeCount(
                        starttime=session_starttime,
                        endtime=endtime_init,
                        duration_seconds=(endtime_init - session_starttime).total_seconds(),
                    )
                    logger.debug(f"Session {idx} initialization completed in {session.init_query_time_count.duration_seconds:.2f} seconds")
                else:
                    conv_query_id = str(uuid.uuid4())
                    with tracing_context(metadata={"query_id": conv_query_id}):
                        await self.run_conv(
                            conv=ConversationTurn(input=session.init_query, answer=""),
                            agent_class=agent_class,
                            project_id=eval_run_id,
                            session_id=runtime_session_id,
                            query_id=conv_query_id,
                            user_id=self.data.user_id,
                            attachments=attachments,
                        )

                for conv in session.conversation:
                    conv_query_id = conv.query_id or str(uuid.uuid4())
                    with tracing_context(metadata={"query_id": conv_query_id}):
                        await self.run_conv(
                            conv=conv,
                            agent_class=agent_class,
                            project_id=eval_run_id,
                            session_id=runtime_session_id,
                            query_id=conv_query_id,
                            user_id=self.data.user_id,
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
            #runtime_project_id=eval_run_id,
            time_counts=TimeCount(
                starttime=starttime,
                endtime=endtime,
                duration_seconds=(endtime - starttime).total_seconds(),
            ),
        )

    #async def run_agent_mult(self, embed_to_vectorstore: bool = True, save_to_storage: bool = True)