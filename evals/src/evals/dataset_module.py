import json
import logging
import re
from collections import defaultdict
from datetime import datetime
import uuid
from base64 import b64encode
from typing import Literal
from agent.agent import Agent
from models import AskAgentRequest, AttachmentModel
from agent.utils import PROMPT, PROMPT_BASELINE, PROMPT_BASELINE_RAG
from agent.tools import TOOLS, BASELINE_TOOLS, BASELINE_RAG_TOOLS
from langsmith.run_helpers import tracing_context
import os
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from google.cloud import storage

from .models import ConversationTurn, DatasetPayload, GatheredResultPayload, Session

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx", "xlsx", "csv", "txt", "md", "eml"}
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


class Dataset:
    def __init__(self, name: str = None, client: storage.Client = None, bucket_name: str = "master-thesis-prod"):
        self.name = name
        self.data: DatasetPayload | None = None
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_datasets(self) -> list[str]:
        seen = set()
        for blob in self.bucket.list_blobs(prefix="datasets/"):
            parts = blob.name.split("/")
            if len(parts) > 1 and parts[1]:
                seen.add(parts[1])
        return sorted(seen)

    # ── Format check ──────────────────────────────────────────────────────────

    def run_format_check(self) -> list[str]:
        wrong = []
        for blob in self.bucket.list_blobs(prefix=f"datasets/{self.name}/01_data/"):
            if not DATE_PATTERN.search(blob.name):
                logger.warning(f"Filename {blob.name} does not match expected date pattern.")
                wrong.append(blob.name)
        if not wrong:
            logger.info("All files have the correct date format.")
        return wrong

    # ── Load / save ───────────────────────────────────────────────────────────

    def load_dataset(self) -> DatasetPayload | None:
        path = f"datasets/{self.name}/dataset_{self.name}.json"
        try:
            raw = self.bucket.blob(path).download_as_string()
            self.data = DatasetPayload.model_validate_json(raw.decode("utf-8"))
            return self.data
        except Exception:
            logger.warning(f"Dataset file {path} not found or is invalid JSON.")
            return None

    def load_results(self) -> dict | None:
        data = {}
        path = f"datasets/{self.name}/04_results"
        for file in self.bucket.list_blobs(prefix=path):
            if file.name.endswith(".json"):
                try:
                    data[file.name] = json.loads(file.download_as_string().decode("utf-8"))
                except Exception as e:
                    logger.warning(f"Failed to load {file.name}: {e}")
        return data

    def save_results(self, data: GatheredResultPayload) -> None:
        path = f"datasets/{data.dataset_name}/04_results/{data.llm_model}_{data.agent_type}_{data.eval_run_id}.json"
        try:
            self.bucket.blob(path).upload_from_string(
                json.dumps(data.model_dump(), indent=4), content_type="application/json"
            )
            logger.info(f"Results saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise

    # ── File helpers ──────────────────────────────────────────────────────────

    def get_all_data_files(self) -> tuple[dict[str, list[str]], list[str]]:
        """Return (date → [blob_paths], sorted_dates) for all supported files."""
        prefix = f"datasets/{self.name}/01_data/"
        date_to_files: dict[str, list[str]] = defaultdict(list)

        for blob in self.bucket.list_blobs(prefix=prefix):
            ext = blob.name.rsplit(".", 1)[-1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            match = DATE_PATTERN.search(blob.name)
            if not match:
                logger.debug(f"File without date: {blob.name}")
                continue
            date_to_files[match.group(1)].append(blob.name)

        sorted_dates = sorted(date_to_files.keys())
        logger.info(f"Found {sum(len(v) for v in date_to_files.values())} files under {prefix}")
        return dict(date_to_files), sorted_dates

    def get_attachments(self, start_date: str = None, end_date: str = None) -> list[str]:
        """Return blob paths filtered by optional date range (inclusive, YYYY-MM-DD strings)."""
        date_to_files, _ = self.get_all_data_files()
        result = []
        for date_str, paths in date_to_files.items():
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            result.extend(paths)
        if not result:
            logger.warning("No attachments found within the specified date range.")
        return result

    # ── Attachment assignment ─────────────────────────────────────────────────

    def assign_session_attachments(self) -> None:
        """Assign data files to sessions based on chronological date windows.

        For each session, files whose extracted date falls in the half-open
        interval (previous_session_date, session_date] are assigned as
        attachments. Files already assigned to an earlier session are excluded.

        Mutates self.data in place. Raises ValueError if data is not loaded.
        """
        if not self.data:
            raise ValueError("No data loaded. Call load_dataset() first.")

        date_to_files, _ = self.get_all_data_files()

        def _parse(s: str | None):
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None

        date_to_files_dt = {_parse(d): files for d, files in date_to_files.items()}
        file_dates_sorted = sorted(date_to_files_dt.keys())

        seen: set[str] = set()
        prev_dt = None

        for session in self.data.sessions:
            current_dt = _parse(session.date)
            if current_dt is None:
                session.attachments = []
                continue

            candidates = [
                f
                for fd in file_dates_sorted
                if (prev_dt is None or fd > prev_dt) and fd <= current_dt
                for f in date_to_files_dt[fd]
            ]
            new_files = [f for f in candidates if f not in seen]
            seen.update(new_files)
            session.attachments = new_files

            logger.info(
                f"Session {session.session_name} | "
                f"{prev_dt or '–'} → {current_dt} | "
                f"{len(candidates)} candidates, {len(new_files)} new"
            )
            prev_dt = current_dt

    def assign_session_attachments_baseline(self) -> None:
        """Assign data files to sessions cumulatively for baseline (non-custom) models.

        Unlike assign_session_attachments(), which uses a sliding window per session,
        this assigns all files up to and including each session's date. This ensures
        baseline models receive the full available context at each session, since they
        have no factsheet or accumulated knowledge from prior sessions.

        Mutates self.data in place. Raises ValueError if data is not loaded.
        """
        if not self.data:
            raise ValueError("No data loaded. Call load_dataset() first.")

        date_to_files, _ = self.get_all_data_files()

        def _parse(s: str | None):
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None

        date_to_files_dt = {_parse(d): files for d, files in date_to_files.items()}
        file_dates_sorted = sorted(date_to_files_dt.keys())

        for session in self.data.sessions:
            current_dt = _parse(session.date)
            if current_dt is None:
                session.attachments = []
                continue

            attachments = [
                f
                for fd in file_dates_sorted
                if fd <= current_dt
                for f in date_to_files_dt[fd]
            ]
            session.attachments = attachments

            logger.info(
                f"Session {session.session_name} | "
                f"– → {current_dt} | "
                f"{len(attachments)} attachments (cumulative)"
            )


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
        pool = AsyncConnectionPool(conninfo=connection_string, open=False)
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

    async def run_agent(self) -> GatheredResultPayload:
        use_factsheet = self.agent_type == "custom"

        base_project_id = self.data.project_id
        runtime_project_id = (
            base_project_id if self.agent_type == "custom"
            else f"{base_project_id}_{self.agent_type}"
        )

        save_to_storage = self.agent_type == "custom"
        embed_to_vectorstore = self.agent_type in ("custom", "baseline_rag")

        tools = _TOOLS_MAP[self.agent_type]
        prompt = _PROMPT_MAP[self.agent_type]

        agent_class = await self.init_agent(
            use_factsheet=use_factsheet,
            save_to_storage=save_to_storage,
            embed_to_vectorstore=embed_to_vectorstore,
            tools=tools,
            prompt=prompt,
        )
        logger.info("=========== STARTING COLLECTING LLM RESPONSES ===========")
        logger.info(
            f'Dataset: {self.data.dataset_name} | '
            f'LLM Model: {self.llm_model} | '
            f'Agent Type: {self.agent_type} | '
            f'Sessions: {len(self.data.sessions)} | '
            f'Project (runtime): {runtime_project_id} | '
            f'User: {self.data.user_id}\n\n'
        )
        eval_run_id = str(uuid.uuid4())

        with tracing_context(
            tags=[eval_run_id],
            metadata={"eval_run_id": eval_run_id, "llm_model": self.llm_model, "agent_type": self.agent_type, "runtime_project_id": runtime_project_id},
        ):
            for idx, session in enumerate(self.data.sessions):
                runtime_session_id = str(uuid.uuid4())
                session.runtime_session_id = runtime_session_id
                logger.info(
                    f"Session {idx} | {session.date} | "
                    f"{session.session_name} | "
                    f"{len(session.attachments)} attachments"
                )
                query_id = str(uuid.uuid4())
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
                    project_id=runtime_project_id,
                    attachments=attachments,
                )
                if use_factsheet:
                    if idx == 0:
                        async for response in agent_class.initialize_project(
                            query=input_obj, user_id=self.data.user_id
                        ):
                            logger.debug(f"Init response: {response}")
                    else:
                        async for response in agent_class.update_project(
                            query=input_obj, user_id=self.data.user_id
                        ):
                            logger.debug(f"Update response: {response}")
                else:
                    conv_query_id = str(uuid.uuid4())
                    await self.run_conv(
                        conv=ConversationTurn(input=session.init_query, answer=""),
                        agent_class=agent_class,
                        project_id=runtime_project_id,
                        session_id=runtime_session_id,
                        query_id=conv_query_id,
                        user_id=self.data.user_id,
                        attachments=attachments,
                    )

                for conv in session.conversation:
                    conv_query_id = conv.query_id or str(uuid.uuid4())
                    await self.run_conv(
                        conv=conv,
                        agent_class=agent_class,
                        project_id=runtime_project_id,
                        session_id=runtime_session_id,
                        query_id=conv_query_id,
                        user_id=self.data.user_id,
                    )

        return GatheredResultPayload(
            dataset_name=self.data.dataset_name,
            project_id=self.data.project_id,
            user_id=self.data.user_id,
            sessions=self.data.sessions,
            eval_run_id=eval_run_id,
            llm_model=self.llm_model,
            agent_type=self.agent_type,
            runtime_project_id=runtime_project_id,
        )
