import os
import base64
import json
import logging
import tiktoken
from datetime import datetime
import asyncio
from typing import Dict, List, Literal, Optional, Sequence, Annotated

import pandas as pd
from dotenv import load_dotenv

from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, BaseMessage,
    ToolMessage, AIMessageChunk, message_to_dict, messages_to_dict
)
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.documents import Document
from langgraph.graph import StateGraph, END

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from agent.agent_modules import Summarizer,ContextManager, ToolManager
from database import SupabaseManager,SupabaseStorageManager, BQVectorStore, ChromaVectorStore, DocumentProcessor
from agent.basemodels import *  
from uuid_utils import uuid4

load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




class Agent:
    '''Main Agent class handling the agent operations'''
    def __init__(self,
                 tools : List[tool],
                 prompt : str,
                 checkpointer = None,
                 ):
        """
        Initializes the Agent with tools, prompt, LLMs, and checkpointer.
        Args:
            tools (List[tool]): List of tools available to the agent.
            prompt (str): The system prompt guiding the agent's behavior.
            llms (dict): Dictionary of LLMs available for the agent.
            checkpointer: Optional checkpointer for saving agent state.
        Returns:
            None

        """
        self.tools = tools
        self.prompt = prompt
        self.checkpointer = checkpointer
        self.summary = "" #rolling summary for long conversations
        self.in_memory_store = ChromaVectorStore()
        self.vs = BQVectorStore()
        self.document_processor = DocumentProcessor()
        self.summarizer = Summarizer()
        self.storage = SupabaseStorageManager() #GCSManager() 
        self.conversation_manager =  SupabaseManager() #ConversationManager()
        self.context_manager = ContextManager()
        self.tool_manager = ToolManager()
    
    # =================================
    #         GRAPH ELEMENTS
    # =================================

    def _build_attachment_context(self,
                                   attachments: list,
                                   attachment_contents: dict[str, str],
                                   user_input: str) -> str:
        """
        Builds RAG context from pre-fetched attachment contents for LLM payload.

        Args:
            attachments: List of attachment metadata
            attachment_contents: Pre-fetched content dict (file_id -> content)
            user_input: User's query (used to determine formatting)

        Returns:
            Formatted text with relevant content from attachments
        """
        if not attachments or not attachment_contents:
            return ""

        attachment_texts = []

        for att in attachments:
            file_id = att.get("file_id", "")
            filename = att.get("filename", "")
            path = att.get("path", "")
            content = attachment_contents.get(file_id, "")

            if content:
                prefix = f"--DOCUMENT: PATH {path} - FILENAME: {filename} --\n"
                attachment_texts.append(prefix + "" + content)

        if not attachment_texts:
            return ""

        combined = "\n\n".join(attachment_texts)

        if user_input:
            return f"Retrieved context from user's documents:\n\n{combined}" + "\n\nUse this information to answer the user's question."
        else:
            return f"Summary of attachment contents:\n{self.summarizer.summarize(combined)}"+ "\n\nUse this information to answer the user's question."

    async def _call_llm(self, state: AgentState, llm_with_tools: BaseChatModel,config: RunnableConfig) -> AgentState:
        """
        Calls the LLM with RAG from BigQuery Vector Store for attachments.

        Args:
            state: The current state of the agent.
            llm_with_tools: The LLM model with tools bound.

        Returns:
            AgentState: The updated state with the LLM's response.
        """
        msg = state["messages"][-1] if isinstance(state["messages"][-1], HumanMessage) else None
        query_id = msg.additional_kwargs.get("query_id", "") if msg else ""
        session_id = msg.additional_kwargs.get("session_id", "") if msg else ""
        attachments = msg.additional_kwargs.get("attachments", []) if msg else []
        user_input = msg.content if msg else ""
        project_id = config.get("configurable").get("custom_project_id",None)

        attachment_contents = {}

        # ---- FETCH ATTACHMENT CONTENTS ONCE ----
        if attachments:
            if user_input:
                docs = self.in_memory_store.query(user_input, collection_id=session_id, k=3)
            else:
                docs = self.in_memory_store.get_all(collection_id=session_id)

            for doc in docs:
                file_id = doc.metadata.get("file_id", "")
                if file_id:
                    if file_id in attachment_contents:
                        attachment_contents[file_id] += "\n" + doc.page_content
                    else:
                        attachment_contents[file_id] = doc.page_content


        # ---- PROCESS ATTACHMENTS: Update factsheet ----
        project_data = self.conversation_manager.load_project(project_id = project_id) if project_id else None
                                                           


        # ---- BUILD ATTACHMENT CONTEXT FOR LLM ----
        attachment_context = self._build_attachment_context(
            attachments=attachments,
            attachment_contents=attachment_contents,
            user_input=user_input
        )

        # ---- BUILD PAYLOAD ----
        payload = [SystemMessage(content=self.prompt)]

        # Add factsheet context
        if project_data and project_data.get("factsheet"):
            factsheet_message = HumanMessage(
                content="Here is the current FactSheet for the case: " + json.dumps(project_data.get("factsheet").model_dump(mode="json"))
            )
            payload.append(factsheet_message)

        # ---- LONG CONVERSATION HANDLING ----
        sum_rate = 8
        messages = state["messages"][1:]  # All messages except SystemMessage

        if len(state["messages"]) > sum_rate:
            if len(messages) % sum_rate == 0:
                msgs_to_sum = ["Previous summary: " + self.summary] if self.summary else []
                msgs_to_sum.extend(messages[-sum_rate - 1:])
                self.summary = self.summarizer.summarize(msgs_to_sum)

            if self.summary:
                payload.append(AIMessage(content=self.summary))
            payload.extend(self.context_manager.truncate_messages(messages, max_messages=sum_rate))
        else:
            payload.extend(messages)

        # ---- ENHANCE LAST MESSAGE WITH ATTACHMENTS ----
        enhanced_msg = None
        if attachment_context and payload and isinstance(payload[-1], HumanMessage):
            enhanced_msg = HumanMessage(
                content=f"{attachment_context}\n\nUser query: {payload[-1].content}",
                id=payload[-1].id,  # Same ID = will replace in state
                additional_kwargs=msg.additional_kwargs if msg else {}
            )
            payload[-1] = enhanced_msg  # For LLM

        # === DEBUG LOGGING ===
        logger.debug(f"--- Payload Messages for query id {config.get("configurable").get("query_id", "")} (session_id {session_id} and project-id {config.get("configurable").get("custom_project_id", "")}) ---")
        for m in payload:
            content_preview = str(m.content)[:100] if m.content else ""
            logger.debug(f"{m.type}: {content_preview}")

        try:
            message = await llm_with_tools.ainvoke(payload)
            # Return enhanced_msg to save full context in state (with same ID to replace)
            messages_to_return = [enhanced_msg, message] if enhanced_msg else [message]
            return {
                "messages": messages_to_return,
                "factsheet": project_data.get("factsheet") if project_data else None,
                "attachments": project_data.get("attachments") if project_data else None
            }
        except Exception as e:
            logger.error(f"Error invoking LLM: {e}", exc_info=True)
            raise e
    
    async def _call_tool(self,state: AgentState,query_id : str) -> AgentState:
        """Executes tool calls from the LLM's response"""

        if not isinstance(state["messages"][-1], AIMessage):
            raise TypeError(f'The last message is not an AI message and has not attr "tool_calls"')
                

        tool_calls = state["messages"][-1].tool_calls
        tools_dict = {our_tool.name: our_tool for our_tool in self.tools}
        results = []
        tool_data_results = []
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        DATA_PROD_TOOLS = ["run_query", "company_info","get_org_num","display_data_on_ui"]
        TOKEN_LIMIT = 1000
        

        if not tool_calls:
            logger.debug(f'No tool calls found')
            return {"messages": []}

        for tool in tool_calls:
            name = tool.get("name", "")
            args = tool.get("args", "")
            tool_id = tool.get("id","")
            logger.debug(f'Calling Tool: {name} with query: {args}')

            if name in tools_dict:
                # ---- CALL TOOL ----
                tool_to_call = tools_dict[name]
                try:
                    #result = tool_to_call.invoke(input_to_tool)
                    result = await tool_to_call.ainvoke(args)
                except Exception as e:
                    result = f'Something went wrong when calling tool {name} with args {args} : {e}.'
                    logger.error(result, exc_info=True)
                
                n_tokens = len(enc.encode(str(result)))
                logger.debug(f'Result length: {n_tokens}')

                # ---- PROCESS DATA PRODUCTION TOOLS ----
                if name in DATA_PROD_TOOLS:
                    raw_tool_data = {
                        "tool_name": name,
                        "tool_args": args,
                        "tool_data": result,
                        "n_tokens": n_tokens,
                        "timestamp": pd.Timestamp.now().isoformat(),
                        "tool_call_id": tool["id"],
                        "query_id": query_id,
                    }                
                    tool_data_results.append(raw_tool_data)

                # ---- HANDLE LONG TOOL RESULTS FOR LLM MEMORY ----
                if n_tokens > TOKEN_LIMIT:
                    formatted_result = "Executive summary of the tool result: " + self.summarizer.summarize(str(result), limit=TOKEN_LIMIT)
                else:
                    formatted_result = self.tool_manager.format_tool_result(result)
                results.append(ToolMessage(tool_call_id=tool_id, name=name, content=str(formatted_result)))

            else:
                logger.warning(f'{tool["name"]} does not exists in tools. \nTools available: {tools_dict.keys()}')
                result = "Incorrect Tool Name, Please Retry and Select tool from list of avaible tools"
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(result)))

        logger.debug(f'Tools execution complete')
        return {"messages": results,
                "tool_results": tool_data_results}
    
    def _should_continue(self,state: AgentState) -> bool:
        """Determine if we should continue or end the conversation"""
        result = state["messages"][-1]
        return hasattr(result, "tool_calls") and len(result.tool_calls) > 0

    def _compile_agent(self,llm_model : str ,query_id : str,):
        """
        Compiles the agent graph with the selected LLM.
        """

        logger.info(f"USER INPUT COMPILE AGENT: Model name : {llm_model}")
        llm_provider, model_name = llm_model.split("_")
        if llm_provider == "google":
            selected_llm = ChatGoogleGenerativeAI(project = project_id , model=model_name)
        elif llm_provider == "openai":
            selected_llm = ChatOpenAI(model=model_name)
        else:
            logger.warning(f"No valid llm provider selected, defaulting to Google Gemini.")
            selected_llm = ChatGoogleGenerativeAI(project = project_id , model="gemini-2.5-flash")

        if not selected_llm:
            raise ValueError(f'Invalid model name: {model_name}.')

        llm = selected_llm.bind_tools(self.tools)

        async def call_llm_node(state, config : RunnableConfig):
            return await self._call_llm(state, llm_with_tools=llm, config=config)

        async def call_tool_node(state):
            return await self._call_tool(state, query_id=query_id)

        graph = StateGraph(AgentState)
        graph.add_node("call_llm", call_llm_node)
        graph.add_node("call_tool", call_tool_node)
        graph.set_entry_point("call_llm")
        graph.add_edge("call_tool", "call_llm")
        graph.add_conditional_edges("call_llm",
                                    self._should_continue,
                                    {
                                        True: "call_tool",
                                        False: END
                                    })
        agent = graph.compile(checkpointer=self.checkpointer)
        return agent

    # =================================
    #         HELPERS
    # ================================
    async def load_or_create_conversation(self, agent_instance, thread: dict, session_id: str): 
        try:
            current_state = await agent_instance.aget_state(thread)
            is_new_conv = not current_state.values.get("messages", [])
        except Exception:
            is_new_conv = True

        if is_new_conv: #load system prompt
            logger.info(f'Creating new conversation. Thread: {thread}. Choosing type of question...')
            system_message = SystemMessage(content=self.prompt)
            await agent_instance.aupdate_state(thread, {"messages": [system_message], 
                                                        "factsheet": None, #FYLL INN HER!
                                                        "tool_results": []})
        else:
            logger.info(f'Continuing conversation (thread: {session_id})')

    def _load_msg_as_document(self, msg):
        msg = msg.copy()
        type_ = msg.pop("type")
        msg_data = msg.get("data", {})
        cont = msg_data.pop("content", "")
        
        # Start med type
        meta = {"type": type_}
        
        # Legg til bare enkle verdier fra msg_data
        for key, value in msg_data.items():
            if isinstance(value, (str, int, float, bool, type(None))):
                meta[key] = value
        
        doc = Document(page_content=cont, metadata=meta)
        return doc

    def _load_messages_as_document(self, messages : list[dict]) -> list[Document]:
        docs = []
        for msg in messages:
            doc = self._load_msg_as_document(msg)
            docs.append(doc)
        return docs

    # =================================
    #       STREAM RESPONSE
    # =================================

    async def stream_response(self, query : AskAgentRequest,
                                user_id : str
                             ):
        """
        This is a generator function that yields status updates and the final response.
        """
        
        
        # =================================
        #               SETUP
        # ================================
        
        thread = {"configurable":
                      {"thread_id": query.session_id,
                       "user_id": user_id,
                       "custom_project_id": query.project_id}
                  }
        agent_instance = self._compile_agent(llm_model=query.llm_model, query_id=query.query_id)
        
        # NEW OR EXISTING CONVERSATION
        await self.load_or_create_conversation(agent_instance, thread, query.session_id)
                                                            
        #HANDLE USER QUERY
        events = []
        event_counter = 0
        token_stream = ""

        # SAVE ATTACHMENTS to both vector store and file storage
        if query.attachments:
            docs = []
            for att in query.attachments:
                docs.extend(self.document_processor.process_attachment(
                    content = att.content, 
                    file_id=att.file_id, 
                    file_type=att.file_type, 
                    session_id=query.session_id))
            # Store (same API regardless of implementation)
            self.in_memory_store.add_documents(docs, collection_id=query.session_id)
            await self.storage.save_raw_documents(attachments=query.attachments)

        #add attachments without content to user message
        event_id = str(uuid4())
        attachments_events = [] #[att.model_dump(mode = "json", exclude={"content"}) for att in query.attachments or []] #rm contents
        for att in query.attachments or []:
            att_dict = att.model_dump(mode = "json", exclude={"content"})
            att_dict["event_id"] = event_id
            attachments_events.append(att_dict)
            #logger.info(f"Attachment for event: {att_dict}")

         # FIRST USER MESSAGE EVENT
        event_model = StreamEvent(data = EventData(attachments = [att.get("file_id") for att in attachments_events]), #writes back without content
                                    order = event_counter,
                                    type = "human",
                                    created_at = datetime.now(),
                                    event_id = event_id,
                                    session_id= query.session_id,
                                    content = query.question,
                                    query_id = query.query_id,
                                    langchain_id= query.query_id
                                    )
        event_counter += 1
        events.append(event_model) #add first user message event

        #=========================================
        #           STREAM RESPONSE
        #=========================================
        user_msg = HumanMessage(content=query.question, 
                                additional_kwargs={"attachments": attachments_events,
                                                   "session_id": query.session_id,
                                                   "user_id": user_id,
                                                   "query_id": query.query_id
                                                   })
        try:
            async for chunk in agent_instance.astream_events({"messages": [user_msg],
                                                                      "tool_results": [],
                                                                      }, 
                                                             config=thread):
                ev = chunk.get("event")
                data = chunk.get("data")
                name = chunk.get("name")

                #token for token streaming
                if ev == "on_chat_model_stream":
                    result = self.on_chat_model_stream(data, query_id=query.query_id, token_stream=token_stream)
                    if result:
                        token_stream += result.get("data","")
                        yield result
                        

                #ai messages
                if name == "call_llm":
                    result = self.on_call_llm(data, 
                                              query_id=query.query_id, 
                                              session_id=query.session_id, 
                                              events=events, 
                                              event_counter=event_counter, 
                                              token_stream=token_stream)
                    if result:
                        yield result
                        #token_stream  = "" #reset after yielding

                #direct tool results
                if name == "call_tool" and ev == "on_chain_end":
                    result = self.on_call_tool(data, 
                                               query_id=query.query_id, 
                                               session_id=query.session_id,
                                               events=events, 
                                               event_counter=event_counter)
                    if result:
                        yield result
        except Exception as e:
            logger.error(f"Error streaming response: {e}", exc_info=True)

        finally:
            # Save final state
            
            data_to_save = StreamData(events=events,
                                    llm_model=query.llm_model,
                                    project_id=query.project_id,
                                    last_query_id=query.query_id,
                                    attachments=[AttachmentModel.model_validate(att) for att in attachments_events or []],
                                    )
            self.conversation_manager.save_stream(data=data_to_save,
                                                  user_id=user_id,
                                                  session_id=query.session_id)
            
            

    
    def on_chat_model_stream(self, data : dict, query_id : str, token_stream : str):
        if data.get("chunk"):
            chunk = data.get("chunk")
            if isinstance(chunk,AIMessageChunk) and chunk.content:
                token_stream += chunk.content
                return {"type": "token", "data": chunk.content, "query_id": query_id}

    def on_call_llm(self, data : dict, 
                    query_id : str,
                    session_id : str,
                    events : list, 
                    event_counter : int, 
                    token_stream : str):
        
        output = data.get("output")
        if output and output.get("messages"):
            ai_msg = output.get("messages")[-1]
            if isinstance(ai_msg, AIMessage):
                event_model = StreamEvent(data = EventData(
                                                            tool_calls = ai_msg.tool_calls,
                                                            token_stream = token_stream),
                                          order = event_counter,
                                          type = "ai",
                                          created_at = datetime.now(),
                                          query_id = query_id,
                                            event_id = str(uuid4()),
                                            session_id = session_id,
                                          content = ai_msg.content,
                                          langchain_id= ai_msg.model_dump().get("id", None))
                events.append(event_model)
                event_counter += 1
                return event_model.model_dump(mode="json")

    def on_call_tool(self, data : dict, 
                     query_id : str, 
                     session_id : str, 
                     events : list, 
                     event_counter : int,):
        output = data.get("output")
        msg = output.get("messages",[])[-1] if output.get("messages",[]) else None
        tool_results = output.get("tool_results", [])
        for tool_result in tool_results:
            payload = {"type": "tool_result",
                    "tool_name": tool_result.get("tool_name"),
                    "tool_args": tool_result.get("tool_args"),
                    "data": tool_result.get("tool_data"),
                    "query_id": query_id
                    }
            
            event_model = StreamEvent.model_validate(data = ToolResultData.model_validate(payload),
                                                       order = event_counter,
                                                       type = "tool_result",
                                                       created_at = datetime.now(),
                                                       query_id = query_id,
                                                       event_id = str(uuid4()),
                                                       session_id = session_id,
                                                       langchain_id= msg.get("data").get("id", None))
            events.append(event_model)
            event_counter += 1
            return event_model.model_dump(mode="json")

    # =================================
    #       INITIAL PROJECT SCAN
    # ================================= 
    async def initialize_project(self, query : AskAgentRequest,
                                 user_id : str,
                                 ):
        '''Initial project scan to generate FactSheet from initial input and attachments'''

        events: list[Event] = []
        damages: list[Damage] = []
        claims: list[Claim] = []
        deadlines: list[Deadline] = []
        files: list[Attachment] = []

        # Parallelize storage operations and initial analysis
        storage_tasks = []
        if query.attachments:
            #logger.debug(f'======= ATTACHMENT CONTENT======= \n { query.attachments }\n')
            docs = []
            for att in query.attachments:
                docs.extend(self.document_processor.process_attachment(content=att.content, 
                                                                       file_id=att.file_id, 
                                                                       file_type=att.file_type, 
                                                                       session_id=query.session_id))
            
            # Run both storage operations in parallel
            storage_tasks = [
                asyncio.to_thread(self.vs.add_documents, docs, collection_id=query.session_id),
                self.storage.save_raw_documents(attachments=query.attachments)
            ]

        # Analyze documents in parallel
        sem = asyncio.Semaphore(20)

        async def analyze_doc_with_limit(att, initial_input_awaitable):
            # ✅ Wait for initial_input OUTSIDE semaphore to avoid blocking
            initial_input = await initial_input_awaitable
            
            # ✅ Only acquire semaphore when making LLM call
            async with sem:
                return await self.context_manager.analyze_doc(
                    initial_input, 
                    att.content,
                    file_id=att.file_id,
                    filename=att.filename,
                    path=att.path or f"{user_id}/{query.session_id}/{att.file_id}",
                    file_type=att.file_type,
                    size=att.size,
                )

        # Start initial_input analysis immediately
        initial_input_task = asyncio.create_task(
            self.context_manager.analyze_init_input(query.question)
        )

        # Start document analysis in parallel
        doc_tasks = [
            analyze_doc_with_limit(att, initial_input_task) 
            for att in query.attachments or []
        ]

        # Wait for ALL operations (storage + analysis) simultaneously
        all_results = await asyncio.gather(
            *storage_tasks,
            initial_input_task,
            *doc_tasks
        )
        
        # Extract initial_input from results (index depends on number of storage_tasks)
        storage_offset = len(storage_tasks)
        initial_input = all_results[storage_offset]
        doc_results = all_results[storage_offset + 1:]
        
        for party in initial_input.parties or []:
            party.party_id = str(uuid4())
        logger.debug(f'\n\n ====== Analyzed Initial Input: {initial_input.model_dump(mode = "json")} ========= \n\n')

        # Process document results
        if doc_results:
            for result in doc_results:
                analyzed_doc = result.get("file")
                logger.debug(f"\n\n ====== Analyzed document: {analyzed_doc.filename} (ID: {analyzed_doc.file_id}) - Result {analyzed_doc.model_dump()} ========= \n\n")

                files.append(analyzed_doc)
                if analyzed_doc.damages:
                    damages.extend(analyzed_doc.damages)
                if analyzed_doc.claims:
                    claims.extend(analyzed_doc.claims)
                if analyzed_doc.deadlines:
                    deadlines.extend(analyzed_doc.deadlines)
                if result.get("events"):
                    events.extend(result.get("events"))

        # Build RAG query from events and run in thread (sync function)
        #events_txt = " ".join([f"- {event.description} (Date: {event.event_date})" for event in events])
        rag_content_law = "No rag content" #await asyncio.to_thread(self.vs.query, query=initial_input.background, collection_id="laws", k=1)
        logger.debug(f'\n\n ====== RAG Content for Governing Law Analysis: {rag_content_law} ========= \n\n')

        # Analyze factual facts and governing law in parallel
        analysis_tasks = [
            self.context_manager.analyze_factual_facts(initial_input, events),
            self.context_manager.analyze_governing_law(events=events, rag_content_law=rag_content_law),
        ]
        analysis_results = await asyncio.gather(*analysis_tasks)

        # Initialize with defaults in case analysis fails
        factual_facts = FactualFacts(disputed_facts=[], undisputed_facts=[])
        governing_law = GoverningLaw(
            primary_jurisdiction="Unknown",
            key_areas=[],
            procedural_law="tvisteloven"
        )

        for res in analysis_results:
            if isinstance(res, FactualFacts):
                factual_facts = res
                logger.debug(f'\n\n ====== Analyzed Factual Facts: {factual_facts.model_dump(mode = "json")} ========= \n\n')
            elif isinstance(res, GoverningLaw):
                governing_law = res
                logger.debug(f'\n\n ====== Analyzed Governing Law: {governing_law.model_dump(mode = "json")} ========= \n\n')

        # Generate UUIDs for all entities before saving
        for event in events:
            if not event.event_id:
                event.event_id = str(uuid4())
        
        for damage in damages:
            if not damage.damage_id:
                damage.damage_id = str(uuid4())
        
        for claim in claims:
            if not claim.claim_id:
                claim.claim_id = str(uuid4())
        
        for deadline in deadlines:
            if not deadline.deadline_id:
                deadline.deadline_id = str(uuid4())

        result = FactSheet(
            events=events,
            damages=damages if damages else None,
            claims=claims if claims else None,
            deadlines=deadlines if deadlines else None,
            governing_law=governing_law,
            **factual_facts.model_dump(),
            **initial_input.model_dump(),
        )
        #logger.debug(f'\n\n ====== Generated FactSheet: {result} ========= \n\n')        
        self.conversation_manager.save_project(factsheet=result,
                                                 files=files,
                                                 user_id=user_id,
                                                 session_id=query.session_id,
                                                 query_id=query.query_id,
                                                 project_id=query.project_id)

        # Return a JSON-serializable dict with all metadata
        return {
            "attachments": [att.model_dump(mode='json') for att in files],
            "factsheet": result.model_dump(mode='json'),
        }


    async def update_project(self, 
                             query : AskAgentRequest,
                              user_id : str,
                             ):
        '''Update the project with new input and attachments'''

        # Validate project_data first
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )

        if project_data and not isinstance(project_data, dict):
            error_msg = f"load_project returned {type(project_data).__name__} instead of dict. Value: {project_data}"
            logger.error(f"Error in update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)

        # Save attachments to vector store and storage in parallel
        storage_tasks = []
        if query.attachments:
            docs = []
            for att in query.attachments:
                docs.extend(self.document_processor.process_attachment(content=att.content, 
                file_id=att.file_id, 
                file_type=att.file_type, 
                session_id=query.session_id))
            
            # Run both storage operations in parallel
            storage_tasks = [
                asyncio.to_thread(self.vs.add_documents, docs, collection_id=query.session_id),
                self.storage.save_raw_documents(attachments=query.attachments)
            ]

        # Extract existing data from project (use direct lists, not wrapper models)
        factsheet : FactSheet = project_data.get("factsheet", {})
        events: list[Event] = [] #factsheet.events if factsheet and factsheet.events else []
        files: list[Attachment] = [] #project_data.get("attachments", [])
        damages: list[Damage] = [] #factsheet.damages if factsheet and factsheet.damages else []
        claims: list[Claim] = [] #factsheet.claims if factsheet and factsheet.claims else []
        deadlines: list[Deadline] = [] #factsheet.deadlines if factsheet and factsheet.deadlines else []

        
        sem = asyncio.Semaphore(20)  # Increased from 5 to 20 for better parallelism
        async def analyze_new_doc_with_limit(att, factsheet,query):
            async with sem:
                return await self.context_manager.consider_new_doc(
                factsheet=factsheet,
                new_content=att.content,
                new_user_input=query.question,
                file_id=att.file_id,
                filename=att.filename,
                path=att.path,
                file_type=att.file_type,
                size=att.size,
            )

        tasks = [analyze_new_doc_with_limit(att, factsheet, query) for att in query.attachments or []]

        # Wait for storage operations and document analysis in parallel
        all_results = await asyncio.gather(*storage_tasks, *tasks)
        
        # Extract document analysis results (skip storage results)
        results = all_results[len(storage_tasks):]
        
        if results:
            for result in results:
                analyzed_doc = result.get("file")
                logger.debug(f"Analyzed document: {analyzed_doc.filename} (ID: {analyzed_doc.file_id}) - Result {analyzed_doc.model_dump()}")

                # Collect results from analyzed documents
                files.append(analyzed_doc)
                if analyzed_doc.damages:
                    damages.extend(analyzed_doc.damages)
                if analyzed_doc.claims:
                    claims.extend(analyzed_doc.claims)
                if analyzed_doc.deadlines:
                    deadlines.extend(analyzed_doc.deadlines)
                if result.get("events"):
                    events.extend(result.get("events"))

            
            storage_saving_tasks = []  # Clear storage tasks after completion
            
            storage_saving_tasks.append(self.conversation_manager.save_project_element(
                data = events,
                project_id=query.project_id,
                table_name = "project_events")) if events else None
            storage_saving_tasks.append(self.conversation_manager.save_project_element(
                data = files,
                project_id=query.project_id,
                table_name = "project_attachments")) if files else None
            storage_saving_tasks.append(self.conversation_manager.save_project_element(
                data = damages,
                project_id=query.project_id,
                table_name = "project_damages")) if damages else None
            storage_saving_tasks.append(self.conversation_manager.save_project_element(
                data = claims,
                project_id=query.project_id,
                table_name = "project_claims")) if claims else None
            storage_saving_tasks.append(self.conversation_manager.save_project_element(
                data = deadlines,
                project_id=query.project_id,
                table_name = "project_deadlines")) if deadlines else None   
            
            await asyncio.gather(*storage_saving_tasks)

        return {"events" : [event.model_dump(mode="json") for event in events],
                "attachments" : [file.model_dump(mode="json") for file in files],
                "damages" : [damage.model_dump(mode="json") for damage in damages],
                "claims" : [claim.model_dump(mode="json") for claim in claims],
                "deadlines" : [deadline.model_dump(mode="json") for deadline in deadlines],
                }
            
    
    async def cleanup_element(self,
                              query : AskAgentRequest,
                              element_type: str,
                             ):
        '''Cleanup project data if needed'''
        valid_element_types = {
            "events": Event,
            "damages": Damage,
            "claims": Claim,
            "deadlines": Deadline,
            "parties": Party,
        }
        if element_type not in list(valid_element_types.keys()):
            raise ValueError(f"Invalid element_type: {element_type}. Must be one of {', '.join(list(valid_element_types.keys()))}")
        
        # == LOAD DATA ==
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if project_data and not isinstance(project_data, dict):
            error_msg = f"load_project returned {type(project_data).__name__} instead of dict. Value: {project_data}"
            logger.error(f"Error in update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)
        
        factsheet : FactSheet = project_data.get("factsheet", {})
        content = factsheet.model_dump().get(element_type, [])
        if not content:
            return {"message" : "No content"}
        content_model = [valid_element_types[element_type].model_validate(c) for c in content] if content else []
        cleaned_element = await self.context_manager.clean_element(content = content_model,
                                                                   factsheet=factsheet,
                                                                   )
        self.conversation_manager.save_project_element(data =cleaned_element,
                                                       project_id=query.project_id,
                                                       table_name = f"project_{element_type}")
        return {
                "success": True,
                "message": f"Successfully cleaned {element_type}",
                "data": {
                    "element_type": element_type,
                    "original_count": len(content_model),
                    "cleaned_count": len(cleaned_element),
                    "removed": len(content_model) - len(cleaned_element)
                }
            }
    
    
    
    async def cleanup_factsheet(self, 
                              query : AskAgentRequest,
                              user_id : str,
                             ):
        '''Cleanup project data if needed'''
        # == LOAD DATA ==
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if project_data and not isinstance(project_data, dict):
            error_msg = f"load_project returned {type(project_data).__name__} instead of dict. Value: {project_data}"
            logger.error(f"Error in update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)
        
        factsheet : FactSheet = project_data.get("factsheet", {})
        cleaned_factsheet = await self.context_manager.clean_factsheet(factsheet)
        self.conversation_manager.save_project(factsheet=cleaned_factsheet,
                                                 files=[],
                                                 user_id=user_id,
                                                 session_id=query.session_id,
                                                 query_id=query.query_id,
                                                 project_id=query.project_id)
        return {
                "success": True,
                "message": f"Successfully cleaned factsheet",
                "data": cleaned_factsheet.model_dump(mode="json")
            }
        

