from langgraph.graph import StateGraph, END, START
from models import FactSheet, AttachmentModel, EmailModel

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer, get_config
from documents import DocumentProcessor, EmailHandler, PDFHandler, EmailThreadParser
import logging
import asyncio
from utils import AppConfig
from .context_manager import ContextManager
from datetime import datetime
import base64
import tiktoken
import email as python_email
from database import SupabaseManager, BQVectorStore, GCSManager

from models import PipelineState, AskAgentRequest, ProjectData, InitialInput

from agent.utils import pick_llm
logger = logging.getLogger(__name__)


class ProjectPipeline:
    def __init__(self, name: str, config: AppConfig,):
        self.name = name
        self.config = config or AppConfig()
        self.context_manager = ContextManager(config=self.config)
        self.document_processor = DocumentProcessor(config=self.config)
        self._semaphore_llm = asyncio.Semaphore(self.config.async_tasks.llm.max_concurrent_requests)
        self._semaphore_db = asyncio.Semaphore(self.config.async_tasks.database.max_concurrent_requests)
        self._semaphore_storage = asyncio.Semaphore(self.config.async_tasks.storage.max_concurrent_requests)
        self._semaphore_vs = asyncio.Semaphore(self.config.async_tasks.vectorstore.max_concurrent_requests)
        self.storage = GCSManager(config=self.config)  #SupabaseStorageManager(config=self.config)
        self.vs = BQVectorStore(embedding_model=self.config.vectorstore.bigquery.embedding_model)
        self.conversation_manager = SupabaseManager()

    # =========== PIPELINE COMPILATION ===========
    def compile_init_pipeline(self):
        logger.info(f'\n\n ================ COMPILING INIT PIPELINE ================ \n\n')
        workflow = StateGraph(PipelineState)

        workflow.add_node("collapse_emails", self._collapse_emails_node)
        workflow.add_node("extract_emails", self._extract_emails_node)
        workflow.add_node("initialize_input", self._initialize_input_node)
        workflow.add_node("storage", self._storage_node)
        workflow.add_node("parsing", self._parsing_node)
        workflow.add_node("embedding", self._embedding_node)
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("update_metadata", self._update_metadata_node)
        workflow.add_node("save", self._save_init_node)
        workflow.add_node("qc_analysis", self._qc_analysis_node)

        workflow.add_edge(START, "collapse_emails")
        workflow.add_edge(START, "initialize_input")
        
        workflow.add_edge("collapse_emails", "extract_emails")
        workflow.add_edge("extract_emails", "parsing")
        workflow.add_edge("extract_emails", "storage")
        workflow.add_edge("parsing", "embedding")
        workflow.add_edge(["parsing", "initialize_input"], "analyze")
        workflow.add_edge("analyze", "update_metadata")
        workflow.add_edge("analyze", "qc_analysis")
        workflow.add_edge("update_metadata", "save")

        workflow.add_edge("embedding", END)
        workflow.add_edge("save", END)
        workflow.add_edge("storage", END)
        workflow.add_edge("qc_analysis", END)
        return workflow.compile()

    def compile_update_pipeline(self):
        logger.info(f'\n\n ================ COMPILING UPDATE PIPELINE ================ \n\n')
        workflow = StateGraph(PipelineState)

        workflow.add_node("load_project_data", self._load_project_data)
        workflow.add_node("collapse_emails", self._collapse_emails_node)
        workflow.add_node("extract_emails", self._extract_emails_node)
        workflow.add_node("storage", self._storage_node)
        workflow.add_node("parsing", self._parsing_node)
        workflow.add_node("embedding", self._embedding_node)
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("update_metadata", self._update_metadata_node)
        workflow.add_node("save", self._save_update_node)
        workflow.add_node("qc_analysis", self._qc_analysis_node)

        workflow.add_edge(START, "load_project_data")
        workflow.add_edge(START, "collapse_emails")
        workflow.add_edge("collapse_emails", "extract_emails")
        workflow.add_edge("extract_emails", "parsing")
        workflow.add_edge("extract_emails", "storage")
        workflow.add_edge("parsing", "embedding")
        workflow.add_edge(["load_project_data", "parsing"], "analyze")
        workflow.add_edge("analyze", "update_metadata")
        workflow.add_edge("update_metadata", "save")
        workflow.add_edge("analyze", "qc_analysis")


        workflow.add_edge("embedding", END)
        workflow.add_edge("save", END)
        workflow.add_edge("storage", END)
        workflow.add_edge("qc_analysis", END)
        return workflow.compile()

    # =========== HELPER METHODS ===========
    def _prepare_analysis_tasks(self, state: PipelineState) -> list:
        """Route attachments to doc/email analysis tasks, batching emails by size/count."""

        async def analyze_docs_with_limit(attachments: list[AttachmentModel], input_, thread: RunnableConfig):
            async with self._semaphore_llm:
                _writer = get_stream_writer()
                filenames = [a.filename for a in attachments if a.filename]
                _writer({
                    "type": "status",
                    "phase": ["analyze_docs"],
                    "status": "starting",
                    "data": {"specs": ", ".join(filenames), "count": len(attachments)},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": state.query.query_id,
                })
                result = await self.context_manager.analyze_docs(
                    input_=input_,
                    attachments=attachments,
                    config=thread,
                )
                if self.config.async_tasks.llm.throttle_value > 0:
                    await asyncio.sleep(self.config.async_tasks.llm.throttle_value)
                result["_source_filenames"] = filenames
                return result

        async def analyze_emails_with_limit(emails: list[EmailModel], input_, thread: RunnableConfig):
            async with self._semaphore_llm:
                _writer = get_stream_writer()
                subjects = [e.subject for e in emails if e.subject]
                _writer({
                    "type": "status",
                    "phase": ["analyze_emails"],
                    "status": "starting",
                    "data": {"specs": ", ".join(subjects), "count": len(emails)},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": state.query.query_id,
                })
                result = await self.context_manager.analyze_emails(
                    input_=input_,
                    emails=emails,
                    config=thread,
                )
                if self.config.async_tasks.llm.throttle_value > 0:
                    await asyncio.sleep(self.config.async_tasks.llm.throttle_value)
                return result

        attachments = state.query.attachments
        input_ = state.input_
        thread = get_config()

        enc = tiktoken.encoding_for_model("gpt-4")

        size_threshold = self.config.project.size_threshold
        token_threshold = self.config.project.token_threshold
        max_attachments = self.config.project.max_attachments
        max_emails = self.config.project.max_emails

        email_attachments = []
        email_size_counter = 0
        email_token_counter = 0

        doc_attachments = []
        doc_size_counter = 0
        doc_token_counter = 0

        doc_tasks = []

        logger.info(f"📎 Preparing analysis tasks for {len(attachments or [])} attachment(s) | project_id={state.query.project_id}")

        # =========== DOCUMENTS (PDF, WORD, ETC) =============
        for att in attachments or []:
            if att.file_type != "message/rfc822":
                att_size = len(att.body.encode("utf-8")) if att.body else att.size or 0
                token_count = len(enc.encode(att.body)) if att.body else 0
                if doc_size_counter + att_size <= size_threshold and doc_token_counter + token_count <= token_threshold and len(doc_attachments) < max_attachments:
                    doc_attachments.append(att)
                    doc_size_counter += att_size
                    doc_token_counter += token_count
                else:
                    if doc_attachments:  # Only dispatch if there are attachments to analyze
                        logger.info(f"📦 Dispatching doc batch: {len(doc_attachments)} file(s), {doc_size_counter / 1024:.1f}KB")
                        doc_tasks.append(analyze_docs_with_limit(doc_attachments, input_, thread))
                    if token_count > token_threshold:
                        logger.warning(f"⚠️ Skipping attachment '{att.filename}': {token_count} tokens exceeds threshold {token_threshold}")
                        doc_attachments = []
                        doc_size_counter = 0
                        doc_token_counter = 0
                    else:
                        doc_attachments = [att]
                        doc_size_counter = att_size
                        doc_token_counter = token_count

        if doc_attachments:
            logger.info(f"📦 Dispatching final doc batch: {len(doc_attachments)} file(s), {doc_size_counter / 1024:.1f}KB")
            doc_tasks.append(analyze_docs_with_limit(doc_attachments, input_, thread))

        # ======== EMAILS (EML) ============
        emails_to_process = state.email_models or []
        for email in emails_to_process:
            email_size = len(email.body_text.encode("utf-8")) if email.body_text else email.size or 0
            token_count = len(enc.encode(email.body_text)) if email.body_text else 0
            if email_size_counter + email_size <= size_threshold and email_token_counter + token_count <= token_threshold and len(email_attachments) < max_emails:
                email_attachments.append(email)
                email_size_counter += email_size
                email_token_counter += token_count
            else:
                if email_attachments:  # Only dispatch if there are emails to analyze
                    logger.info(f"📦 Dispatching email batch: {len(email_attachments)} email(s), {email_size_counter / 1024:.1f}KB")
                    doc_tasks.append(analyze_emails_with_limit(email_attachments, input_, thread))
                email_attachments = [email]
                email_size_counter = email_size
                email_token_counter = token_count

        if email_attachments:
            logger.info(f"📦 Dispatching final email batch: {len(email_attachments)} email(s), {email_size_counter / 1024:.1f}KB")
            doc_tasks.append(analyze_emails_with_limit(email_attachments, input_, thread))
        return doc_tasks

    def mk_update_query_from_session(self,
                                        query : AskAgentRequest,
                                        ) -> AskAgentRequest:
        '''Update the project with new input and attachments, using a given session as context.'''
        input_attachments = query.attachments or []
        new_input = ""
        session_conv = self.conversation_manager.load_session_history(session_id=query.session_id)
        if session_conv.attachments:
            for att in session_conv.attachments:
                content = self.storage.read_attachment(att.path) if att.path else None
                if content:
                    att.content = base64.b64encode(content.encode() if isinstance(content, str) else content).decode()
                    input_attachments.append(att)
        if session_conv.events:
            new_input += "Session messages\n"
            for event in session_conv.events:
                if event.type == "human" and event.content:
                    new_input += f"- {event.content}\n"

        updated_query = AskAgentRequest(
            project_id=query.project_id,
            session_id=query.session_id,
            llm_model=query.llm_model,
            query_id=query.query_id,
            attachments=input_attachments,
            question=new_input or query.question,
        )
        return updated_query

    # =========== NODES ===========
    async def _parsing_node(self, state: PipelineState):
        """Parse documents and return parsed results."""
        writer = get_stream_writer()
        attachments = state.query.attachments
        query_id = state.query.query_id
        user_id = get_config().get("configurable", {}).get("user_id")
        session_id = state.query.session_id
        project_id = state.query.project_id
        shortened_emails = state.collapsed_emails
        shortened_email_ids = set(shortened_emails.keys()) if shortened_emails else None

        docs_by_file = {}
        if not attachments:
            return {"docs_by_file": docs_by_file}

        filtered_attachments = [
            att for att in attachments
            if not (att.file_type == "message/rfc822" and shortened_email_ids is not None and att.file_id not in shortened_email_ids)
        ]

        writer({
            "type": "status",
            "phase": ["parse_documents"],
            "status": "starting",
            "data": {"total": len(filtered_attachments)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query_id,
        })

        async def parse_with_limit(att):
            async with self._semaphore_storage:
                content_bytes = base64.b64decode(att.content)
                ocr_needed = None
                if att.file_type == "application/pdf":
                    ocr_needed = PDFHandler(
                        aws_region=self.config.storage.aws.region,
                        aws_bucket_name=self.config.storage.aws.bucket_name,
                    )._needs_ocr(content_bytes)

                writer({
                    "type": "status",
                    "phase": ["parse_doc"],
                    "status": "ocr" if ocr_needed else "starting",
                    "data": {"filename": att.filename, "file_id": att.file_id, "total": len(filtered_attachments)},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query_id,
                })

                extracted_docs = await asyncio.to_thread(
                    self.document_processor.parse_to_docs,
                    content=content_bytes,
                    file_type=att.file_type,
                    ocr=ocr_needed,
                    metadata={
                        "file_id": att.file_id,
                        "filename": att.filename,
                        "user_id": user_id,
                        "query_id": query_id,
                        "path": att.path,
                        "file_type": att.file_type,
                        "project_id": project_id,
                        "size": att.size,
                        "session_id": session_id,
                        "embedding_model": self.vs.embedding_model,
                    },
                )

                att.body = self.document_processor.to_plain_text(extracted_docs)

                writer({
                    "type": "status",
                    "phase": ["parse_doc"],
                    "status": "complete",
                    "data": {"filename": att.filename, "file_id": att.file_id, "total": len(filtered_attachments)},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query_id,
                })

                return att.file_id, extracted_docs

        results = await asyncio.gather(*[parse_with_limit(att) for att in filtered_attachments])

        for file_id, extracted_docs in results:
            docs_by_file[file_id] = extracted_docs

        writer({
            "type": "status",
            "phase": ["parse_documents"],
            "status": "complete",
            "data": {"total": len(filtered_attachments)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query_id,
        })

        #strip attachment for contents
        stripped_query = state.query.model_copy(update={
                            "attachments": [
                                att.model_copy(update={"content": None})
                                for att in state.query.attachments or []
                            ]
                        })
        return {"docs_by_file": docs_by_file, "query": stripped_query}

    def _collapse_emails_node(self, state: PipelineState):
        eml_handler = EmailThreadParser()
        collapsed_emails: dict = {}
        writer = get_stream_writer()
        query = state.query

        writer({
            "type": "status",
            "phase": ["collapse_emails"],
            "status": "starting",
            "data": {"total": sum(1 for att in (query.attachments or []) if att.file_type == "message/rfc822")},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        if query.attachments:
            raw_emails = {att.file_id: python_email.message_from_bytes(base64.b64decode(att.content))
                          for att in query.attachments if att.file_type == "message/rfc822"}
            if raw_emails:
                collapsed_emails = eml_handler.collapse_threads(raw_emails)
                logger.info(f'ℹ️ Collapsed {len(raw_emails)} raw email(s) to {len(collapsed_emails)} for analysis | project_id={query.project_id}')

        writer({
            "type": "status",
            "phase": ["collapse_emails"],
            "status": "complete",
            "data": {
                "n_input": len(collapsed_emails),
                "n_collapsed": len(collapsed_emails),
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        return {"collapsed_emails": collapsed_emails}

    def _extract_emails_node(self, state: PipelineState):
        '''Extract email content and nested attachments as documents for analysis.'''
        writer = get_stream_writer()
        shortened_emails = state.collapsed_emails
        query = state.query
        user_id = get_config().get("configurable", {}).get("user_id")

        writer({
            "type": "status",
            "phase": ["extract_emails"],
            "status": "starting",
            "data": {"total": len(shortened_emails or {})},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        eml = EmailHandler()
        emails_to_handle = shortened_emails or {}
        output_emails = []
        logger.info(f'ℹ️ Processing {len(emails_to_handle)} email(s) for analysis | project_id={query.project_id}')
        for id_, messages in emails_to_handle.items():
            data = eml.extract_email_data(
                msg=messages[0],
                user_id=user_id,
                query_id=query.query_id,
                session_id=query.session_id,
                file_id=id_,
            )
            email = data.get("email")
            if not email:
                logger.warning(f"⚠️ No email extracted for id {id_}, skipping.")
                continue
            email.reference_paths = [f"{user_id}/{query.session_id}/{e_id}.eml" for e_id in messages[1]] if messages[1] else None
            output_emails.append(email)
            current_email_attachments = data.get("attachments", [])
            if current_email_attachments:
                logger.info(f"📎 Email '{email.subject}': {len(current_email_attachments)} nested attachment(s) → dispatching as doc batch")
                for att in current_email_attachments:
                    if att.file_type != "message/rfc822":
                        query.attachments.append(att)
                    else:
                        data = eml.extract_email_data(msg = python_email.message_from_bytes(att.content), 
                                                      user_id=user_id, 
                                                      query_id=query.query_id, 
                                                      session_id=query.session_id, 
                                                      file_id=att.file_id)
                        nested_email = data.get("email")
                        nested_attachments = data.get("attachments", [])
                        if nested_email:
                            logger.info(f'📧 Nested email found in attachment of email "{email.subject}": "{nested_email.subject}"')
                            output_emails.append(nested_email)
                        if nested_attachments:
                            logger.info(f"📎 Email '{email.subject}': {len(nested_attachments)} additional nested attachment(s) found in '{nested_email.subject}' → dispatching as doc batch")
                            query.attachments.extend(nested_attachments)

            else:
                logger.debug(f"📭 Email '{email.subject}': no nested attachments")

            writer({
                "type": "status",
                "phase": ["extract_emails"],
                "status": "processing",
                "data": {"current": email.subject, 
                        "remaining": len(emails_to_handle) - len(output_emails)},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })

        writer({
            "type": "status",
            "phase": ["extract_emails"],
            "status": "complete",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        return {"email_models": output_emails, "query": query}

    async def _storage_node(self, state: PipelineState):
        query = state.query
        writer = get_stream_writer()

        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "starting",
            "data": {
                "total": len(query.attachments or []),
                "storage_type": ["file_storage"],
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        result = await self.storage.save_raw_documents(attachments=query.attachments)

        if result is not None and not isinstance(result, bool):
            logger.warning(f"⚠️ Storage node returned non-boolean result: {result}")
            return
        writer({
            "type": "status",
            "phase": ["storage"],
            "status": "complete",
            "data": {
                "total": len(query.attachments or []),
                "storage_type": ["file_storage"],
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        logger.debug(f'File storage operation completed')

    async def _initialize_input_node(self, state: PipelineState):
        writer = get_stream_writer()
        query = state.query
        thread = get_config()
        self.context_manager.llm = pick_llm(thread.get("configurable", {}).get("llm_model"), self.config)

        writer({
            "type": "status",
            "phase": ["init_input"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        initial_input = await self.context_manager.analyze_init_input(query.question, config=thread)
        
        
        
        writer({
            "type": "status",
            "phase": ["init_input"],
            "status": "complete",
            "data": {"parties_found": len(initial_input.parties or [])},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })
        return {"input_": initial_input}

    async def _embedding_node(self, state: PipelineState):
        writer = get_stream_writer()
        query = state.query
        docs_by_file = state.docs_by_file

        if docs_by_file and self.config.project.embed_to_vectorstore:
            all_docs = [doc for file_docs in docs_by_file.values() for doc in file_docs]
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {
                    "file_count": len(docs_by_file),
                    "doc_count": len(all_docs),
                    "storage_type": ["vector_store"],
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
            vs_cfg = self.config.async_tasks.vectorstore
            for attempt in range(vs_cfg.retry_attempts + 1):
                try:
                    await asyncio.to_thread(self.vs.add_documents, all_docs, collection_id="attachments")
                    break
                except Exception as e:
                    if attempt < vs_cfg.retry_attempts:
                        wait_time = min(vs_cfg.retry_wait_min * (2 ** attempt), vs_cfg.retry_wait_max)
                        logger.warning(f"⚠️ Retry {attempt + 1}/{vs_cfg.retry_attempts} for add_documents after {wait_time}s: {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ add_documents failed after {attempt + 1} attempts: {e}")
                        raise
            writer({
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {
                    "file_count": len(docs_by_file),
                    "doc_count": len(all_docs),
                    "storage_type": ["vector_store"],
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })
            logger.debug(f'Vector store batch save completed: {len(all_docs)} docs across {len(docs_by_file)} files')

    async def _analyze_node(self, state: PipelineState):
        writer = get_stream_writer()
        query = state.query
        thread = get_config()
        self.context_manager.llm = pick_llm(thread.get("configurable", {}).get("llm_model"), self.config)

        doc_tasks = self._prepare_analysis_tasks(state)

        attachments = []
        events = []
        damages = []
        claims = []
        deadlines = []
        emails = []

        writer({
            "type": "status",
            "phase": ["analyze_docs", "analyze_emails"],
            "status": "starting",
            "data": {"total": len(doc_tasks)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        completed = 0
        for coro in asyncio.as_completed(doc_tasks):
            result = await coro
            completed += 1
            phase = "analyze_emails" if "emails" in result else "analyze_docs"

            specs = ""
            if isinstance(result, dict) and "attachments" in result:
                attachments.extend(result.get("attachments", []))
                filenames = [a.filename for a in result.get("attachments", []) if hasattr(a, "filename") and a.filename]
                specs = ", ".join(filenames) if filenames else ""
            elif isinstance(result, dict) and "emails" in result:
                emails.extend(result.get("emails", []))
                email_subjects = [e.subject for e in result.get("emails", []) if hasattr(e, "subject") and e.subject]
                specs = ", ".join(email_subjects) if email_subjects else ""

            events.extend(result.get("events", []))
            damages.extend(result.get("damages", []))
            claims.extend(result.get("claims", []))
            deadlines.extend(result.get("deadlines", []))

            count = len(result.get("emails", [])) if "emails" in result else len(result.get("attachments", []))
            writer({
                "type": "status",
                "phase": [phase],
                "status": "complete",
                "data": {
                    "count": count,
                    "specs": specs,
                    "progress": completed,
                    "total": len(doc_tasks),
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            })

        writer({
            "type": "status",
            "phase": ["analyze_docs", "analyze_emails"],
            "status": "complete",
            "data": {"total": len(doc_tasks)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        
        return {
            "attachments": attachments,
            "events": events,
            "damages": damages,
            "claims": claims,
            "deadlines": deadlines,
            "emails": emails,
        }

    def _qc_analysis_node(self, state):
        input_emails = {e.message_id: getattr(e, "subject", "unknown subject") for e in state.email_models or [] if hasattr(e, "message_id")}
        input_attachments = {a.file_id: getattr(a, "filename", "unknown file") for a in state.query.attachments or [] if hasattr(a, "file_id") and getattr(a, "file_type", "") != "message/rfc822"}

        output_emails = {e.message_id for e in state.emails or [] if hasattr(e, "message_id")}
        output_attachments = {a.file_id for a in state.attachments or [] if hasattr(a, "file_id")}

        if len(input_emails) != len(output_emails):
            difference = set(input_emails.keys()) - output_emails
            logger.warning(f"QC Warning: Number of output emails ({len(output_emails)}) does not match number of input emails ({len(input_emails)}).")
            logger.debug(f'The following emails are in input but missing from output:')
            for msg_id in difference:
                logger.debug(f'- [{msg_id}] {input_emails[msg_id]}')

        if len(input_attachments) != len(output_attachments):
            difference = set(input_attachments.keys()) - output_attachments
            logger.warning(f"QC Warning: Number of output attachments ({len(output_attachments)}) does not match number of input attachments ({len(input_attachments)}).")
            logger.debug(f'The following attachments are in input but missing from output:')
            for file_id in difference:
                logger.debug(f'- [{file_id}] {input_attachments[file_id]}')

    async def _save_init_node(self, state: PipelineState):
        query = state.query
        user_id = get_config().get("configurable", {}).get("user_id")
        attachments = state.attachments
        events = state.events
        damages = state.damages
        claims = state.claims
        deadlines = state.deadlines
        emails = state.emails
        initial_input = state.input_

        writer = get_stream_writer()

        writer({
            "type": "status",
            "phase": ["save_project"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        result = FactSheet(
            events=events,
            damages=damages if damages else None,
            claims=claims if claims else None,
            deadlines=deadlines if deadlines else None,
            **initial_input.model_dump(),
        )
        logger.debug(f"About to save project {query.project_id} to Supabase...")
        await asyncio.to_thread(
            self.conversation_manager.save_project,
            factsheet=result,
            attachments=attachments,
            emails=emails,
            user_id=user_id,
            session_id=query.session_id,
            query_id=query.query_id,
            project_id=query.project_id,
            llm_model=query.llm_model,
        )

        writer({
            "type": "status",
            "phase": ["save_project"],
            "status": "complete",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        logger.debug(f"Project saved successfully. About to yield final result...")
        try:
            factsheet_dict = result.model_dump(mode="json")
            attachments_dict = [file.model_dump(mode="json") for file in attachments]
            emails_dict = [email.model_dump(mode="json") for email in emails]
            logger.debug(f"Successfully serialized factsheet and attachments. Yielding result...")
            writer({
                "type": "result",
                "data": {
                    "factsheet": factsheet_dict,
                    "attachments": attachments_dict,
                    "emails": emails_dict,
                },
            })
            logger.debug(f"Final result yielded successfully.")
        except Exception as e:
            logger.exception(f"❌ Failed to serialize/yield final result")
            raise

    async def _save_update_node(self, state: PipelineState):
        writer = get_stream_writer()
        query = state.query
        attachments = state.attachments
        events = state.events
        damages = state.damages
        claims = state.claims
        deadlines = state.deadlines
        emails = state.emails
        init_input = state.input_

        writer({
            "type": "status",
            "phase": ["update_project"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        # ============= PHASE 2 =================
        # Insert FK-parent tables in parallel (must complete before data tables)
        # ========================================
        async def insert_fk_table(table_name, elements):
            if not elements or not hasattr(elements[0], "model_dump"):
                logger.info(f"No new elements to save for {table_name}, skipping.")
                return
            async with self._semaphore_db:
                writer({
                    "type": "status",
                    "phase": ["storage"],
                    "status": "starting",
                    "data": {"total": len(elements), "storage_type": ["database"], "table_name": table_name},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id,
                })
                await asyncio.to_thread(
                    self.conversation_manager.insert_project_element,
                    data= elements, # [element.model_dump(mode="json", exclude={"claims", "damages", "deadlines", "events"}) for element in elements],
                    project_id=query.project_id,
                    table_name=table_name,
                    llm_model=query.llm_model,
                )
                writer({
                    "type": "status",
                    "phase": ["storage"],
                    "status": "complete",
                    "data": {"total": len(elements), "storage_type": ["database"], "table_name": table_name},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id,
                })

        fk_results = await asyncio.gather(
            insert_fk_table("project_attachments", attachments),
            insert_fk_table("project_emails", emails),
            return_exceptions=True,
        )
        fk_errors = [r for r in fk_results if isinstance(r, Exception)]
        if fk_errors:
            logger.error(f"FK parent inserts failed for project {query.project_id}: {fk_errors}. Skipping dependent tables to avoid FK violations.")
            return

        # ============= PHASE 3 =================
        # Insert data tables + metadata in parallel (FK parents already committed)
        # ========================================
        party_reps = []
        parties = []
        for party in (init_input.parties or []):
            if party.party_reps:
                for rep in party.party_reps:
                    party_reps.append(
                        rep if rep.party_id else rep.model_copy(update={"party_id": party.party_id})
                    )
            parties.append(party.model_dump(mode='json', exclude={"party_reps"}))


        to_insert = {
            "project_events": events,
            "project_damages": damages,
            "project_claims": claims,
            "project_deadlines": deadlines,
        }
        to_replace = {
            "project_parties": parties or [],
            "project_party_reps" : party_reps,
        }

        async def insert_data_table(table_name, items, replace=False):
            if not items or (not replace and not hasattr(items[0], "model_dump")):
                logger.warning(f"No valid items to save for {table_name}. Skipping storage for this table.")
                return
            async with self._semaphore_db:
                writer({
                    "type": "status",
                    "phase": ["storage"],
                    "status": "starting",
                    "data": {"total": len(items), "storage_type": ["database"], "table_name": table_name},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id,
                })
                if replace:
                    await asyncio.to_thread(
                        self.conversation_manager.upsert_replace_project_element,
                        data=items,
                        project_id=query.project_id,
                        table_name=table_name,
                        llm_model=query.llm_model,
                    )
                else:
                    await asyncio.to_thread(
                        self.conversation_manager.insert_project_element,
                        data= items, # [item.model_dump(mode="json") for item in items],
                        project_id=query.project_id,
                        table_name=table_name,
                        llm_model=query.llm_model,
                    )
                writer({
                    "type": "status",
                    "phase": ["storage"],
                    "status": "complete",
                    "data": {"total": len(items), "storage_type": ["database"], "table_name": table_name},
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id,
                })

        await asyncio.gather(
            *[insert_data_table(t, items) for t, items in to_insert.items()],
            *[insert_data_table(t, items, replace=True) for t, items in to_replace.items()],
            asyncio.to_thread(
                self.conversation_manager.upsert_project,
                data={"background": init_input.background, "title": init_input.title},
                element_type="metadata",
                project_id=query.project_id,
                llm_model=query.llm_model,
            ),
        )

        writer({
            "type": "status",
            "phase": ["update_project"],
            "status": "complete",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

    async def _load_project_data(self, state: PipelineState):
        writer = get_stream_writer()
        query = state.query

        writer({
            "type": "status",
            "phase": ["load_project_data"],
            "status": "starting",
            "data": {"project_id": query.project_id},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id,
        )

        if project_data and not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData. Value: {project_data}"
            logger.error(f"❌ update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)

        writer({
            "type": "status",
            "phase": ["load_project_data"],
            "status": "complete",
            "data": {"project_id": query.project_id},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        })

        return {"input_": project_data}

    async def _update_metadata_node(self, state: PipelineState):
        logger.info(f"🏷️ Running metadata update node | project_id={state.query.project_id}")
        writer = get_stream_writer()
        
        project_data = state.input_
        existing_init_input = InitialInput()

        if isinstance(project_data, ProjectData) and project_data.factsheet:
            logger.debug(f"Loaded project data with factsheet containing {len(project_data.factsheet.events or [])} events")
            existing_init_input = InitialInput(
                parties=project_data.factsheet.parties,
                title=project_data.factsheet.title,
                background=project_data.factsheet.background,
            )
        elif isinstance(project_data, InitialInput):
            existing_init_input = project_data

        writer({
            "type": "status",
            "phase": ["update_metadata"],
            "status": "starting",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": state.query.query_id,
        })
        parties = []
        if state.emails:
            for row in state.emails:
                parties.extend(row.parties or [])
        if state.attachments:
            for row in state.attachments:
                parties.extend(row.parties or [])

        if parties:
            context = "**Additional info extracted from emails and documents:**\n"
            for p in parties:
                rep_str = "; ".join(
                    f"{r.first_name} {r.last_name} ({r.email or 'no email'}, {r.rep_role or 'unknown role'})"
                    for r in (p.party_reps or [])
                ) or "no reps identified"
                context += f"- {p.legal_name or 'unknown'} | role: {p.role or 'unknown'} | reps: {rep_str}\n"
        else:
            context = "No email or document context available."

        initial_input = await self.context_manager.update_initial_input(
                                                                        context=context,
                                                                        existing_initial_input=existing_init_input,
                                                                        )
        logger.debug(f'\n\nUpdated metadata {initial_input.model_dump(mode="json")}\n\n')
        writer({
            "type": "status",
            "phase": ["update_metadata"],
            "status": "complete",
            "data": {},
            "timestamp": datetime.now().isoformat(),
            "query_id": state.query.query_id,
        })
        logger.info(f'🏷️ Metadata update complete.')
        return {"input_": initial_input}

