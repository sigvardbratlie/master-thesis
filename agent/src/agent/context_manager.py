
import json
from typing import List,Optional
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
    
    # ===== TRUNCATION HELPERS =====
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
        prompt = f'Analyze the following case introduction and extract key information into the InitialInput structure. If not sufficient information, leave blank:\n\n{init_input}. '
        return await structured_llm.ainvoke(prompt, config=config)
    
    async def analyze_docs(self,
                input_ : InitialInput | FactSheet,
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
            events: Optional[List[Event]] = []

        class MultipleAttachmentsResult(BaseModel):
            attachments: List[AttachmentWithEvents]

        documents_formatted = "\n\n".join([
            f"DOCUMENT #{idx+1} (file_id: {att.file_id}):\n{att.model_dump(include={'body','file_type',})}"
            for idx, att in enumerate(attachments)
        ])

        structured_llm = self.llm.with_structured_output(MultipleAttachmentsResult, method="function_calling")
        init_prompt = f'{input_.shorten_factsheet()}\n\n' if isinstance(input_, FactSheet) else f'Case input: {input_.model_dump(mode = "json")}\n\n'
        prompt = init_prompt + f'''Analyze the following {len(attachments)} documents.

                                For EACH document, return an AttachmentWithEvents object containing:
                                1. attachment: AttachmentExtracted - metadata from that document (MUST set file_id to the file_id shown for each document)
                                2. events: List[Event] or null - timeline events mentioned in that document

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
                # Set file_id to the original file_id for consistency
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
                input_ : InitialInput | FactSheet,
                emails : list[EmailModel],
                config: RunnableConfig = None,
                ) -> dict:
        '''Function to analyze multiple documents and extract structured data as Attachments.'''
        
        class EmailAnalysisResult(BaseModel):
            """Result for ONE email analysis"""
            email: EmailExtracted = Field(description="Extracted metadata and content from this specific email")
            events: Optional[List[Event]] = Field(default=None, description="Timeline events mentioned in this email (can be empty list or null if no events found)")
        
        class EmailsAnalysisResult(BaseModel):
            """Result containing ALL email analyses"""
            emails: List[EmailAnalysisResult] = Field(description="List of email analysis results - one EmailAnalysisResult object per input email")

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
        init_prompt = f'{input_.shorten_factsheet()}\n\n' if isinstance(input_, FactSheet) else f'Case input: {input_.model_dump(mode = "json")}\n\n'
        
        # Format emails with clear ID separation
        emails_formatted = "\n\n".join([
            f"EMAIL #{idx+1} (email_id: {eml.file_id}):\n{eml.model_dump(include={'from_addr',"to","cc","bcc",'subject','body_text', "date",})}"
            for idx, eml in enumerate(emails)
        ])
        
        # Clearer prompt showing the expected structure
        prompt = init_prompt + f'''Analyze the following {len(emails)} emails.
        
                                For EACH email, return an EmailAnalysisResult object containing:
                                1. email: EmailExtracted - metadata from that email (MUST set email_id to the file_id shown for each email)
                                2. events: List[Event] or null - timeline events mentioned in that email

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
            })
            result_emails.append(Email(**email_data))
            logger.debug(f'✅ Email #{idx+1} done — email_id={input_email.file_id}')
        
        return {"emails" : result_emails,
                "events" : events,
                "damages" : damages,
                "deadlines" : deadlines,
                "claims" : claims}


    async def analyze_governing_law(self, events : list[Event], rag_content_law : str, config: RunnableConfig = None) -> GoverningLaw:
        '''Function to analyze case events and extract governing law information.
        
        Args:
            events (list[Event]): The list of case events.
            rag_content_law (str): Relevant legal context retrieved via RAG.
            
        Returns:
            GoverningLaw : The structured GoverningLaw object with extracted information.
        '''
        if not events:
            logger.warning('No events provided for governing law analysis. Returning empty GoverningLaw.')
            return
        if not rag_content_law:
            logger.warning('No RAG content provided for governing law analysis. Proceeding with events only.')
        
            if not isinstance(rag_content_law, str):
                logger.warning(f'RAG content for governing law is not a string: Instance {type(rag_content_law)}. ')
                if isinstance(rag_content_law, dict):
                    logger.debug('RAG content is a dict. Converting to JSON string for analysis.')
                    rag_content_law = json.dumps(rag_content_law)
                elif isinstance(rag_content_law, list):
                    if all(isinstance(item, dict) for item in rag_content_law):
                        logger.debug('RAG content is a list of dicts. Converting to JSON string for analysis.')
                        rag_content_law = json.dumps(rag_content_law)
                    elif isinstance(rag_content_law[0], Document):
                        logger.debug('RAG content is a list of Documents. Concatenating page content for analysis.')
                        rag_content_law = "\n\n".join([doc.page_content for doc in rag_content_law])
                    else:
                        logger.warning('RAG content is a list but not of dicts or Documents. Converting each item to string and concatenating.')
                        rag_content_law = " ".join(str(item) for item in rag_content_law)
                else:
                    logger.warning('RAG content is of an unexpected type. Converting to string for analysis.')
                    rag_content_law = str(rag_content_law)
        
        structured_llm = self.llm.with_structured_output(GoverningLaw, method="function_calling")
        law_context = f'Extracted legal context:\n\n{rag_content_law}\n\n' if rag_content_law else ''
        prompt = law_context + f'Based on the following case events, analyze and extract governing law information:\n\n{events}'
        return await structured_llm.ainvoke(prompt, config=config)

    async def analyze_factual_facts(self,
                              initial_input : InitialInput,
                              events : list[Event],
                              config: RunnableConfig = None,
                              ) -> FactualFacts:
        '''Function to analyze case events and extract disputed and undisputed facts.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            events (list[Event]): The list of case events.
        
        Returns: 
            FactualFacts : The structured FactualFacts object with disputed and undisputed facts.
        '''
        structured_llm = self.llm.with_structured_output(FactualFacts, method="function_calling")
        init = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init + f'Based on the following case events, extract disputed and undisputed facts:\n\n{events}'
        return await structured_llm.ainvoke(prompt, config=config)
    

    async def clean_element(self, 
                            content: BaseModel, 
                            element_type : str,
                            project_data : ProjectData,
                            ) -> list[dict]:   
        '''Clean/merge items with LLM, then deduplicate with Python and assign UUIDs.'''
        
        if not content:
            logger.warning('No content provided for cleaning. Filling in empty list.')
            content = []

        model_map  = {"events" : Events, "damages" : Damages, "claims" : Claims,
                      "deadlines" : Deadlines, "parties" : Parties}
        id_map = {"events" : "event_id", "damages" : "damage_id", "claims" : "claim_id",
                  "deadlines" : "deadline_id", "parties" : "party_id"}
        
        name = element_type[:-1].capitalize()  # e.g. "events" -> "Event"
        ContentList = model_map.get(element_type)
        if not ContentList:
            logger.error(f'❌ Unknown content type: {name}')
            return []
        
        id_field = id_map.get(element_type, f"{name.lower()}_id")
        
        # Step 1: LLM cleans/merges/fills missing info (but may create duplicates)
        structured_llm = self.llm.with_structured_output(ContentList, method="function_calling")
        if content:
            data = content.model_dump(mode="json").get(element_type, []) if hasattr(content, 'model_dump') else content.get(element_type, [])
        else:
            data = []
        prompt = (
            f'{project_data.shorten_factsheet(excluded_fields=[element_type])}\n'
            f'{project_data.shorten_attachments()}\n'
            f'{project_data.shorten_emails()}\n'
            f'Use the context of the given above to clean, fill in missing information, if content is empty -> fill the content!'
            f'If content is filled, merge similar entries for the following {name} items if they are refering to the same entity.'
            "I.e for party, fill in all relevant roles such as plaintiff, defendant, witness, legal representative, etc. For events, fill in event dates and categorize the type of event.n\n'"
            f":\n\n{data}"
        )
        logger.debug(f"─── Cleaning prompt for {name.upper()} ───\n{prompt}")
        
        response = await structured_llm.ainvoke(prompt)
        if not response:
            logger.warning('No response from LLM during cleaning.')
            return []
        
        llm_cleaned = response.model_dump(mode="json").get(element_type, [])
        
        # Build map of original UUIDs from input data
        original_uuids = {}
        for item in data:
            for key, value in item.items():
                if key.endswith('_id') and value and self.is_valid_uuid(value):
                    original_uuids[value] = key
        
        def post_process(llm_cleaned, element_type, id_field, ):
            logger.debug(f"─── Post-processing {len(llm_cleaned)} {name} items ───")
            logger.debug(f"llm_cleaned: {llm_cleaned}")
            # Step 2: Python deduplicates based on identity fields
            identity_fields = {
                "events": ["event_date", "category", "event_name"],
                "damages": ["category", "file_id", "party_role"],
                "claims": ["relief_sought", "file_id", "party_role"],
                "deadlines": ["file_id", "deadline_date", "party_role"],
                "parties": ["legal_name", "role"],
            }.get(element_type, [])
            
            logger.debug(f"Identity fields for {element_type}: {identity_fields}")
            
            seen = {}
            result = []
            
            for idx, item in enumerate(llm_cleaned):
                sig_values = tuple(item.get(field) for field in identity_fields)
                logger.debug(f"Item {idx}: sig={sig_values} id={item.get(id_field)}")
                
                if sig_values in seen:
                    logger.warning(f'⚠️  Duplicate {name} #{idx} — skipping: {sig_values}')
                    continue
                
                seen[sig_values] = item[id_field]
                result.append(item)
                logger.debug(f"  → added (total: {len(result)})")
            
            logger.debug(f"─── Post-processing done: {len(result)} unique items ───")
            return result
        
        for item in llm_cleaned:
            if not item.get(id_field):
                logger.warning(f'Missing {id_field} in LLM output item: {item}. Assigning new UUID.')
                item[id_field] = str(uuid.uuid4())
            elif not self.is_valid_uuid(item[id_field]):
                logger.warning(f'Invalid UUID in LLM output for {id_field}: "{item[id_field]}". Assigning new UUID.')
                item[id_field] = str(uuid.uuid4())
        
        result = post_process(llm_cleaned, element_type=element_type, id_field=id_field)
        
        logger.info(f'✅ Cleaned {name}: {len(data) if data else 0} → {len(llm_cleaned) if llm_cleaned else 0} (LLM) → {len(result) if result else 0} (deduplicated)')
        return result

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

    async def clean_metadata(self, content : str,
                             element_type : str,
                             project_data : ProjectData,
                             ) -> str:
        """Clean metadata fields (title, background) using structured output to avoid LLM wrapper text."""
        
        if element_type not in ["title", "background"]:
            logger.error(f'❌ Unknown element type for metadata cleaning: {element_type}')
            return content
        
        # Create a generic single-field model dynamically
        CleanedText = create_model(
            'CleanedText',
            cleaned_text=(str, Field(description=f"The cleaned and revised {element_type}, without any preamble or explanation"))
        )
        
        prompt = (
            f'{project_data.shorten_factsheet(excluded_fields=[element_type])}\n'
            f'{project_data.shorten_attachments()}\n'
            f'{project_data.shorten_emails()}\n'
            f'Task: Clean and/or rewrite the following {element_type} according to the context. '
            f'Return ONLY the cleaned {element_type} itself, no explanation or preamble.\n\n'
            f'Original {element_type}:\n{content}'
        )
        #logger.debug(f" ====== PROMPT FOR CLEANING {element_type.upper()} ====== \n{prompt}\n\n")
        
        structured_llm = self.llm.with_structured_output(CleanedText, method="function_calling")
        response = await structured_llm.ainvoke(prompt)
        
        return response.cleaned_text if hasattr(response, 'cleaned_text') else str(response)
    
    async def clean_all_metadata(self, 
                             project_data : ProjectData,
                             ) -> str:
        """Clean metadata fields (title, background) using structured output to avoid LLM wrapper text."""
        
        
        
        class ProjectMetadata(BaseModel):
            title: str = Field(description="The cleaned and revised title, without any preamble or explanation")
            background: str = Field(description="The cleaned and revised background, without any preamble or explanation")
        
        prompt = (
            f'{project_data.shorten_factsheet(excluded_fields=["title", "background"])}\n'
            #f'{project_data.shorten_attachments()}\n'
            #f'{project_data.shorten_emails()}\n'
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
    
    async def clean_legal_attr(self, 
                               content : BaseModel, 
                               element_type : str,
                               project_data : ProjectData
                               ) -> dict:
        '''Clean/fill a simple attribute (e.g. case title) with LLM.
        
        Returns:
            - List[str] for "disputed_facts" and "undisputed_facts"
            - dict for "governing_law"
        '''
        # Define which types need structured output
        structured_types = {
            "disputed_facts": List[str],
            "undisputed_facts": List[str],
            "governing_law": GoverningLaw,
        }
        if element_type not in structured_types:
            raise ValueError(f'Unknown element type for cleaning: {element_type}')
        
        prompt = (
            f'Context from factsheet:\n{project_data.shorten_factsheet(excluded_fields=[element_type])}\n\n'
            f'Context from attachments:\n{project_data.shorten_attachments()}\n\n'
            f'Context from emails:\n{project_data.shorten_emails()}\n\n'
            f'Task: Clean and revise the following {element_type}. '
            f'Return ONLY the cleaned {element_type} itself, no explanation or preamble.\n\n'
            f'Original {element_type}:\n{content}'
        )
        
        structured_llm = self.llm.with_structured_output(structured_types[element_type], method="function_calling")
        response = await structured_llm.ainvoke(prompt)
        
        # Return based on type
        if hasattr(response, 'model_dump'):  # Pydantic model (GoverningLaw)
            return response.model_dump()
        else:  # List[str]
            return response
    
    # async def update_project_from_session(self, ):
    #     pass