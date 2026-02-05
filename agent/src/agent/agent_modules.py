import json
from pyexpat import model
from typing import Dict, Type,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
import os
import tiktoken
import logging
from uuid import uuid4
import asyncio
from pydantic import BaseModel, RootModel, create_model

from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,BaseMessage,ToolMessage,AIMessageChunk
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.language_models.chat_models import BaseChatModel

from langchain.chat_models import init_chat_model

from agent.basemodels import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, model_name: str = "gpt-4o-mini", model_provider: str = "openai"):
        self.model = init_chat_model(model_name, model_provider=model_provider, temperature=0)

    def summarize(self, content: str, limit: int = None) -> str:
        if limit and len(content) > limit:
            logger.info(f'Tool result exceeded token limit of {limit}. Truncating result.')
            query  = f'Summarize the this data in 200-400 tokens: {str(content)[:limit//2]}... {str(content)[-limit//2:]}'
        else:
            query  = f'Summarize the this data in MAX 200-400 tokens: {str(content)}'
        summary_response = self.model.invoke(query)
        return summary_response.content if hasattr(summary_response, 'content') else str(summary_response)

    def mk_title(self, messages : list):
        prompt = f'Make a short title (2-5 words) as summary of this chat. MAX 5 words. Use company if present: {messages}'
        res = self.model.invoke(prompt)
        title = res.content
        logger.info(f'Generated title: {title}')
        return title


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
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        token_count = 0
        truncated = []

        for msg in reversed(messages):
            token_count += len(enc.encode(msg.content or ""))
            truncated.insert(0, msg)

            if token_count > max_tokens:
                break

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

    # ===== FUNCTIONS FOR INITIAL FACTSHEET CREATION =====
    async def analyze_init_input(self, init_input : str) -> InitialInput:
        structured_llm = self.llm.with_structured_output(InitialInput, method="function_calling")
        prompt = f'Analyze the following case introduction and extract key information into the InitialInput structure:\n\n{init_input}'
        return await structured_llm.ainvoke(prompt)
    
    async def __analyze_events(self, initial_input : InitialInput , content : str,file_id: str) -> Events:
        '''Analyzes document content to extract a list of events.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            content (str): The document content to analyze.

        Returns:
            list[Event]: A list of extracted Event objects.
        '''
        structured_llm = self.llm.with_structured_output(Events, method="function_calling")
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{content}'
        response = await structured_llm.ainvoke(prompt)
        for event in response.events:
            event.file_id = file_id
            event.event_id = str(uuid4())
        return response
    

    async def analyze_doc(self, 
                initial_input : InitialInput ,
                content: str, 
                file_id : str, 
                filename: str, 
                path: str, 
                file_type: str, 
                size: int, 
                ) -> dict:
        ''' Function to analyze document content and extract structured data as Attachment.'''
        
        # Kombiner til én Pydantic model
        class AttachmentWithEvents(BaseModel):
            attachment: AttachmentExtracted
            events: List[Event]
        
        structured_llm = self.llm.with_structured_output(AttachmentWithEvents, method="function_calling")
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document and extract BOTH attachment metadata AND timeline events:\n\n{content}'
        
        for attempt in range(3):  # Retry mechanism
            try:
                response = await structured_llm.ainvoke(prompt)
                break  # Exit loop if successful
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Rate limit hit, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        # Process events
        for event in response.events:
            event.file_id = file_id
            event.event_id = str(uuid4())
        
        # Process attachment damages/claims/deadlines
        if response.attachment.damages:
            for damage in response.attachment.damages:
                damage.file_id = file_id
                damage.damage_id = str(uuid4())
        if response.attachment.deadlines:
            for deadline in response.attachment.deadlines:
                deadline.file_id = file_id
                deadline.deadline_id = str(uuid4())
        if response.attachment.claims:
            for claim in response.attachment.claims:
                claim.file_id = file_id
                claim.claim_id = str(uuid4())
        
        file = Attachment(**response.attachment.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in response.events],
                        )
        return {"file": file, "events": response.events}
    
    async def analyze_governing_law(self, events : list[Event],rag_content_law : str) -> GoverningLaw:
        '''Function to analyze case events and extract governing law information.
        
        Args:
            events (list[Event]): The list of case events.
            rag_content_law (str): Relevant legal context retrieved via RAG.
            
        Returns:
            GoverningLaw : The structured GoverningLaw object with extracted information.
        '''
        if not isinstance(rag_content_law, str):
            logger.warning(f'RAG content for governing law is not a string: Instance {type(rag_content_law)}. ')
            if isinstance(rag_content_law, dict):
                rag_content_law = json.dumps(rag_content_law)
            elif isinstance(rag_content_law, list):
                rag_content_law = " ".join([str(item) for item in rag_content_law])
            else:
                rag_content_law = str(rag_content_law)
                
        structured_llm = self.llm.with_structured_output(GoverningLaw, method="function_calling")
        law_context = f'Extracted legal context:\n\n{rag_content_law}\n\n' if rag_content_law else ''
        prompt = law_context + f'Based on the following case events, analyze and extract governing law information:\n\n{events}'
        return await structured_llm.ainvoke(prompt)
        
    async def analyze_factual_facts(self, 
                              initial_input : InitialInput, 
                              events : list[Event], 
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
        return await structured_llm.ainvoke(prompt)
    
    # ===== FUNCTIONS FOR UPDATING EXISTING FACTSHEET =====
    async def __consider_new_events(self,
                            factsheet : FactSheet,
                         new_content : str,
                         new_user_input : str,
                         file_id : str
                         ) -> list[Event]:
        structured_llm = self.llm.with_structured_output(Events, method="function_calling")
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        init_prompt = f'Existing factsheet:\n\n{factsheet_data}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{new_content}' + f'\n\nNew user input:\n\n{new_user_input}\n\n'
        response = await structured_llm.ainvoke(prompt)
        for event in response.events:
            event.file_id = file_id
        return response.events
    
    def is_valid_uuid(self, val):
        try:
            uuid.UUID(str(val))
            return True
        except ValueError:
            return False

    async def consider_new_doc(self,
                            factsheet : FactSheet,
                         new_content : str,
                         new_user_input : str,
                         file_id : str,
                         filename : str,
                         path : str,
                         file_type : str,
                         size : int,
                         ) -> dict:
        '''Function to analyze new document content in relation to existing FactSheet.
        Args:
            factsheet (FactSheet | dict): The existing FactSheet object or dict.
            content (str): The new document content to analyze.
            file_id (str): The unique identifier for the file.
            filename (str): The name of the file.
            path (str): The storage path of the file.
            file_type (str): The MIME type of the file.
            size (int): The size of the file in bytes.

        Returns:
            dict: A dictionary indicating relevance and suggested updates.
        '''
        class AttachmentExtractedWithEvents(BaseModel):
            attachment: AttachmentExtracted
            events: List[Event]
        
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        existing_factsheet = f'Existing factsheet:\n\n{factsheet_data}\n\n'
        prompt = existing_factsheet + f'Analyze the following document and extract BOTH attachment metadata AND timeline events:\n\n{new_content}'
        structured_llm = self.llm.with_structured_output(AttachmentExtractedWithEvents, method="function_calling")

        for attempt in range(3):  # Retry mechanism
            try:
                response = await structured_llm.ainvoke(prompt)
                break  # Exit loop if successful
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Rate limit hit, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
        
        # Process events
        for event in response.events:
            event.file_id = file_id
            event.event_id = str(uuid4())
        
        # Process attachment damages/claims/deadlines
        if response.attachment.damages:
            for damage in response.attachment.damages:
                damage.file_id = file_id
                damage.damage_id = str(uuid4())
        if response.attachment.deadlines:
            for deadline in response.attachment.deadlines:
                deadline.file_id = file_id
                deadline.deadline_id = str(uuid4())
        if response.attachment.claims:
            for claim in response.attachment.claims:
                claim.file_id = file_id
                claim.claim_id = str(uuid4())
        
        file = Attachment(**response.attachment.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in response.events],
                        )
        return {"file": file, "events": response.events}

    async def analyze_new_input(self,
                         factsheet : FactSheet,
                         new_user_input : str,
                         new_content : Optional[str] = "",
                         file_id : Optional[str] = None,
                         filename : Optional[str] = None,
                         path : Optional[str] = None,
                         file_type : Optional[str] = None,
                         size : Optional[int] = None,

                         ) -> dict:
        '''Function to update an existing FactSheet with new input data.

        Args:
            factsheet (FactSheet | dict): The existing FactSheet to update.
            new_user_input (str): The new input query or information from the user.
            new_content (str, optional): New document content to consider for updating the factsheet.
            file_id (str, optional): The unique identifier for the new document.
            filename (str, optional): The name of the new document.
            path (str, optional): The storage path of the new document.
            file_type (str, optional): The MIME type of the new document.
            size (int, optional): The size of the new document in bytes.

        Returns:
            dict: Result containing updated file, events, damages, deadlines, claims.
        '''
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        existing_facts = f"Existing factsheet:\n\n{factsheet_data}"
        prompt = existing_facts + f"\n\nNew user content: {new_content}" + f'\n\nReturn True if the following new input is relevant to update the existing factsheet, else return False:\n\n{new_user_input}'
        structured_llm = self.llm.with_structured_output(RelevanceCheck, method="function_calling")  
        relevant = await structured_llm.ainvoke(prompt)
        if relevant.is_relevant:
            result = await self.consider_new_doc(new_content=new_content,
                                            new_user_input=new_user_input,
                                            factsheet=factsheet,
                                            file_id=file_id,
                                            filename=filename,
                                            path=path,
                                            file_type=file_type,
                                            size=size,)
            return result

    async def clean_element(self, content: BaseModel, factsheet: FactSheet, element_type : str) -> list[dict]:   
        '''Clean/merge items with LLM, then deduplicate with Python and assign UUIDs.'''
        
        if not content:
            logger.warning('No content provided for cleaning. Filling in empty list.')
            content = []
        
        # model_map = {
        #     "Event": Events, "Damage": Damages, "Claim": Claims,
        #     "Deadline": Deadlines, "Party": Parties
        # }
        model_map  = {"events" : Events, "damages" : Damages, "claims" : Claims,
                      "deadlines" : Deadlines, "parties" : Parties}
        id_map = {"events" : "event_id", "damages" : "damage_id", "claims" : "claim_id",
                  "deadlines" : "deadline_id", "parties" : "party_id"}
        
        name = element_type[:-1].capitalize()  # e.g. "events" -> "Event"
        ContentList = model_map.get(element_type)
        if not ContentList:
            logger.error(f'Unknown content type: {name}')
            return []
        
        id_field = id_map.get(element_type, f"{name.lower()}_id")
        
        # Step 1: LLM cleans/merges/fills missing info (but may create duplicates)
        structured_llm = self.llm.with_structured_output(ContentList, method="function_calling")
        if content:
            data = content.model_dump(mode="json").get(element_type, []) if hasattr(content, 'model_dump') else content.get(element_type, [])
        else:
            data = []
        prompt = (
            f"Context: {factsheet.model_dump()}\n\n"
            f'Use the context of the existing factsheet to clean, fill in missing information, '
            f'and merge similar entries for the following {name} items.'
            "I.e for party, fill in all relevant roles such as plaintiff, defendant, witness, legal representative, etc. For events, fill in event dates and categorize the type of event. For damages, fill in type of damage and amount if mentioned. For claims, fill in legal basis and relief sought. For deadlines, fill in deadline date and associated party role.\n\n'"
            f":\n\n{data}"
        )
        
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
        
        def ensure_uuid(item, original_uuids=original_uuids, id_field=id_field):
            # Check ALL _id fields for validity
            for key, value in list(item.items()):
                if key.endswith('_id') and value is not None:
                    if not self.is_valid_uuid(value):
                        if value in original_uuids:
                            logger.debug(f'LLM modified original UUID for {key}: "{value}". Restoring original UUID: {original_uuids[value]}')
                            item[key] = original_uuids[value]
                        else:
                            new_uuid = str(uuid.uuid4())
                            logger.warning(f'LLM produced invalid UUID in {key}: "{value}" -> {new_uuid}')
                            item[key] = new_uuid
                    elif value not in original_uuids:
                        # UUID not in original input - LLM created it
                        logger.debug(f'LLM created new UUID for {key}: {value}')
            
            # Assign UUID if missing for main ID field
            if not item.get(id_field):
                logger.warning(f'Missing {id_field} in item {item}. Assigning new UUID.')
                item[id_field] = str(uuid.uuid4())


        def post_process(llm_cleaned, element_type, id_field, ):
            logger.info(f"\n=== POST-PROCESSING {len(llm_cleaned)} {name} items ===")
            logger.info(f"llm_cleaned: \n{llm_cleaned}\n\n")
            # Step 2: Python deduplicates based on identity fields
            identity_fields = {
                "events": ["event_date", "category", "event_name"],
                "damages": ["category", "file_id", "party_role"],
                "claims": ["relief_sought", "file_id", "party_role"],
                "deadlines": ["file_id", "deadline_date", "party_role"],
                "parties": ["legal_name", "role"],
            }.get(element_type, [])
            
            logger.info(f"Identity fields for {element_type}: {identity_fields}")
            
            seen = {}
            result = []
            
            for idx, item in enumerate(llm_cleaned):
                sig_values = tuple(item.get(field) for field in identity_fields)
                logger.info(f"Item {idx}: signature = {sig_values}, id = {item.get(id_field)}")
                
                if sig_values in seen:
                    logger.warning(f'DUPLICATE FOUND! Skipping {name} #{idx}: {sig_values}')
                    continue
                
                seen[sig_values] = item[id_field]
                result.append(item)
                logger.info(f"  -> Added to result (total: {len(result)})")
            
            logger.info(f"=== POST-PROCESSING COMPLETE: {len(result)} unique items ===\n")
            return result
        
        
        for item in llm_cleaned:
            ensure_uuid(item, original_uuids=original_uuids, id_field=id_field)
        
        result = post_process(llm_cleaned, element_type=element_type, id_field=id_field)
        
        logger.info(f'Cleaned {len(data) if data else 0} {name} items -> {len(llm_cleaned) if llm_cleaned else 0} (LLM) -> {len(result) if result else 0} (deduplicated)')
        return result
    
    async def clean_factsheet(self,
                         factsheet : FactSheet,
                         ) -> FactSheet:
        '''Function to clean and deduplicate disputed and undisputed facts.'''
        structured_llm = self.llm.with_structured_output(FactSheet, method="function_calling")
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        prompt = f'Existing factsheet:\n\n{factsheet_data}\n\n' + f'Clean this factsheet. Remove irrelevant or duplicate contents.'
        try:
            return await structured_llm.ainvoke(prompt)
        except Exception as e:
            logger.error(f'Error during factsheet cleaning: {e}', exc_info=True)
            return
    
    
class ToolManager:
    def __init__(self):
        pass

    def format_tool_result(self, result: Any) -> str:
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return str(result)


