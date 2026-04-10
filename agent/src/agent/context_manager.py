
import json
from agent.tools import _parse_date
import tiktoken
import logging
from uuid import uuid4
import uuid
import asyncio
from pydantic import BaseModel, create_model, Field, field_validator
from langchain_core.messages import AIMessage,ToolMessage, HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from datetime import date, datetime

from langchain.chat_models import init_chat_model

from models import *
from utils import AppConfig
from .utils import _parse_date, apply_retry

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self, 
                 config : AppConfig,
                 llm: BaseChatModel = None,
                 ):
        self._llm = init_chat_model("gemini-2.5-flash", model_provider="google_genai") if llm is None else llm
        self.config = config

    @property
    def llm(self):
        return self._llm

    @llm.setter
    def llm(self, value: BaseChatModel):
        self._llm = value

    def _structured(self, schema):
        """Return a structured output chain with retry applied after chaining."""
        chain = self._llm.with_structured_output(schema, method="function_calling")
        return apply_retry(chain, self.config)

    # ===== HELPERS =====
    def truncate_tokens(self, messages, max_tokens=7000):
        """Truncate messages to fit within max_tokens while preserving tool-call structure."""
        if not isinstance(messages, list):
            logger.error(f'Messages should be a list, got {type(messages)}')
            return messages
        # if not isinstance(messages[0], BaseMessage):
        #     logger.error(f'Messages should be a list of BaseMessage, got {type(messages[0])}')
        #     return messages
        
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        token_count = 0
        truncated = []

        for msg in reversed(messages):
            if hasattr(msg, 'content'):
                if token_count > max_tokens:
                    break
                token_count += len(enc.encode(msg.content or ""))
                truncated.insert(0, msg)

            else:
                raise ValueError(f'Message wrong type: {type(msg)}. Expected message with "content" attribute.')

        # Safety check: drop any orphan tool messages at the start
        while truncated and isinstance(truncated[0], ToolMessage):
            truncated.pop(0)

        # Safety check: drop trailing AIMessage with tool_calls if no following ToolMessages
        # This prevents OpenAI API error about missing tool responses
        if truncated and isinstance(truncated[-1], AIMessage) and hasattr(truncated[-1], 'tool_calls') and truncated[-1].tool_calls:
            logger.warning("Dropping trailing AIMessage with tool_calls after truncation to avoid API error")
            truncated.pop()

        return truncated

    def truncate_messages(self, messages, max_messages=20):
        """Truncate messages while preserving tool-call structure."""
        if len(messages) <= max_messages:
            return messages

        truncated = messages[-max_messages:]

        # Remove orphan tool messages at start
        while truncated and not isinstance(truncated[0], HumanMessage):
            truncated.pop(0)

        # If no HumanMessage found in window, fall back to last HumanMessage + everything after
        if not truncated:
            last_human_idx = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
            if last_human_idx is not None:
                truncated = list(messages[last_human_idx:])
            else:
                truncated = list(messages[-1:])

        # Remove trailing AIMessage with tool_calls if no ToolMessage follows
        if (truncated and
            isinstance(truncated[-1], AIMessage) and
            hasattr(truncated[-1], 'tool_calls') and
            truncated[-1].tool_calls):
            logger.warning("Dropping trailing AIMessage with tool_calls to avoid API error")
            truncated.pop()

        return truncated

    def is_valid_uuid(self, val):
        try:
            uuid.UUID(str(val))
            return True
        except ValueError:
            return False


    # ===== FUNCTIONS FOR INITIAL FACTSHEET CREATION =====
    async def analyze_init_input(self, init_input : str, config: RunnableConfig = None) -> InitialInput:
        structured_llm = self._structured(InitialInput)
        prompt = f'Analyze the following project description and extract key information into the InitialInput structure. If not sufficient information, leave blank:\n\n{init_input}.'
        init_input = await structured_llm.ainvoke(prompt, config=config)
        for party in init_input.parties or []:
            party.party_id = str(uuid4())
            for party_rep in party.party_reps or []:
                party_rep.party_rep_id = str(uuid4())
                party_rep.party_id = party.party_id
        logger.debug('\n\n' + "="*5 + f' Analyzed Initial Input: {str(init_input.model_dump(mode = "json"))[:500]} ' + '='*5 + '\n\n')
        return init_input
    
    async def analyze_docs(self,
                input_ : InitialInput | ProjectData,
                attachments : list[AttachmentModel],
                config: RunnableConfig = None,
                ) -> dict:
        '''Function to analyze multiple documents and extract structured data as Attachments.'''
                
        result_attachments = []
        deadlines = []
        damages = []
        claims = []
        events  = []
        
        if not attachments:
            logger.warning('No content provided for document analysis. Returning empty result.')
            return {"attachments": [], 
                    "events": [],
                    "damages": [],
                    "claims": [],
                    "deadlines": []
                    }

        class AttachmentWithEvents(BaseModel):
            attachment: AttachmentExtracted
            events: list[Event] | None = []

        class MultipleAttachmentsResult(BaseModel):
            attachments: list[AttachmentWithEvents]

        documents_formatted = "\n\n".join([
            f"DOCUMENT #{idx+1}\nFILE_ID={att.file_id}  <-- copy this into attachment.file_id\n{att.model_dump(include={'body','file_type'})}"
            for idx, att in enumerate(attachments)
        ])

        structured_llm = self._structured(MultipleAttachmentsResult)
        if isinstance(input_, ProjectData):
            init_prompt = f'{input_.factsheet.shorten_factsheet()}\n\n'
        elif isinstance(input_, str):
            init_prompt = f'Case input: {input_}\n\n'
        else:
            init_prompt = f'Case input: {input_.model_dump(mode="json")}\n\n'
        prompt = init_prompt + f'''Analyze the following {len(attachments)} documents.

                                For EACH document, return an AttachmentWithEvents object containing:
                                1. attachment: AttachmentExtracted - metadata from that document (MUST set file_id to the file_id shown for each document)
                                2. events: list[Event] or null - timeline events mentioned in that document

                                IMPORTANT: Return exactly {len(attachments)} AttachmentWithEvents objects in the attachments array.
                                CRITICAL: Set file_id in AttachmentExtracted to match the file_id from the input document.

                                Do not include any irrelevant information.
                                Documents to analyze:
                                {documents_formatted}'''
        retry_prompt = prompt
        response = None
        for attempt in range(3):
            try:
                response = await structured_llm.ainvoke(retry_prompt, config=config)
                if not response or not response.attachments:
                    logger.warning(f"Attempt {attempt + 1} returned empty response, retrying...")
                    retry_prompt = prompt + f"\n\nPREVIOUS ATTEMPT RETURNED EMPTY: You must return exactly {len(attachments)} AttachmentWithEvents objects. Do not return an empty list."
                    continue
                break
            except Exception as e:
                if getattr(e, 'status_code', None) == 400:
                    logger.error(f"Input exceeds model context length — skipping retries: {e}")
                    break
                logger.warning(f"Attempt {attempt + 1} failed validation: {e}")
                retry_prompt = prompt + f"\n\nPREVIOUS ATTEMPT FAILED WITH VALIDATION ERROR:\n{e}\nPlease fix the above errors and try again."

        if not response or not response.attachments:
            logger.error("LLM returned empty or invalid response after all attempts")
            return {
                "attachments": [],
                "events": [],
                "damages": [],
                "deadlines": [],
                "claims": []
            }
        if len(response.attachments) != len(attachments):
            logger.warning(f'LLM returned {len(response.attachments)} attachments but {len(attachments)} were provided. This may indicate a parsing issue.')
        for idx, att_result in enumerate(response.attachments):
            if idx >= len(attachments):
                logger.error(f'LLM returned more attachments than provided. Stopping at index {idx}.')
                break
            
            extracted = att_result.attachment
            logger.debug(f"─── Attachment element ───\n{extracted.model_dump(mode='json')}")
            
            # Validate that extracted file_id matches one of our original IDs
            if extracted.file_id not in [att.file_id for att in attachments]:
                logger.warning(f'⚠️  File ID mismatch for attachment #{idx}: got "{extracted.file_id}" — using index fallback')
                input_att = attachments[idx]
            else:
                # Find the correct input attachment by matching file_id
                input_att = next((att for att in attachments if att.file_id == extracted.file_id), None)
                if not input_att:
                    logger.error(f'❌ Cannot find attachment with file_id={extracted.file_id} — using index fallback')
                    input_att = attachments[idx]
                else:
                    logger.debug(f'Attachment #{idx+1}: matched file_id={extracted.file_id}')
            
            # Critical safety check
            if not input_att:
                logger.error(f'❌ input_att is None at index {idx} — skipping')
                continue
            
            logger.debug(f'📄 Attachment #{idx+1}: input={input_att.file_id} extracted={extracted.file_id}')
            
            # Assign file_id and unique IDs to all extracted elements from this attachment
            if extracted.damages:
                for damage in extracted.damages:
                    damage.file_id = input_att.file_id  # Link damage to this attachment's file_id
                    damage.email_id = None  # This is from attachment, not email
                    damage.damage_id = str(uuid4())       # Generate unique damage_id
                    logger.debug(f'  - Damage: {damage.damage_id} linked to file_id={input_att.file_id}')
                damages.extend(extracted.damages)

            if extracted.deadlines:
                for deadline in extracted.deadlines:
                    deadline.file_id = input_att.file_id  # Link deadline to this attachment's file_id
                    deadline.email_id = None  # This is from attachment, not email
                    deadline.deadline_id = str(uuid4())     # Generate unique deadline_id
                deadlines.extend(extracted.deadlines)
            if extracted.claims:
                for claim in extracted.claims:
                    claim.file_id = input_att.file_id  # Link claim to this attachment's file_id
                    claim.email_id = None  # This is from attachment, not email
                    claim.claim_id = str(uuid4())        # Generate unique claim_id
                    logger.debug(f'  - Claim: {claim.claim_id} linked to file_id={input_att.file_id}')
                claims.extend(extracted.claims)
            if att_result.events:
                for event in att_result.events:
                    event.file_id = input_att.file_id  # Link event to this attachment's file_id
                    event.email_id = None  # This is from attachment, not email
                    event.event_id = str(uuid4())        # Generate unique event_id
                    logger.debug(f'  - Event: {event.event_id} linked to file_id={input_att.file_id}')
                events.extend(att_result.events)
            
            attachment_data = extracted.model_dump()
            attachment_data.update({
                "filename": input_att.filename,
                "path": input_att.path,
                "body": input_att.body,
                "file_type": input_att.file_type,
                "size": input_att.size,
                "file_id": input_att.file_id,
            })
            result_attachments.append(Attachment(**attachment_data))
            logger.debug(f'✅ Attachment #{idx+1} done — file_id={input_att.file_id}')
        
        return {"attachments" : result_attachments,
                "events" : events,
                "damages"   : damages,
               "claims"    : claims,
               "deadlines" : deadlines,
                }
        
    async def analyze_emails(self,
                input_ : InitialInput | ProjectData,
                emails : list[EmailModel],
                config: RunnableConfig = None,
                ) -> dict:
        '''Function to analyze multiple documents and extract structured data as Attachments.'''
        
        class EmailAnalysisResult(BaseModel):
            """Result for ONE email analysis"""
            email: EmailExtracted = Field(description="Extracted metadata and content from this specific email")
            events: list[Event] | None = Field(default=None, description="Timeline events mentioned in this email (can be empty list or null if no events found)")

            @field_validator("events", mode="before")
            @classmethod
            def filter_events_without_date(cls, v):
                if not isinstance(v, list):
                    return v
                def _has_valid_date(e):
                    if not isinstance(e, dict):
                        return True
                    val = e.get("event_start_date")
                    if val is None:
                        return False
                    if isinstance(val, (date, datetime)):
                        return True
                    if isinstance(val, str):
                        return val.split("-")[0].isdigit()
                    return False
                return [e for e in v if _has_valid_date(e)]
        
        class EmailsAnalysisResult(BaseModel):
            """Result containing ALL email analyses"""
            emails: list[EmailAnalysisResult] = Field(description="List of email analysis results - one EmailAnalysisResult object per input email")

        # Build set of original IDs for validation
        org_ids = set()
        email_id_map = {}  # Map email_id -> EmailModel
        for email in emails:
            org_ids.add(email.file_id)
            email_id_map[email.file_id] = email

        result_emails = []
        deadlines = []
        damages = []
        claims = []
        events = []

        structured_llm = self._structured(EmailsAnalysisResult)
        if isinstance(input_, ProjectData):
            init_prompt = f'{input_.factsheet.shorten_factsheet()}\n\n'
        elif isinstance(input_, str):
            init_prompt = f'Case input: {input_}\n\n'
        else:
            init_prompt = f'Case input: {input_.model_dump(mode="json")}\n\n'
        
        # Format emails with clear ID separation
        emails_formatted = "\n\n".join([
            f"EMAIL #{idx+1} (email_id: {eml.file_id}):\n{eml.model_dump(include={'from_addr',"to","cc","bcc",'subject','body_text', "date",})}"
            for idx, eml in enumerate(emails)
        ])
        
        # Clearer prompt showing the expected structure
        prompt = init_prompt + f'''Analyze the following {len(emails)} emails.

                                For EACH email, return an EmailAnalysisResult object containing:
                                1. email: EmailExtracted - metadata from that email (MUST set email_id to the file_id shown for each email)
                                2. events: list[Event] or null - timeline events mentioned in that email

                                IMPORTANT: Return exactly {len(emails)} EmailAnalysisResult objects in the emails array.
                                CRITICAL: Set email_id in EmailExtracted to match the file_id from the input email.
                                For email.parties:
                                - List only ORGANIZATIONS or independently-acting entities as parties, NOT named individuals.
                                - Named individuals (senders/recipients) belong under party_reps of their organization — infer affiliation from email domain (e.g. borghildur@redearkitekter.no → rep for Rede arkitekter as).
                                - If a person has no clear org affiliation, list them as a party with no reps.

                                Emails to analyze:
                                {emails_formatted}'''
        
        response = await structured_llm.ainvoke(prompt, config=config)

        # Validate response structure
        if not response or not response.emails:
            logger.error("LLM returned empty or invalid response")
            return {
                "emails": [],
                "events": [],
                "damages": [],
                "deadlines": [],
                "claims": []
            }

        if len(response.emails) != len(emails):
            logger.warning(f'LLM returned {len(response.emails)} emails but {len(emails)} were provided. This may indicate a parsing issue.')
        
        for idx, email_result in enumerate(response.emails):
            
            if idx >= len(emails):
                logger.error(f'LLM returned more emails than provided. Stopping at index {idx}.')
                break
            
            extracted = email_result.email
            
            # Validate that extracted email_id matches one of our original IDs
            if extracted.email_id not in org_ids:
                logger.warning(f'⚠️  Email ID mismatch for email #{idx}: got "{extracted.email_id}" — using index fallback')
                input_email = emails[idx]
            else:
                # Find the correct input email by matching email_id
                input_email = email_id_map.get(extracted.email_id)
                if not input_email:
                    logger.error(f'❌ Cannot find email with email_id={extracted.email_id} — using index fallback')
                    input_email = emails[idx]
                else:
                    logger.debug(f'Email #{idx+1}: matched email_id={extracted.email_id}')
            
            # Critical safety check
            if not input_email:
                logger.error(f'❌ input_email is None at index {idx} — skipping')
                continue
            
            # Log the matching
            #logger.info(f'Processing email #{idx+1}: input_file_id={input_email.file_id}, extracted_email_id={extracted.email_id}')
            
            # Assign email_id (not file_id!) and unique IDs to all extracted elements from this email
            if extracted.damages:
                for damage in extracted.damages:
                    damage.email_id = input_email.file_id  # Link damage to this email's email_id
                    damage.file_id = None  # Clear file_id since this is from email
                    damage.damage_id = str(uuid4())       # Generate unique damage_id
                    logger.debug(f'  - Damage: {damage.damage_id} linked to email_id={input_email.file_id}')
                damages.extend(extracted.damages)

            if extracted.deadlines:
                for deadline in extracted.deadlines:
                    deadline.email_id = input_email.file_id  # Link deadline to this email's email_id
                    deadline.file_id = None  # Clear file_id since this is from email
                    deadline.deadline_id = str(uuid4())     # Generate unique deadline_id
                    logger.debug(f'  - Deadline: {deadline.deadline_id} linked to email_id={input_email.file_id}')
                deadlines.extend(extracted.deadlines)

            if extracted.claims:
                for claim in extracted.claims:
                    claim.email_id = input_email.file_id  # Link claim to this email's email_id
                    claim.file_id = None  # Clear file_id since this is from email
                    claim.claim_id = str(uuid4())        # Generate unique claim_id
                    logger.debug(f'  - Claim: {claim.claim_id} linked to email_id={input_email.file_id}')
                claims.extend(extracted.claims)
            
            if email_result.events:
                for event in email_result.events:
                    event.email_id = input_email.file_id  # Link event to this email's email_id
                    event.file_id = None  # Clear file_id since this is from email
                    event.event_id = str(uuid4())        # Generate unique event_id
                    logger.debug(f'  - Event: {event.event_id} linked to email_id={input_email.file_id}')
                events.extend(email_result.events)
            
            # Build final Email object by combining extracted data with original email metadata
            email_data = extracted.model_dump()
            email_data.update({
                # Override with original email metadata
                "to": input_email.to,
                "to_names": input_email.to_names,
                "from": input_email.from_addr,
                "from_name": input_email.from_name,
                "cc": input_email.cc,
                "cc_names": input_email.cc_names,
                "bcc": input_email.bcc,
                "bcc_names": input_email.bcc_names,
                "subject": input_email.subject,
                "date": input_email.date,
                "message-id": input_email.message_id or "",
                "in-reply-to": input_email.in_reply_to,
                "references": input_email.references,
                "thread_id": input_email.thread_id,
                "thread-index": input_email.thread_index,
                "thread-topic": input_email.thread_topic,
                "body": input_email.body_text,
                "html": input_email.body_html,
                "headers": input_email.headers or {},
                # Set email_id to the original file_id for consistency
                "email_id": input_email.file_id,
                "path": input_email.path,
                "reference_paths" : input_email.reference_paths,
            })
            result_emails.append(Email(**email_data))
            logger.debug(f'✅ Email #{idx+1} done — email_id={input_email.file_id}')
        
        return {"emails" : result_emails,
                "events" : events,
                "damages" : damages,
                "deadlines" : deadlines,
                "claims" : claims}

    # =========== FUNCTIONS TO CLEAN AND REVISE EXISTING ELEMENTS

    _ITEM_MODEL_MAP = {
        "events": (list[Event], Field(default_factory=list)),
        "parties": (list[Party], Field(default_factory=list)),
        "claims": (list[Claim], Field(default_factory=list)),
        "damages": (list[Damage], Field(default_factory=list)),
        "deadlines": (list[Deadline], Field(default_factory=list)),
    }
    _ID_MAP = {
        "events": "event_id", "parties": "party_id", "claims": "claim_id",
        "damages": "damage_id", "deadlines": "deadline_id",
    }
    _IDENTITY_FIELDS_MAP = {
        "events": ["event_date", "category", "event_name"],
        "damages": ["category", "file_id", "party_role"],
        "claims": ["relief_sought", "file_id", "party_role"],
        "deadlines": ["file_id", "deadline_date", "party_role"],
        "parties": ["legal_name", "role"],
    }
    _NULLABLE_UUID_FIELDS = {"file_id", "email_id"}

    async def _clean_chunk(self, et: str, items: list[dict]) -> list[dict]:
        """Clean a single chunk of items for one element type. Falls back to originals if LLM returns empty."""
        ChunkModel = create_model(f"{et.capitalize()}Chunk", **{et: self._ITEM_MODEL_MAP[et]})
        id_field = self._ID_MAP[et]

        keys = list(items[0].keys()) if items else []
        prompt = f'Clean and de-duplicate the following {et}. Merge entries that refer to the same real-world entity.\n'
        prompt += f'FORMAT: {" | ".join(keys)}\n'
        for item in items:
            prompt += f'\t* {" | ".join(str(item.get(k, "")) for k in keys)}\n'

        structured_llm = self._structured(ChunkModel)
        response = await structured_llm.ainvoke(prompt)

        raw_items = getattr(response, et, []) or []
        if not raw_items:
            logger.warning(f'⚠️ LLM returned empty for {et} chunk ({len(items)} items) — keeping originals')
            return items

        cleaned = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in raw_items]
        for item in cleaned:
            if not item.get(id_field) or not self.is_valid_uuid(item[id_field]):
                item[id_field] = str(uuid.uuid4())
            for field in self._NULLABLE_UUID_FIELDS:
                if isinstance(item.get(field), str) and item[field].lower() in ("null", "none", ""):
                    item[field] = None
        return cleaned

    async def clean_elements(self,
                             element_types: list[str],
                             project_data: ProjectData,
                             ) -> dict[str, list[dict]]:
        """Clean multiple element types using chunked concurrent LLM calls. Returns {element_type: cleaned_items}."""
        data_map = {et: project_data.factsheet.model_dump().get(et, []) for et in element_types}

        # Build all chunk tasks across all element types
        sem = asyncio.Semaphore(self.config.async_tasks.llm.max_concurrent_requests)
        chunk_size = self.config.project.clean.chunk_size

        async def _guarded(et: str, items: list[dict]) -> list[dict]:
            async with sem:
                return await self._clean_chunk(et, items)

        tasks = []
        task_et = []
        for et in element_types:
            items = data_map[et]
            if not items:
                continue
            for i in range(0, len(items), chunk_size):
                tasks.append(_guarded(et, items[i:i + chunk_size]))
                task_et.append(et)

        chunk_results = await asyncio.gather(*tasks)

        # Merge chunk results per element type
        merged: dict[str, list[dict]] = {et: [] for et in element_types}
        for et, result in zip(task_et, chunk_results):
            merged[et].extend(result)

        # Final code-based dedup pass (catches cross-chunk duplicates)
        results = {}
        for et in element_types:
            identity_fields = self._IDENTITY_FIELDS_MAP.get(et, [])
            seen: dict = {}
            deduped = []
            for item in merged[et]:
                sig = tuple(item.get(f) for f in identity_fields)
                if sig not in seen:
                    seen[sig] = True
                    deduped.append(item)

            logger.info(f'✅ Cleaned {et}: {len(data_map[et])} → {len(merged[et])} (LLM) → {len(deduped)} (deduplicated)')
            results[et] = deduped

        return results

    async def deduplicate_elements(self,
                  elements: dict[str, list[dict]]) -> dict[str, list[dict]]:
        """Deduplicate elements using LLM. Sends minimal key fields per type, returns filtered original items."""

        class KeepIds(BaseModel):
            ids: list[str] = Field(description="List of IDs to keep (one per unique real-world entity)")

        date_col_map = {
            "events": "event_start_date",
            "deadlines": "deadline_date",
            "claims": "source_date",
            "damages": "source_date",
        }
        format_map = {
            "events": ["event_id", "event_start_date", "event_name", "description"],
            "parties": ["party_id", "legal_name", "entity_type", "role", "role_description"],
            "claims": ["claim_id", "party_role", "relief_sought", "factual_basis", "legal_basis", "strength_assessment"],
            "damages": ["damage_id", "party_role", "category", "amount", "currency", "basis"],
            "deadlines": ["deadline_id", "deadline_date", "description"],
        }

        element_types = list(elements.keys())
        logger.info("Original element counts: " + ", ".join(f"{et}={len(elements.get(et, []))}" for et in element_types))

        structured_llm = self._structured(KeepIds)

        task_meta: list[tuple[str, set]] = []  # parallel to tasks: (et, chunk_ids)
        tasks = []
        for et in element_types:
            all_items = elements.get(et, [])
            for i in range(0, len(all_items), self.config.project.clean.chunk_size):
                chunk = all_items[i:i + self.config.project.clean.chunk_size]
                chunk_num = i // self.config.project.clean.chunk_size + 1
                logger.info(f'Creating deduplication task for {et} chunk {chunk_num} ({len(chunk)} items)')

                date_col = date_col_map.get(et)
                if date_col:
                    chunk = sorted(chunk, key=lambda x: _parse_date(x.get(date_col), default=date.min) or "")

                fields = format_map[et]
                prompt = (
                    f'These are the existing {et} extracted for this legal project. '
                    f'De-duplicate this list by identifying entries that refer to the same real-world entity. '
                    f'Also remove any redundant or low-quality entries. '
                    f'Return the IDs of the entries to KEEP (one per unique entity). Keep the ones that are most complete or accurate.\n\n'
                    f'FORMAT: {" | ".join(fields)}\n'
                )
                for item in chunk:
                    prompt += "\t- " + " | ".join(str(item.get(f, "")) for f in fields) + "\n"

                tasks.append(structured_llm.ainvoke(prompt))
                task_meta.append((et, set(item.get(self._ID_MAP[et]) for item in chunk)))

        llm_results = await asyncio.gather(*tasks)

        # Collect keep_ids per element type across all chunks
        keep_ids_per_et: dict[str, set] = {et: set() for et in element_types}
        for i, res in enumerate(llm_results):
            et, chunk_ids = task_meta[i]
            keep_ids = set(res.ids) if res and res.ids else set()

            invalid = keep_ids - chunk_ids
            if invalid:
                logger.warning(f'⚠️ {et}: LLM returned unknown IDs {invalid} — keeping all from this chunk')
                keep_ids_per_et[et] |= chunk_ids
                continue

            if not keep_ids:
                logger.warning(f'⚠️ {et}: LLM returned no IDs — keeping all from this chunk')
                keep_ids_per_et[et] |= chunk_ids
                continue

            keep_ids_per_et[et] |= keep_ids

        output: dict[str, list[dict]] = {}
        for et in element_types:
            id_field = self._ID_MAP[et]
            kept = [item for item in elements[et] if item.get(id_field) in keep_ids_per_et[et]]
            logger.info(f'✅ Deduplicated {et}: {len(elements[et])} → {len(kept)}')
            output[et] = kept

        logger.info("Final deduplicated counts: " + ", ".join(f"{et}={len(output.get(et, []))}" for et in element_types))

        return output

    async def clean_metadata(self, 
                             project_data : ProjectData,
                             ) -> str:
        """Clean metadata fields (title, background) using structured output to avoid LLM wrapper text."""
        
        class ProjectMetadata(BaseModel):
            title: str = Field(description="The cleaned and revised title, without any preamble or explanation")
            background: str = Field(description="The cleaned and revised background, without any preamble or explanation")
        
        prompt = (
            f'{project_data.factsheet.shorten_events()}\n'
            f'Task: Clean and/or rewrite the metadata (title & background) according to the context. '
            f'Return ONLY the cleaned metadata content itself, no explanation or preamble.\n\n'
            f'Original metadata content:\nCurrent Title: {project_data.factsheet.title}\nCurrent Background: {project_data.factsheet.background}'
        )        
        structured_llm = self._structured(ProjectMetadata)
        response = await structured_llm.ainvoke(prompt)
        
        return {
            "title": response.title if hasattr(response, 'title') else str(response),
            "background": response.background if hasattr(response, 'background') else str(response)
        }
    
    async def update_initial_input(self, context : str,
                                   existing_initial_input : InitialInput,
                                   
                                   ) -> InitialInput:
        """Update the initial input string based on the cleaned title and background."""
        #view_events = "Current Events"
        #view_events += "\t* Format: event_start_date | event_name | file_id | description" + "(Disputed)"  + "\n"
        # if isinstance(events, list):
        #     events.sort(key=lambda e: str(e.event_start_date))
        # else:
        #     raise ValueError(f'Events should be of type list, but actual type is {type(events)}')
        # for e in events:
        #     view_events += f"\t* {e.event_start_date} | {e.event_name} | {e.file_id or 'No file ID'} | {e.description or ''}"
        #     if e.disputed:
        #         view_events += " | Disputed"
        #     view_events += "\n"

        view_existing_init_input = "Existing Initial Input:\n"
        view_existing_init_input += f"Title: {existing_initial_input.title}\n"
        view_existing_init_input += f"Background: {existing_initial_input.background}\n"
        view_existing_init_input += f'Existing Parties ({len(existing_initial_input.parties or [])}):\n'
        for party in existing_initial_input.parties or []:
            reps_str = "; ".join(
                f"{r.first_name} {r.last_name} (email={r.email or ''}, role={r.rep_role or ''}, id={r.party_rep_id})"
                for r in (party.party_reps or [])
            )
            reps_part = f" | Reps: {reps_str}" if reps_str else ""
            view_existing_init_input += f"Party: {party.legal_name} | {party.party_id} | Role: {party.role}{reps_part} | Description: {party.role_description or ''}\n"

        
        prompt = (
            view_existing_init_input +
            "\n\n" + context + "\n\n" +
            f'Extract initial input (all parties, updated title and background) based on the project context above.\n'
            f'**IMPORTANT**:\n'
            f'- Keep all party_ids for existing parties. Update role, role_description if needed.\n'
            f'- For existing parties that already have reps: preserve them (re-use their id), update any missing fields if better info is found.\n'
            f'- For parties listed in **Additional info** above: copy their reps directly into the matching party\'s party_reps. Do not skip this step.\n'
            f'- Do not translate any legal names, but keep them as they are (e.g "Plan & Byggningsetaten" should not be translated to "The Norwegian Building Authority").\n'
            f'- Add any new parties (organisations or individuals acting independently) found in the context.\n'
            f'- A person who appears as sender/recipient across many sources (e.g. john@email.no, John Doe) is a key representative — do not omit them.'
        )
        logger.info(f"\n ===== DEBUG PROMPT INPUT ====  \n\n {prompt}\n\n")
        structured_llm = apply_retry(self._llm.with_structured_output(InitialInput, method="json_mode"), self.config)
        updated_input = await structured_llm.ainvoke(prompt)

        for party in updated_input.parties:
            if not party.party_id or not self.is_valid_uuid(party.party_id):
                party.party_id = str(uuid.uuid4())
            for rep in party.party_reps or []:
                rep.party_id = party.party_id
                if not rep.party_rep_id or not self.is_valid_uuid(rep.party_rep_id):
                    rep.party_rep_id = str(uuid.uuid4())

        org_ids = set(p.party_id for p in existing_initial_input.parties or [] if p.party_id)
        org_rep_ids = {
            p.party_id: set(r.party_rep_id for r in p.party_reps or [] if r.party_rep_id)
            for p in existing_initial_input.parties or []
        }

        seen_parties = set()
        deduped_parties = []

        # De-duplicate the LLM output
        for party in updated_input.parties:
            if party.party_id not in seen_parties:
                deduped_parties.append(party)
                seen_parties.add(party.party_id)

        # Re-add any existing party the LLM dropped entirely
        for party_id in org_ids:
            if party_id not in seen_parties:
                original_party = next((p for p in existing_initial_input.parties if p.party_id == party_id), None)
                if original_party:
                    deduped_parties.append(original_party)
                    seen_parties.add(party_id)

        # Restore any existing rep the LLM dropped from a party it kept
        for party in deduped_parties:
            org_reps = org_rep_ids.get(party.party_id, set())
            new_reps = set(r.party_rep_id for r in party.party_reps or [] if r.party_rep_id)
            missing_rep_ids = org_reps - new_reps
            if missing_rep_ids:
                logger.warning(f'⚠️ Party {party.legal_name} ({party.party_id}) is missing reps: {missing_rep_ids}')
                for rep_id in missing_rep_ids:
                    original_rep = next(
                        (rep for p in (existing_initial_input.parties or []) if p.party_id == party.party_id
                         for rep in (p.party_reps or []) if rep.party_rep_id == rep_id),
                        None,
                    )
                    if original_rep:
                        if party.party_reps is None:
                            party.party_reps = []
                        party.party_reps.append(original_rep)
                        logger.info(f'✅ Restored missing rep {original_rep.first_name} {original_rep.last_name} (id={original_rep.party_rep_id}) to {party.legal_name}')

        logger.info(f'✅ Updated Parties: {len(existing_initial_input.parties)} → {len(updated_input.parties)} (LLM) → {len(deduped_parties)} (deduplicated)')
        updated_input.parties = deduped_parties
        
        return updated_input
    