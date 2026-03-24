import os
import json
import base64
import logging
import tiktoken
from datetime import datetime
import asyncio
from langgraph.config import get_stream_writer, get_config

import pandas as pd

from langchain_core.messages import (
    HumanMessage, AIMessage, SystemMessage, BaseMessage,
    ToolMessage, AIMessageChunk, message_to_dict, messages_to_dict
)
from langchain_core.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, END, START

from .agent_modules import Summarizer, ToolManager
from .context_manager import ContextManager
from database import SupabaseManager,SupabaseStorageManager, BQVectorStore, ChromaVectorStore, GCSManager
from documents import DocumentProcessor, EmailHandler
from models import *  
from uuid import uuid4
from utils import AppConfig
from .utils import pick_llm

project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)


class Agent:
    '''Main Agent class handling the agent operations'''
    def __init__(self,
                 tools : list[tool],
                 checkpointer = None,
                 config: AppConfig = None,
                 llm : BaseChatModel = None,
                 ):
        """
        Initializes the Agent with tools, prompt, LLMs, and checkpointer.
        Args:
            tools (list[tool]): List of tools available to the agent.
            prompt (str): The system prompt guiding the agent's behavior.
            llms (dict): Dictionary of LLMs available for the agent.
            checkpointer: Optional checkpointer for saving agent state.
        Returns:
            None

        """
        self.config = config or AppConfig()
        self._semaphore = asyncio.Semaphore(self.config.async_tasks.max_concurrent_requests)
        logger.debug(f"⚙️  AgentConfig: max_concurrent={self.config.async_tasks.max_concurrent_requests}, throttle_value={self.config.async_tasks.throttle_value}s")
        
        self.tools = tools
        self.checkpointer = checkpointer
        self.summary = "" #rolling summary for long conversations
        self.in_memory_store = ChromaVectorStore()
        self.vs = BQVectorStore(**self.config.vectorstore.bigquery.model_dump())
        self.document_processor = DocumentProcessor(config=self.config)
        self.summarizer = Summarizer()
        self.storage = GCSManager(config=self.config)  #SupabaseStorageManager(config=self.config) #
        self.conversation_manager =  SupabaseManager() #ConversationManager()
        self.context_manager = ContextManager()
        self.tool_manager = ToolManager()

        self.llm  = llm
        self._tool_cache: dict[str, dict[str, str]] = {}  # session_id -> {cache_key -> result}

        

        self.prompt = self.load_prompt(self.config.agent.prompt_file_path)
    
    
    def load_prompt(self, path: str) -> str:
        """Loads the system prompt from a file."""
        try:
            with open(path, "r") as f:
                prompt = f.read()
            logger.debug(f"✅ Loaded system prompt from {path}")
            return prompt
        except Exception as e:
            logger.error(f"❌ Failed to load system prompt from {path}: {e}")
            raise FileNotFoundError()
    
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

        return f"User's documents:\n\n{combined}" + "\n\nUse this information to answer the user's question."

    def _sanitize_payload(self, payload: list[BaseMessage]) -> list[BaseMessage]:
        """Sanitize message payload for Gemini compatibility.

        Ensures:
        1. No consecutive messages of same role (user/model)
        2. Every AIMessage with tool_calls is followed by ToolMessage(s)
        3. AI content is string, not list (avoids Gemini splitting turns)
        """
        if not payload:
            return payload

        sanitized = []
        for i, msg in enumerate(payload):
            # Always keep SystemMessage at the start
            if isinstance(msg, SystemMessage):
                sanitized.append(msg)
                continue

            # Drop empty AI messages with no tool calls — they confuse open-source models
            if isinstance(msg, AIMessage):
                has_content = bool(msg.content) if isinstance(msg.content, str) else bool(msg.content)
                has_tool_calls = bool(getattr(msg, 'tool_calls', None))
                if not has_content and not has_tool_calls:
                    logger.debug("🧹 Dropping empty AIMessage from payload")
                    continue

            # Normalize AI message content from list to string
            if isinstance(msg, AIMessage) and isinstance(msg.content, list):
                text = "".join(
                    block.get("text", "") for block in msg.content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
                msg = AIMessage(
                    content=text,
                    tool_calls=msg.tool_calls if hasattr(msg, 'tool_calls') else [],
                    id=msg.id,
                    additional_kwargs=msg.additional_kwargs,
                )

            # Merge consecutive HumanMessages
            if isinstance(msg, HumanMessage) and sanitized and isinstance(sanitized[-1], HumanMessage):
                prev = sanitized[-1]
                merged = HumanMessage(
                    content=f"{prev.content}\n\n{msg.content}",
                    id=msg.id,
                    additional_kwargs=msg.additional_kwargs,
                )
                sanitized[-1] = merged
                continue

            # Remove orphan AIMessage with tool_calls (no ToolMessage follows)
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                has_tool_response = False
                for j in range(i + 1, len(payload)):
                    if isinstance(payload[j], ToolMessage):
                        has_tool_response = True
                        break
                    if isinstance(payload[j], (HumanMessage, AIMessage)):
                        break
                if not has_tool_response:
                    # Strip tool_calls, keep as regular AI message
                    msg = AIMessage(content=msg.content or "I attempted to use a tool but couldn't complete the action.", id=msg.id)

            # Skip AI message if previous non-system message is also AI (avoid consecutive model turns)
            if isinstance(msg, AIMessage) and sanitized:
                last_non_system = next((m for m in reversed(sanitized) if not isinstance(m, SystemMessage)), None)
                if isinstance(last_non_system, AIMessage):
                    # Merge with previous AI message
                    prev_content = last_non_system.content or ""
                    new_content = msg.content or ""
                    merged = AIMessage(
                        content=f"{prev_content}\n\n{new_content}",
                        tool_calls=msg.tool_calls if hasattr(msg, 'tool_calls') and msg.tool_calls else [],
                        id=msg.id,
                    )
                    # Replace the previous AI message
                    for k in range(len(sanitized) - 1, -1, -1):
                        if isinstance(sanitized[k], AIMessage):
                            sanitized[k] = merged
                            break
                    continue

            sanitized.append(msg)

        return sanitized

    async def _call_llm(self, state: AgentState,):
        """
        Calls the LLM with RAG from BigQuery Vector Store for attachments.

        Args:
            state: The current state of the agent.
            llm_with_tools: The LLM model with tools bound.

        Returns:
            AgentState: The updated state with the LLM's response.
        """
        thread = get_config()
        #writer = get_stream_writer()
        llm_with_tools = self.llm

        msg = state.messages[-1] if isinstance(state.messages[-1], HumanMessage) else None
        #query_id = msg.additional_kwargs.get("query_id", "") if msg else ""
        session_id = msg.additional_kwargs.get("session_id", "") if msg else ""
        attachments = msg.additional_kwargs.get("attachments", []) if msg else []
        user_input = msg.content if msg else ""
        project_id = thread.get("configurable").get("custom_project_id", None)

        attachment_contents = {}

        # ---- FETCH ATTACHMENT CONTENTS ONCE ----
        if attachments:
            for att in attachments:
                file_id = att.get("file_id", "")
                attachment_contents[file_id] = att.get("body", "")  if att.get("body", "") else "NO BODY CONTENT"

        # ---- BUILD ATTACHMENT CONTEXT FOR LLM ----
        attachment_context = self._build_attachment_context(
            attachments=attachments,
            attachment_contents=attachment_contents,
            user_input=user_input
        )

        project = self.conversation_manager.load_project(project_id=project_id,) if project_id and self.config.agent.use_factsheet else None
        if project and isinstance(project, ProjectData) and isinstance(project.factsheet, FactSheet):
            if self.config.agent.minimal_context:
                inclued_fields=["title", 
                                "background",
                                ]
                significance = self.config.agent.significance
            content = project.shorten_project(excluded_keys=["description"], significance=significance, inclued_fields=inclued_fields)
            prompt = self.prompt + "\n\n" + content
        else:
            prompt = self.prompt

        payload = [SystemMessage(content=prompt)]

        

        # ---- LONG CONVERSATION HANDLING ----
        sum_rate = self.config.agent.sum_rate
        messages = [m for m in state.messages if not isinstance(m, SystemMessage)]

        if len(state.messages) > sum_rate:
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

        # ---- SANITIZE PAYLOAD for Gemini compatibility ----
        payload = self._sanitize_payload(payload)

        # === PAYLOAD TRACE ===
        logger.debug(f"─── LLM payload | query={thread.get('configurable', {}).get('query_id', '')} session={session_id} project={thread.get('configurable', {}).get('custom_project_id', '')} ───")
        for m in payload:
            content_preview = str(m.content)[:100] if m.content else ""
            logger.debug(f"  {m.type}: {content_preview}")

        try:
            accumulated: AIMessageChunk | None = None
            async with self._semaphore:
                async for chunk in llm_with_tools.astream(payload, config=thread):
                    accumulated = chunk if accumulated is None else accumulated + chunk
                if self.config.async_tasks.throttle_value > 0:
                    await asyncio.sleep(self.config.async_tasks.throttle_value)
            if accumulated is None:
                raise ValueError("LLM returned no response chunks")


            if isinstance(accumulated.content, list):
                parts = []
                for block in accumulated.content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") != "thinking":
                        parts.append(block.get("text", ""))
                full_text = "".join(parts)
            else:
                full_text = accumulated.content or ""

            message = AIMessage(
                content=full_text,
                tool_calls=accumulated.tool_calls if accumulated.tool_calls else [],
                id=accumulated.id,
                response_metadata=getattr(accumulated, "response_metadata", {}),
                usage_metadata=getattr(accumulated, "usage_metadata", None),
            )
            # Return enhanced_msg to save full context in state (with same ID to replace)
            messages_to_return = [enhanced_msg, message] if enhanced_msg else [message]
            return {
                "messages": messages_to_return,
            }
        except Exception as e:
            logger.error(f"❌ LLM invocation failed: {e}", exc_info=True)
            raise e
    
    async def _call_tool(self,state: AgentState,):
        """Executes tool calls from the LLM's response"""

        thread = get_config()
        query_id = thread.get("metadata", {}).get("query_id")
        session_id = thread.get("configurable", {}).get("thread_id", "")

        if not isinstance(state.messages[-1], AIMessage):
            raise TypeError(f'The last message is not an AI message and has not attr "tool_calls"')

        tool_calls = state.messages[-1].tool_calls
        tools_dict = {our_tool.name: our_tool for our_tool in self.tools}
        results = []
        tool_data_results = []
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        DATA_PROD_TOOLS = []
        TOKEN_LIMIT = self.config.agent.max_token_tool


        if not tool_calls:
            logger.debug("No tool calls in message")
            return {"messages": []}

        for tool in tool_calls:
            name = tool.get("name", "")
            args = tool.get("args", "")
            tool_id = tool.get("id","")
            logger.debug(f'🔧 Calling tool: {name} | args={args}')

            if name in tools_dict:
                tool_to_call = tools_dict[name]
                session_cache = self._tool_cache.setdefault(session_id, {})

                cache_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                if cache_key in session_cache:
                    logger.debug(f'💾 Cache hit — skipping tool call: {name}')
                    formatted_result = f"[Already retrieved this session — refer to the earlier {name} result in this conversation.]"
                else:
                    try:
                        result = await tool_to_call.ainvoke(args)
                    except Exception as e:
                        logger.exception(f"❌ Tool '{name}' failed (args={args})")
                        result = f'Something went wrong when calling tool {name}: {e}.'
                    session_cache[cache_key] = result

                    n_tokens = len(enc.encode(str(result)))
                    logger.debug(f'Result: {n_tokens} tokens')

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

                    if TOKEN_LIMIT and n_tokens > TOKEN_LIMIT:
                        formatted_result = "Executive summary of the tool result: " + self.summarizer.summarize(str(result), limit=TOKEN_LIMIT)
                    else:
                        formatted_result = self.tool_manager.format_tool_result(result)

                results.append(ToolMessage(tool_call_id=tool_id, name=name, content=str(formatted_result)))

            else:
                logger.warning(f'⚠️  Unknown tool: {tool["name"]} — available: {list(tools_dict.keys())}')
                result = f"Incorrect Tool Name, Please Retry and Select tool from list of avaible tools {list(tools_dict.keys())}"
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(result)))

        logger.debug('✅ Tools execution complete')
        if tool_data_results:
            writer = get_stream_writer()
            writer({"type": "tool_data", "results": tool_data_results, "query_id": query_id})
        return {"messages": results}
    
    def _should_continue(self,state: AgentState) -> bool:
        """Determine if we should continue or end the conversation"""
        result = state.messages[-1]
        return hasattr(result, "tool_calls") and len(result.tool_calls) > 0

    def _init_node(self, state: AgentState):
        if not state.messages:                                                                                                                                                                            
            logger.info("💬 New conversation — injecting system prompt")                                                                                                                                
            return {"messages": [SystemMessage(content=self.prompt)]}
        logger.info("💬 Resuming conversation")
        return {}

    def _compile_agent(self,llm_model : str):
        """
        Compiles the agent graph with the selected LLM.
        """
        logger.info(f'\n\n ================ COMPILING LLM PIPELINE ================ \n\n')
        logger.debug(f"🤖 Compiling agent | model={llm_model}")
        selected_llm = pick_llm(llm_model, config=self.config,)
        self.llm = selected_llm.bind_tools(self.tools)

        graph = StateGraph(AgentState)
        graph.add_node("init", self._init_node)
        graph.add_node("call_llm", self._call_llm)
        graph.add_node("call_tool", self._call_tool)


        graph.add_edge(START, "init")
        graph.add_edge("init", "call_llm")
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

    # =================================
    #       STREAM RESPONSE
    # =================================

    def on_chat_model_stream(self, data: dict, query_id: str, token_stream: str) -> list[dict]:
        results = []
        if data.get("chunk"):
            chunk = data.get("chunk")
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                if isinstance(chunk.content, list):
                    text_parts = []
                    reasoning_parts = []
                    for block in chunk.content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict):
                            if block.get("type") == "thinking":
                                reasoning_parts.append(block.get("thinking", ""))
                            elif block.get("type") != "thinking":
                                text_parts.append(block.get("text", ""))
                    text_content = "".join(text_parts)
                    reasoning_content = "".join(reasoning_parts)
                    if text_content:
                        results.append({"type": "token", "data": text_content, "query_id": query_id})
                    if reasoning_content:
                        results.append({"type": "reasoning", "data": reasoning_content, "query_id": query_id})
                elif isinstance(chunk.content, str):
                    results.append({"type": "token", "data": chunk.content, "query_id": query_id})
                else:
                    logger.warning(f"⚠️  Unexpected content type in AIMessageChunk: {type(chunk.content)}")
        return results

    def on_call_llm(self, data : dict,
                    query_id : str,
                    session_id : str,
                    events : list,
                    event_counter : int,
                    token_stream : str,
                    reasoning_stream: str = ""):
        
        output = data.get("output")
        if output and output.get("messages"):
            ai_msg = output.get("messages")[-1]
            if isinstance(ai_msg, AIMessage):
                # Prefer manually accumulated token_stream over ai_msg.content,
                # as some LLM providers (e.g. Gemini) may return incomplete content
                # in the on_chain_end event when streaming.
                if token_stream:
                    content_str = token_stream
                elif isinstance(ai_msg.content, list):
                    content_str = "".join(
                        block.get("text", "")
                        for block in ai_msg.content
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                else:
                    content_str = ai_msg.content
                
                event_model = StreamEvent(data = EventData(
                                                            tool_calls = ai_msg.tool_calls,
                                                            token_stream = token_stream,
                                                            reasoning_stream = reasoning_stream or None),
                                          order = event_counter,
                                          type = "ai",
                                          created_at = datetime.now().isoformat(),
                                          query_id = query_id,
                                            event_id = str(uuid4()),
                                            session_id = session_id,
                                          content = content_str,
                                          langchain_id= ai_msg.model_dump().get("id", None))
                events.append(event_model)
                event_counter += 1
                return event_model.model_dump(mode="json")

    def on_call_tool(self, data : dict,
                     query_id : str,
                     session_id : str,
                     events : list,
                     event_counter : int,):
        tool_results = data.get("results", [])
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
                                                       content = "",
                                                       created_at = datetime.now().isoformat(),
                                                       query_id = query_id,
                                                       event_id = str(uuid4()),
                                                       session_id = session_id,
                                                       langchain_id= None)
            events.append(event_model)
            event_counter += 1
            return event_model.model_dump(mode="json")

    async def stream_response(self, query : AskAgentRequest,
                                user_id : str
                             ):
        """
        This is a generator function that yields status updates and the final response.
        """

        # =================================
        #               SETUP
        # ================================
        
        thread = {
            "configurable": {
                "thread_id": query.session_id,
                "user_id": user_id,
                "custom_project_id": query.project_id,
            },
            "metadata": {"query_id": query.query_id},
        }
        agent_instance = self._compile_agent(llm_model=query.llm_model)
                                                            
        #HANDLE USER QUERY
        events = []
        token_stream = ""
        reasoning_stream = ""

        # Get current max order from existing events to continue sequentially
        try:
            existing = self.conversation_manager.supabase.table("session_events")\
                .select("order")\
                .eq("session_id", query.session_id)\
                .order("order", desc=True)\
                .limit(1)\
                .execute()
            event_counter = (existing.data[0]["order"] + 1) if existing.data else 0
        except Exception:
            event_counter = 0

        # SAVE ATTACHMENTS to both vector store and file storage
        if query.attachments:
            docs = []
            for att in query.attachments:
                extracted_docs = self.document_processor.parse(
                    content=base64.b64decode(att.content),
                    metadata={"file_id": att.file_id,
                              "filename": att.filename,
                              "user_id": user_id,
                              "query_id": query.query_id,
                              "path": att.path,
                              "file_type": att.file_type,
                              "size": att.size,
                              "session_id": query.session_id,
                              "project_id": query.project_id,
                              "embedding_model" : self.in_memory_store.embedding_model,
                              },
                    file_type=att.file_type)
                docs.extend(extracted_docs)
                att.body = self.document_processor.to_plain_text(extracted_docs)
            if not self.config.agent.use_factsheet and self.config.agent.embed_to_vectorstore:
                self.vs.add_documents(docs, collection_id="attachments",)
            # Store (same API regardless of implementation)
            #self.in_memory_store.add_documents(docs, collection_id="attachments") #for testing with in-memory store
            if self.config.agent.save_to_storage:
                await self.storage.save_raw_documents(attachments=query.attachments)

        #add attachments without content to user message
        event_id = str(uuid4())
        attachments_events = [] 
        for att in query.attachments or []:
            att_dict = att.model_dump(mode = "json", exclude={"content"})
            att_dict["event_id"] = event_id
            attachments_events.append(att_dict)

         # FIRST USER MESSAGE EVENT
        event_model = StreamEvent(data = EventData(attachments = [att.get("path") for att in attachments_events]), #writes back without content
                                    order = event_counter,
                                    type = "human",
                                    created_at = datetime.now().isoformat(),
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
        llm_question = f"{query.focus_context}\n\n{query.question}" if query.focus_context else query.question
        user_msg = HumanMessage(content=llm_question,
                                additional_kwargs={"attachments": attachments_events,
                                                   "session_id": query.session_id,
                                                   "user_id": user_id,
                                                   "query_id": query.query_id
                                                   })
        try:
            async for chunk in agent_instance.astream_events({"messages": [user_msg]},
                                                             config=thread):
                ev = chunk.get("event")
                data = chunk.get("data")
                name = chunk.get("name")

                #token for token streaming
                if ev == "on_chat_model_stream":
                    for result in self.on_chat_model_stream(data, query_id=query.query_id, token_stream=token_stream):
                        if result.get("type") == "token":
                            token_stream += result.get("data", "")
                        elif result.get("type") == "reasoning":
                            reasoning_stream += result.get("data", "")
                        yield result

                #ai messages
                if name == "call_llm":
                    result = self.on_call_llm(data,
                                              query_id=query.query_id,
                                              session_id=query.session_id,
                                              events=events,
                                              event_counter=event_counter,
                                              token_stream=token_stream,
                                              reasoning_stream=reasoning_stream)
                    if result:
                        yield result
                        token_stream = ""
                        reasoning_stream = ""
                #direct tool results (written via get_stream_writer, bypasses checkpointer)
                if ev == "on_custom_event" and isinstance(data, dict) and data.get("type") == "tool_data":
                    result = self.on_call_tool(data,
                                               query_id=query.query_id,
                                               session_id=query.session_id,
                                               events=events,
                                               event_counter=event_counter)
                    if result:
                        yield result
        except Exception as e:
            logger.error(f"❌ Stream error: {e}", exc_info=True)

        finally:
            # Save final state
            
            data_to_save = StreamData(events=events,
                                    llm_model=query.llm_model,
                                    project_id=query.project_id,
                                    last_query_id=query.query_id,
                                    attachments=attachments_events,
                                    )
            self.conversation_manager.save_stream(data=data_to_save,
                                                  user_id=user_id,
                                                  session_id=query.session_id)
            