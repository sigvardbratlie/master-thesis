import json
from pyexpat import model
from typing import Dict,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
import os
from io import BytesIO
from PyPDF2 import PdfReader
import tiktoken
import logging

from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,BaseMessage,ToolMessage,AIMessageChunk
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.language_models.chat_models import BaseChatModel


from langchain_openai import ChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore


from google.cloud import bigquery
from google.cloud import storage
from google.cloud import bigquery
from google.cloud import firestore

from agent.basemodels import *
from fastapi import FastAPI,HTTPException,status,Depends

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model = ChatOpenAI(model=model_name, temperature=0)

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
    def __init__(self, llm: BaseChatModel,
                 ):
        self._llm = llm
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
        structured_llm = self.llm.with_structured_output(InitialInput)
        prompt = f'Analyze the following case introduction and extract key information into the InitialInput structure:\n\n{init_input}'
        return await structured_llm.ainvoke(prompt)
    
    async def analyze_events(self, initial_input : InitialInput , content : str,file_id: str) -> Events:
        '''Analyzes document content to extract a list of events.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            content (str): The document content to analyze.

        Returns:
            list[Event]: A list of extracted Event objects.
        '''
        structured_llm = self.llm.with_structured_output(Events)
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{content}'
        response = await structured_llm.ainvoke(prompt)
        for event in response.events:
            event.file_id = file_id
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
        ''' Function to analyze document content and extract structured data as Attachment.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            content (str): The document content to analyze.
            file_id (str): The unique identifier for the file.
            filename (str): The name of the file.
            path (str): The storage path of the file.
            file_type (str): The MIME type of the file.
            size (int): The size of the file in bytes.
            query_id (str): The query identifier.   
            
            Returns:    
            Attachment: The structured Attachment object with extracted data.
        '''
        structured_llm = self.llm.with_structured_output(AttachmentExtracted)
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key information into the Attachment structure:\n\n{content}'
        response_events = await self.analyze_events(initial_input=initial_input, 
                                     content = content, 
                                     file_id = file_id)
        events = response_events.events
        
        response = await structured_llm.ainvoke(prompt)
        file = Attachment(**response.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in events],
                        )
        return {"file": file, "events": events}
    
    async def analyze_governing_law(self, events : list[Event],rag_content_law : str) -> GoverningLaw:
        '''Function to analyze case events and extract governing law information.
        
        Args:
            events (list[Event]): The list of case events.
            rag_content_law (str): Relevant legal context retrieved via RAG.
            
        Returns:
            GoverningLaw : The structured GoverningLaw object with extracted information.
        '''
        structured_llm = self.llm.with_structured_output(GoverningLaw)
        law_context = f'Extracted legal context:\n\n{rag_content_law}\n\n' if rag_content_law else ''
        prompt = law_context + f'Based on the following case events, analyze and extract governing law information:\n\n{events}'
        return await structured_llm.ainvoke(prompt)
        
    async def analyze_factual_facts(self, 
                              initial_input : InitialInput, 
                              events : list[Event], 
                              #claims : list[Claim], 
                              #damages: list[Damage]
                              ) -> FactualFacts:
        '''Function to analyze case events and extract disputed and undisputed facts.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            events (list[Event]): The list of case events.
        
        Returns: 
            FactualFacts : The structured FactualFacts object with disputed and undisputed facts.
        '''
        structured_llm = self.llm.with_structured_output(FactualFacts)
        init = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init + f'Based on the following case events, extract disputed and undisputed facts:\n\n{events}'
        return await structured_llm.ainvoke(prompt)
    
    # ===== FUNCTIONS FOR UPDATING EXISTING FACTSHEET =====
    async def consider_new_events(self,
                            factsheet : FactSheet,
                         new_content : str,
                         new_user_input : str,
                         file_id : str
                         ) -> list[Event]:
        structured_llm = self.llm.with_structured_output(Events)
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        init_prompt = f'Existing factsheet:\n\n{factsheet_data}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{new_content}' + f'\n\nNew user input:\n\n{new_user_input}\n\n'
        response = await structured_llm.ainvoke(prompt)
        for event in response.events:
            event.file_id = file_id
        return response.events
    
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
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        prompt = f'Existing factsheet:\n\n{factsheet_data}\n\n'
        prompt += f'Analyze the following document content and extract key information into the Attachment structure:\n\n{new_content}' + f'\n\nNew user input:\n\n{new_user_input}\n\n'

        structured_llm = self.llm.with_structured_output(AttachmentExtracted)
        response = await structured_llm.ainvoke(prompt)
        events = await self.consider_new_events(factsheet, new_content, new_user_input, file_id)
        file = Attachment(**response.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in events],
                        )
        

        return {"file": file, 
                "events": events,
        }

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
        structured_llm = self.llm.with_structured_output(RelevanceCheck)  
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

    
    async def clean(self,
                         content : Events | Claims | Damages | Deadlines,
                         ) -> Events | Claims | Damages | Deadlines:   
        '''Function to clean and deduplicate a list of events.'''
        
        structured_llm = self.llm.with_structured_output(content.__class__)
        data = content.model_dump() if hasattr(content, 'model_dump') else content
        prompt = f'Clean and deduplicate the following list of events. Remove any duplicate or irrelevant entries:\n\n{data}'
        return await structured_llm.ainvoke(prompt)
    
    async def update_content(self,factsheet : FactSheet,
                             content : InitialInput | GoverningLaw | FactualFacts
                             ) -> InitialInput | GoverningLaw | FactualFacts:
        '''Method for updating parts of the factsheet based on new content.'''
        structured_llm = self.llm.with_structured_output(content.__class__)
        factsheet_data = factsheet.model_dump() if hasattr(factsheet, 'model_dump') else factsheet
        prompt = f"Current data for {content.__class__.__name__}: {content}"+  f'Existing factsheet:\n\n{factsheet_data}\n\nUpdate the following section {content.__class__.__name__} of the factsheet'
        return await structured_llm.ainvoke(prompt)

    
    async def clean_factsheet(self,
                         factsheet : FactSheet,
                         ) -> FactSheet:
        '''Function to clean and deduplicate the entire factsheet.
        
        Args:
            factsheet (FactSheet): The factsheet to clean.
        Returns:
            FactSheet: The cleaned factsheet.
        '''
        events = await self.clean(Events(events=factsheet.timeline))
        claims = await self.clean(Claims(claims=factsheet.claims))
        damages = await self.clean(Damages(damages=factsheet.damages))
        deadlines = await self.clean(Deadlines(deadlines=factsheet.deadlines))

        factsheet = FactSheet(
            timeline=events.events,
            claims=claims.claims,
            damages=damages.damages,
            deadlines=deadlines.deadlines,
            governing_law=factsheet.governing_law,
            disputed_facts=factsheet.disputed_facts,
            undisputed_facts=factsheet.undisputed_facts,
            parties=factsheet.parties,
            third_parties=factsheet.third_parties,
            background=factsheet.background,
        )
        
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


