
import json
import tiktoken
import logging
from uuid import uuid4
import uuid
import asyncio
from pydantic import BaseModel, create_model,Field
from langchain_core.messages import AIMessage,ToolMessage
from langchain_core.documents import Document
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from langchain.chat_models import init_chat_model

from models import *

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self, llm: BaseChatModel = None,
                 ):
        self._llm = init_chat_model("gemini-2.5-flash", model_provider="google_genai") if llm is None else llm
        #self.vector_search = VectorSearch()

    @property
    def llm(self):
        return self._llm
    @llm.setter
    def llm(self, value: BaseChatModel):
        self._llm = value
    
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
        while truncated and isinstance(truncated[0], ToolMessage):
            truncated.pop(0)
        
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
        structured_llm = self.llm.with_structured_output(InitialInput, method="function_calling")
        prompt = f'Analyze the following project description and extract key information into the InitialInput structure. If not sufficient information, leave blank:\n\n{init_input}.'
        init_input = await structured_llm.ainvoke(prompt, config=config)
        for party in init_input.parties or []:
            party.party_id = str(uuid4())
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

        structured_llm = self.llm.with_structured_output(MultipleAttachmentsResult, method="function_calling")
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

                                Documents to analyze:
                                {documents_formatted}'''
        retry_prompt = prompt
        response = None
        for attempt in range(2):
            try:
                response = await structured_llm.ainvoke(retry_prompt, config=config)
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed validation: {e}")
                if attempt == 0:
                    retry_prompt = prompt + f"\n\nPREVIOUS ATTEMPT FAILED WITH VALIDATION ERROR:\n{e}\nPlease fix the above errors and try again."
                else:
                    logger.error("Both attempts failed, returning empty result.")
                    return {"attachments": [], "events": [], "damages": [], "deadlines": [], "claims": []}

        if not response or not response.attachments:
            logger.error("LLM returned empty or invalid response")
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

        structured_llm = self.llm.with_structured_output(EmailsAnalysisResult, method="function_calling")
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
                "from": input_email.from_addr,
                "cc": input_email.cc,
                "bcc": input_email.bcc,
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

    async def clean_elements(self,
                             element_types: list[str],
                             project_data: ProjectData,
                             ) -> dict[str, list[dict]]:
        """Clean multiple element types in a single LLM call. Returns {element_type: cleaned_items}."""
        item_model_map = {
            "events": (list[Event], Field(default_factory=list)),
            "parties": (list[Party], Field(default_factory=list)),
            "claims": (list[Claim], Field(default_factory=list)),
            "damages": (list[Damage], Field(default_factory=list)),
            "deadlines": (list[Deadline], Field(default_factory=list)),
        }
        id_map = {
            "events": "event_id", "parties": "party_id", "claims": "claim_id",
            "damages": "damage_id", "deadlines": "deadline_id",
        }
        identity_fields_map = {
            "events": ["event_date", "category", "event_name"],
            "damages": ["category", "file_id", "party_role"],
            "claims": ["relief_sought", "file_id", "party_role"],
            "deadlines": ["file_id", "deadline_date", "party_role"],
            "parties": ["legal_name", "role"],
        }

        CombinedModel = create_model("CombinedElements", **{et: item_model_map[et] for et in element_types})

        data_map = {et: project_data.factsheet.model_dump().get(et, []) for et in element_types}

        prompt = (
            f'{project_data.shorten_factsheet(excluded_fields=element_types)}\n'
            f'{project_data.shorten_attachments()}\n'
            f'{project_data.shorten_emails()}\n'
            f'Use the context above to clean and fill in missing information for: {", ".join(element_types)}.\n'
            f'Merge entries that refer to the same entity within each type.\n\n'
        )
        for et in element_types:
            prompt += f'Current {et}:\n{json.dumps(data_map[et], default=str)}\n\n'

        structured_llm = self.llm.with_structured_output(CombinedModel, method="function_calling")
        response = await structured_llm.ainvoke(prompt)

        results = {}
        for et in element_types:
            id_field = id_map[et]
            raw_items = getattr(response, et, []) or []
            llm_cleaned = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in raw_items]

            for item in llm_cleaned:
                if not item.get(id_field) or not self.is_valid_uuid(item[id_field]):
                    item[id_field] = str(uuid.uuid4())

            identity_fields = identity_fields_map.get(et, [])
            seen = {}
            deduped = []
            for item in llm_cleaned:
                sig = tuple(item.get(f) for f in identity_fields)
                if sig not in seen:
                    seen[sig] = True
                    deduped.append(item)

            logger.info(f'✅ Cleaned {et}: {len(data_map[et])} → {len(llm_cleaned)} (LLM) → {len(deduped)} (deduplicated)')
            results[et] = deduped

        return results

    async def clean_all_metadata(self, 
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
        structured_llm = self.llm.with_structured_output(ProjectMetadata, method="function_calling")
        response = await structured_llm.ainvoke(prompt)
        
        return {
            "title": response.title if hasattr(response, 'title') else str(response),
            "background": response.background if hasattr(response, 'background') else str(response)
        }
    
    async def update_initial_input(self, events : list[Event],existing_initial_input : InitialInput) -> InitialInput:
        """Update the initial input string based on the cleaned title and background."""
        view_events = "Current Events"
        view_events += "\t* Format: event_start_date | event_name | file_id | description" + "(Disputed)"  + "\n"
        if isinstance(events, list):
            events.sort(key=lambda e: str(e.event_start_date))
        else:
            raise ValueError(f'Events should be of type list, but actual type is {type(events)}')
        for e in events:
            view_events += f"\t* {e.event_start_date} | {e.event_name} | {e.file_id or 'No file ID'} | {e.description or ''}"
            if e.disputed:
                view_events += " | Disputed"
            view_events += "\n"

        view_existing_init_input = "Existing Initial Input:\n"
        view_existing_init_input += f"Title: {existing_initial_input.title}\n"
        view_existing_init_input += f"Background: {existing_initial_input.background}\n"
        for party in existing_initial_input.parties or []:
            view_existing_init_input += f"Party: {party.legal_name} | {party.party_id} | Role: {party.role} | Description: {party.role_description or ''}\n"

        prompt = (
            view_existing_init_input +
            view_events +
            f'Extract initial input (All parties and updated title and background) based on the project events'
            f'**IMPORTANT**: Keep all party_ids for existing parties, and update the additional information if nececcary (i.e role, role_description, key_contact, etc)'
        )
        structured_llm = self.llm.with_structured_output(InitialInput, method="function_calling")
        updated_input = await structured_llm.ainvoke(prompt)
        org_ids = set(p.party_id for p in existing_initial_input.parties or [] if p.party_id)

        for party in updated_input.parties:
            if not party.party_id or not self.is_valid_uuid(party.party_id):
                party.party_id = str(uuid.uuid4())

        seen = set()
        deduped = []
        for party in updated_input.parties:
            if party.party_id not in seen:
                deduped.append(party)
                seen.add(party.party_id)
        for party_id in org_ids:
            if party_id not in seen:
                original_party = next((p for p in existing_initial_input.parties if p.party_id == party_id), None)
                if original_party:
                    deduped.append(original_party)
                    seen.add(party_id)

        logger.info(f'✅ Updated Parties: {len(existing_initial_input.parties)} → {len(updated_input.parties)} (LLM) → {len(deduped)} (deduplicated)')
        updated_input.parties = deduped
        
        return updated_input
    