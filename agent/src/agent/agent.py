import os
import base64
import json
import logging
from langchain_openai import ChatOpenAI
import tiktoken
from datetime import datetime
import asyncio
from typing import List, Optional

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

from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI

from .agent_modules import Summarizer, ToolManager
from .config import AgentConfig
from .context_manager import ContextManager
from database import SupabaseManager,SupabaseStorageManager, BQVectorStore, ChromaVectorStore
from documents import DocumentProcessor, EmailHandler
from models import *  
from uuid import uuid4
load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

logger = logging.getLogger(__name__)




class Agent:
    '''Main Agent class handling the agent operations'''
    def __init__(self,
                 tools : List[tool],
                 prompt : str,
                 checkpointer = None,
                 use_factsheet : bool = True,
                 embed_to_vectorstore : bool = True,
                 save_to_storage : bool = True,
                 config: AgentConfig = None,
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

        #TOGGLES
        self.use_factsheet = use_factsheet
        self.embed_to_vectorstore = embed_to_vectorstore
        self.save_to_storage = save_to_storage

        self.config = config or AgentConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        logger.debug(f"⚙️  AgentConfig: max_concurrent={self.config.max_concurrent}, throttle_value={self.config.throttle_value}s")
    
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
            for att in attachments:
                file_id = att.get("file_id", "")
                attachment_contents[file_id] = att.get("body", "")  if att.get("body", "") else "NO BODY CONTENT"

        # ---- BUILD ATTACHMENT CONTEXT FOR LLM ----
        attachment_context = self._build_attachment_context(
            attachments=attachments,
            attachment_contents=attachment_contents,
            user_input=user_input
        )

        project = self.conversation_manager.load_project(project_id=project_id,) if project_id and self.use_factsheet else None
        if project and isinstance(project, ProjectData) and isinstance(project.factsheet, FactSheet):
            #raise TypeError("THIS SHOULD BE INCLUDED")
            content = project.shorten_factsheet() + "\n\n"
            content += project.shorten_attachments(excluded_fields=["description"]) + "\n\n"
            content += project.shorten_emails(excluded_fields=["description"]) + "\n\n"
            prompt = self.prompt + "\n\n" + content
        else:
            prompt = self.prompt

        payload = [SystemMessage(content=prompt)]

        

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

        # ---- SANITIZE PAYLOAD for Gemini compatibility ----
        payload = self._sanitize_payload(payload)

        # === PAYLOAD TRACE ===
        logger.debug(f"─── LLM payload | query={config.get('configurable', {}).get('query_id', '')} session={session_id} project={config.get('configurable', {}).get('custom_project_id', '')} ───")
        for m in payload:
            content_preview = str(m.content)[:100] if m.content else ""
            logger.debug(f"  {m.type}: {content_preview}")

        try:
            # Stream and accumulate manually to prevent Gemini 2.5 thinking-model truncation:
            # when LangGraph's astream_events wraps ainvoke, pure-text responses only store
            # the first streaming chunk in state. Using astream fixes this while still
            # forwarding all chunks (including reasoning) as on_chat_model_stream events.
            accumulated: AIMessageChunk | None = None
            async with self._semaphore:
                async for chunk in llm_with_tools.astream(payload, config=config):
                    accumulated = chunk if accumulated is None else accumulated + chunk
                if self.config.throttle_value > 0:
                    await asyncio.sleep(self.config.throttle_value)
            if accumulated is None:
                raise ValueError("LLM returned no response chunks")

            # Extract full text from accumulated content.
            # LangChain content type is Union[str, List[Union[str, Dict]]], so after
            # accumulating streaming chunks the result can be any combination:
            #   - plain str (OpenAI, some Gemini chunks)
            #   - list of dicts only (Anthropic, Gemini 3.x)
            #   - mixed list of dicts + plain strings (Gemini 2.5-pro — the signature
            #     dict is followed by continuation text as a bare string)
            # Thinking blocks (type == "thinking") are excluded from the stored response.
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
    
    async def _call_tool(self,state: AgentState,query_id : str) -> AgentState:
        """Executes tool calls from the LLM's response"""

        if not isinstance(state["messages"][-1], AIMessage):
            raise TypeError(f'The last message is not an AI message and has not attr "tool_calls"')
                

        tool_calls = state["messages"][-1].tool_calls
        tools_dict = {our_tool.name: our_tool for our_tool in self.tools}
        results = []
        tool_data_results = []
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        DATA_PROD_TOOLS = []
        TOKEN_LIMIT = 10000
        

        if not tool_calls:
            logger.debug("No tool calls in message")
            return {"messages": []}

        for tool in tool_calls:
            name = tool.get("name", "")
            args = tool.get("args", "")
            tool_id = tool.get("id","")
            logger.debug(f'🔧 Calling tool: {name} | args={args}')

            if name in tools_dict:
                # ---- CALL TOOL ----
                tool_to_call = tools_dict[name]
                try:
                    #result = tool_to_call.invoke(input_to_tool)
                    result = await tool_to_call.ainvoke(args)
                except Exception as e:
                    result = f'Something went wrong when calling tool {name} with args {args} : {e}.'
                    logger.error(f"❌ {result}", exc_info=True)
                
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

                # ---- HANDLE LONG TOOL RESULTS FOR LLM MEMORY ----
                if n_tokens > TOKEN_LIMIT:
                    formatted_result = "Executive summary of the tool result: " + self.summarizer.summarize(str(result), limit=TOKEN_LIMIT)
                else:
                    formatted_result = self.tool_manager.format_tool_result(result)
                results.append(ToolMessage(tool_call_id=tool_id, name=name, content=str(formatted_result)))

            else:
                logger.warning(f'⚠️  Unknown tool: {tool["name"]} — available: {list(tools_dict.keys())}')
                result = f"Incorrect Tool Name, Please Retry and Select tool from list of avaible tools {list(tools_dict.keys())}"
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(result)))

        logger.debug('✅ Tools execution complete')
        return {"messages": results,
                "tool_results": tool_data_results}
    
    def _should_continue(self,state: AgentState) -> bool:
        """Determine if we should continue or end the conversation"""
        result = state["messages"][-1]
        return hasattr(result, "tool_calls") and len(result.tool_calls) > 0

    # Maps UI provider names to init_chat_model provider identifiers
    PROVIDER_MAP = {
        "google": "google_genai",
        "openai": "openai",
        "meta": "together",
        "qwen": "together",
        "zai" : "together",
        "anthropic": "anthropic", 
    }

    
    THINKING_KWARGS: dict[tuple[str, str], dict] = {
        ("google_genai", "flash"): {"include_thoughts": False},
        # Anthropic extended thinking — add when Claude is wired up:
        # ("anthropic", "claude"): {"thinking": {"type": "enabled", "budget_tokens": 8000}},
    }

    def _pick_llm(self, llm_model: str) -> BaseChatModel:
        """Create LLM via init_chat_model from 'provider_model' string (e.g. 'google_gemini-2.5-flash')."""
        provider_key, model_name = llm_model.split("_", 1)
        model_provider = self.PROVIDER_MAP.get(provider_key)
        if not model_provider:
            logger.warning(f"⚠️  Unknown provider '{provider_key}' — defaulting to google_genai")
            model_provider = "google_genai"
        kwargs = {}
        for (provider, name_hint), thinking_kwargs in self.THINKING_KWARGS.items():
            if model_provider == provider and name_hint in model_name:
                kwargs.update(thinking_kwargs)
                break
        logger.debug(f'🤖 LLM: provider={model_provider} model={model_name} thinking={bool(kwargs)}')
        if model_provider in ["together"]:
            is_qwen3 = "Qwen3" in model_name
            return ChatOpenAI(
                        base_url="https://api.together.xyz/v1",
                        api_key=os.getenv("TOGETHER_API_KEY"),
                        model=model_name,
                        max_tokens=4096,
                        stream_usage=False,  # Together AI doesn't support stream_options/include_usage
                        stop=["<|im_end|>", "<|endoftext|>"] if is_qwen3 else None,
                        extra_body={"enable_thinking": False} if is_qwen3 else {},
                    )

        return init_chat_model(model_name, model_provider=model_provider, **kwargs)

    def _compile_agent(self,llm_model : str ,query_id : str,):
        """
        Compiles the agent graph with the selected LLM.
        """

        logger.debug(f"🤖 Compiling agent | model={llm_model}")
        selected_llm = self._pick_llm(llm_model)

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

    def delete_project_vectorstore(self, project_id: str):
        """Delete project documents from BigQuery vector store."""
        try:
            self.vs.delete_project(project_id)
            logger.info(f"🗑️  Deleted project {project_id} from vector store")
            return {"success": True, "project_id": project_id}
        except Exception as e:
            logger.error(f"❌ Error deleting project {project_id} from vector store: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
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
            logger.info(f'💬 New conversation | thread={thread}')
            system_message = SystemMessage(content=self.prompt)
            await agent_instance.aupdate_state(thread, {"messages": [system_message], 
                                                        "factsheet": None, #FYLL INN HER!
                                                        "tool_results": []})
        else:
            logger.info(f'💬 Resuming conversation | thread={session_id}')

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
                                                       content = "",
                                                       created_at = datetime.now().isoformat(),
                                                       query_id = query_id,
                                                       event_id = str(uuid4()),
                                                       session_id = session_id,
                                                       langchain_id= msg.get("data").get("id", None))
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
        agent_instance = self._compile_agent(llm_model=query.llm_model, query_id=query.query_id)
        
        # NEW OR EXISTING CONVERSATION
        await self.load_or_create_conversation(agent_instance, thread, query.session_id)
                                                            
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
            if not self.use_factsheet and self.embed_to_vectorstore:
                self.vs.add_documents(docs, collection_id="attachments",)
            # Store (same API regardless of implementation)
            #self.in_memory_store.add_documents(docs, collection_id="attachments") #for testing with in-memory store
            if self.save_to_storage:
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
            async for chunk in agent_instance.astream_events({"messages": [user_msg],
                                                                      "tool_results": [],
                                                                      }, 
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
            

    # =================================
    #       PROJECT SCAN
    # =================================
    def _prepare_analysis_tasks(self, attachments: list[AttachmentModel],
                                user_id: str,
                                query: AskAgentRequest,
                                input_: FactSheet | InitialInput,
                                config: RunnableConfig = None,
                                ) -> list:
        """Route attachments to doc/email analysis tasks, batching emails by size/count."""

        async def analyze_docs_with_limit(attatchments: list[AttachmentModel], input_,):
            async with self._semaphore:
                result = await self.context_manager.analyze_docs(
                    input_=input_,
                    attachments=attatchments,
                    config=config,
                )
                if self.config.throttle_value > 0:
                    await asyncio.sleep(self.config.throttle_value)
                result["_source_filenames"] = [a.filename for a in attatchments]
                return result

        async def analyze_emails_with_limit(emails: list[EmailModel], input_):
            async with self._semaphore:
                result = await self.context_manager.analyze_emails(
                    input_=input_,
                    emails=emails,
                    config=config,
                )
                if self.config.throttle_value > 0:
                    await asyncio.sleep(self.config.throttle_value)
                return result

        
        doc_tasks = []
        threshold = 500 * 1024  # 500KB extracted text — sized for LLM context window
        max_attachments = 10

        eml = EmailHandler()
        email_attachments = []
        email_size_counter = 0

        doc_size_counter = 0
        doc_attachments = []

        logger.info(f"📎 Preparing analysis tasks for {len(attachments or [])} attachment(s)")

        for att in attachments or []:
            if att.file_type != "message/rfc822":
                att_size = len(att.body.encode("utf-8")) if att.body else att.size or 0
                if doc_size_counter + att_size <= threshold and len(doc_attachments) < max_attachments:
                    doc_attachments.append(att)
                    doc_size_counter += att_size
                else:
                    logger.info(f"📦 Dispatching doc batch: {len(doc_attachments)} file(s), {doc_size_counter / 1024:.1f}KB")
                    doc_tasks.append(analyze_docs_with_limit(doc_attachments, input_=input_))
                    doc_attachments = [att]
                    doc_size_counter = att_size
            elif att.file_type == "message/rfc822":
                data = eml.parse_eml_to_obj(content=base64.b64decode(att.content),
                                     user_id=user_id,
                                     query_id=query.query_id,
                                     session_id=query.session_id,
                                     file_id=att.file_id)
                email = data.get("email", [])
                current_email_attachments = data.get("attachments", [])
                if current_email_attachments:
                    logger.info(f"📎 Email '{att.filename}': {len(current_email_attachments)} nested attachment(s) → dispatching as doc batch")
                    doc_tasks.append(analyze_docs_with_limit(current_email_attachments, input_=input_))
                else:
                    logger.debug(f"📭 Email '{att.filename}': no nested attachments")

                email_size = len(att.body.encode("utf-8")) if att.body else att.size or 0
                if email_size_counter + email_size <= threshold and len(email_attachments) < max_attachments:
                    email_attachments.append(email)
                    email_size_counter += email_size
                    logger.debug(f"📧 Accumulated {len(email_attachments)} email(s) in batch ({email_size_counter / 1024:.1f}KB)")
                else:
                    logger.info(f"📦 Dispatching email batch: {len(email_attachments)} email(s), {email_size_counter / 1024:.1f}KB")
                    doc_tasks.append(analyze_emails_with_limit(email_attachments, input_))
                    email_attachments = [email]
                    email_size_counter = email_size

        if email_attachments:
            logger.info(f"📦 Dispatching final email batch: {len(email_attachments)} email(s), {email_size_counter / 1024:.1f}KB")
            doc_tasks.append(analyze_emails_with_limit(email_attachments, input_))

        if doc_attachments:
            logger.info(f"📦 Dispatching final doc batch: {len(doc_attachments)} file(s), {doc_size_counter / 1024:.1f}KB")
            doc_tasks.append(analyze_docs_with_limit(doc_attachments, input_))

        return doc_tasks

    def _parse_docs_with_progress(self, attachments: list, query_id: str, session_id: str, user_id : str, project_id : str):
        """
        Parse documents and yield progress events + return parsed results.
        Returns docs
        """
        yield {
            "type": "status",
            "phase": ["parse-documents"],
            "status": "starting",
            "data": {
                "attachments": len(attachments or [])
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query_id
        }
        
        docs = []
        completed_text_extraction = 0
        
        for att in attachments:
            yield {
                "type": "status",
                "phase": ["parse_doc"],
                "status": "starting",
                "data": {
                    "filename": att.filename,
                    "file_id": att.file_id,
                    "progress": completed_text_extraction,
                    "total": len(attachments or [])
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query_id
            }
            
            extracted_docs = self.document_processor.parse(
                content=base64.b64decode(att.content),
                file_type=att.file_type,
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
                    "embedding_model" : self.vs.embedding_model,
                }
            )
            completed_text_extraction += 1
            
            yield {
                "type": "status",
                "phase": ["parse_doc"],
                "status": "complete",
                "data": {
                    "filename": att.filename,
                    "file_id": att.file_id,
                    "progress": completed_text_extraction,
                    "total": len(attachments or [])
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query_id
            }
            
            docs.extend(extracted_docs)
            att.body = self.document_processor.to_plain_text(extracted_docs) #store parsed content in body for later use without hitting token limits in metadata
        
        yield {
            "type": "status",
            "phase": ["parse-documents"],
            "status": "completed",
            "data": {
                "attachments": len(attachments or [])
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query_id
        }
        
        # Store results in instance variable to be retrieved by caller
        self._last_parse_results = docs
    
    async def initialize_project(self, query : AskAgentRequest,
                                 user_id : str,
                                 ):
        '''Initial project scan to generate FactSheet from initial input and attachments'''
        self.context_manager.llm = self._pick_llm(query.llm_model)
        thread: RunnableConfig = {
            "configurable": {"thread_id": query.session_id, "user_id": user_id, "custom_project_id": query.project_id},
            "metadata": {"query_id": query.query_id},
        }

        events: list[Event] = []
        damages: list[Damage] = []
        claims: list[Claim] = []
        deadlines: list[Deadline] = []
        attachments: list[Attachment] = []
        emails: list[Email] = []

        # ============= PHASE 1 =================
        # Parallelize storage operations and initial analysis
        # ========================================

        
        docs = []
        if query.attachments:
            # Parse documents with streaming progress
            for event in self._parse_docs_with_progress(attachments=query.attachments,
                                                        query_id = query.query_id,
                                                        session_id=query.session_id,
                                                        project_id=query.project_id,
                                                        user_id=user_id):
                yield event
            # Retrieve parsed results from instance variable
            docs = self._last_parse_results

            # Group docs by file_id for per-file vector store saving
            docs_by_file = {}
            for doc in docs:
                fid = doc.metadata.get("file_id", "unknown")
                docs_by_file.setdefault(fid, []).append(doc)

        else:
            docs_by_file = {}

        # Total = per-file vs saves + file storage + init_input
        total_phase1 = len(docs_by_file) + (1 if query.attachments else 0) + 1
        yield {
            "type": "status",
            "phase": ["initialization"],
            "status": "starting",
            "data": {
                "total_operations": total_phase1,
                "attachments": len(query.attachments or [])
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id
        }

        # Run file storage + init_input analysis in parallel
        initial_input = InitialInput()
        parallel_tasks = [
            asyncio.create_task(self.context_manager.analyze_init_input(query.question, config=thread))
        ]
        if query.attachments and self.save_to_storage:
            parallel_tasks.append(asyncio.create_task(
                self.storage.save_raw_documents(attachments=query.attachments)
            ))

        completed_phase1 = 0
        for coro in asyncio.as_completed(parallel_tasks):
            result = await coro
            completed_phase1 += 1
            if isinstance(result, InitialInput):
                initial_input = result
                for party in initial_input.parties or []:
                    party.party_id = str(uuid4())
                logger.debug('\n\n' + "="*5 + f' Analyzed Initial Input: {str(initial_input.model_dump(mode = "json"))[:500]} ' + '='*5 + '\n\n')
                yield {
                        "type": "status",
                        "phase": ["init_input"],
                        "status": "complete",
                        "data": {
                            "parties_found": len(initial_input.parties or []),
                            "progress": completed_phase1,
                            "total": total_phase1
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
            else:
                if result is not None and not isinstance(result, bool):
                    logger.warning(f"analyze_init_input returned unexpected type {type(result)} — using empty InitialInput fallback")
                yield {
                        "type": "status",
                        "phase": ["storage"],
                        "status": "complete",
                        "data": {
                            "progress": completed_phase1,
                            "total": total_phase1,
                            "storage_type": ["file_storage"]
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
                logger.debug(f'File storage operation completed')

        # Save all docs to vector store in a single batched call
        if docs_by_file and self.embed_to_vectorstore:
            all_docs = [doc for file_docs in docs_by_file.values() for doc in file_docs]
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {
                    "file_count": len(docs_by_file),
                    "doc_count": len(all_docs),
                    "storage_type": ["vector_store"]
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
            await asyncio.to_thread(self.vs.add_documents, all_docs, collection_id="attachments")
            completed_phase1 += len(docs_by_file)
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {
                    "file_count": len(docs_by_file),
                    "doc_count": len(all_docs),
                    "progress": completed_phase1,
                    "total": total_phase1,
                    "storage_type": ["vector_store"]
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
            logger.debug(f'Vector store batch save completed: {len(all_docs)} docs across {len(docs_by_file)} files')
            
        
        # ============= PHASE 2 =================
        # Analyze documents and extract events, damages, claims, deadlines
        # ========================================
    
        doc_tasks = self._prepare_analysis_tasks(
            attachments=query.attachments,
            user_id=user_id, query=query,
            input_=initial_input,
            config=thread,
        )
        
        yield {
            "type": "status",
            "phase": ["analyze_docs", "analyze_email"],
            "status": "starting",
            "data": {"total": len(query.attachments)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id
        }
        completed = 0
        for coro in asyncio.as_completed(doc_tasks):
            result = await coro
            completed += 1
            if result:
                if isinstance(result, dict) and "attachments" in result:
                    completed += 1
                    logger.debug('\n\n' + '='*5 + f" Analyzed document: {len(result.get("attachments"))}" + '='*5 + '\n\n')

                    attachments.extend(result.get("attachments", [])) if result.get("attachments") else None
                    damages.extend(result.get("damages", [])) if result.get("damages") else None
                    claims.extend(result.get("claims", [])) if result.get("claims") else None
                    deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                    events.extend(result.get("events", [])) if result.get("events") else None

                    if result.get("attachments"):
                        filenames = [a.filename for a in result.get("attachments", []) if hasattr(a, 'filename') and a.filename]
                        yield {
                            "type": "status",
                            "phase": ["analyze_doc"],
                            "status": "complete",
                            "data": {
                                "attachment_count": len(result.get("attachments", [])),
                                "filename": ", ".join(filenames) if filenames else "",
                                "progress": completed,
                                "total": len(doc_tasks)
                            },
                            "timestamp": datetime.now().isoformat(),
                            "query_id": query.query_id
                        }
                    else:
                        source_filenames = result.get("_source_filenames", [])
                        yield {
                            "type": "status",
                            "phase": ["analyze_doc"],
                            "status": "complete",
                            "data": {
                                "filename": ", ".join(source_filenames) if source_filenames else "unknown",
                                "file_id": "no content",
                                "progress": completed,
                                "total": len(doc_tasks)
                            },
                            "timestamp": datetime.now().isoformat(),
                            "query_id": query.query_id
                        }
                elif isinstance(result, dict) and "attachment" in result:
                    # Single doc result from analyze_doc
                    att = result.get("attachment")
                    if att:
                        attachments.append(att)
                        logger.debug('\n\n' + '='*5 + f" Analyzed single document: {att.filename} (ID: {att.file_id})" + '='*5 + '\n\n')
                    damages.extend(result.get("damages", [])) if result.get("damages") else None
                    claims.extend(result.get("claims", [])) if result.get("claims") else None
                    deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                    events.extend(result.get("events", [])) if result.get("events") else None
                    completed += 1
                    yield {
                        "type": "status",
                        "phase": ["analyze_doc"],
                        "status": "complete",
                        "data": {
                            "attachment_count": 1 if att else 0,
                            "filename": att.filename if att and hasattr(att, 'filename') else "",
                            "progress": completed,
                            "total": len(doc_tasks)
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
                elif isinstance(result,dict) and "emails" in result:
                    if result.get("emails"):
                        logger.debug('\n\n' + '='*5 + f" Email analysis completed with {len(result.get('emails', []))} emails extracted. " + '='*5 + '\n\n')
                    completed += 1
                    emails.extend(result.get("emails", [])) if result.get("emails") else None
                    claims.extend(result.get("claims", [])) if result.get("claims") else None
                    deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                    damages.extend(result.get("damages", [])) if result.get("damages") else None
                    events.extend(result.get("events", [])) if result.get("events") else None
                    
                    email_subjects = [e.subject for e in result.get("emails", []) if hasattr(e, 'subject') and e.subject]
                    yield {
                        "type": "status",
                        "phase": ["analyze_email"],
                        "status": "complete",
                        "data": {
                            "email_count": len(result.get("emails", [])),
                            "subject": ", ".join(email_subjects) if email_subjects else "",
                            "progress": completed,
                            "total": len(doc_tasks)
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
        yield {
                "type": "status",
                "phase": ["analyze_docs"],
                "status": "complete",
                "data": {"total": len(doc_tasks)},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
                

        
        
        result = FactSheet(
            events=events,
            damages=damages if damages else None,
            claims=claims if claims else None,
            deadlines=deadlines if deadlines else None,
            
            **initial_input.model_dump(),
            
            
        )
        logger.debug(f"About to save project {query.project_id} to Supabase...")
        self.conversation_manager.save_project(factsheet=result,
                                                 attachments=attachments,
                                                 emails = emails,
                                                 user_id=user_id,
                                                 session_id=query.session_id,
                                                 query_id=query.query_id,
                                                 project_id=query.project_id)
        
        logger.debug(f"Project saved successfully. About to yield final result...")
        # Yield final result for consumers that need the data
        try:
            factsheet_dict = result.model_dump(mode="json")
            attachments_dict = [file.model_dump(mode="json") for file in attachments]
            emails = [email.model_dump(mode="json") for email in emails]
            logger.debug(f"Successfully serialized factsheet and attachments. Yielding result...")
            yield {
                "type": "result",
                "data": {
                    "factsheet": factsheet_dict,
                    "attachments": attachments_dict,
                    "emails" : emails
                }
            }
            logger.debug(f"Final result yielded successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to serialize/yield final result: {e}", exc_info=True)
            raise

    async def update_project(self, 
                             query : AskAgentRequest,
                              user_id : str,
                             ):
        '''Update the project with new input and attachments'''
        self.context_manager.llm = self._pick_llm(query.llm_model)
        thread: RunnableConfig = {
            "configurable": {"thread_id": query.session_id, "user_id": user_id, "custom_project_id": query.project_id},
            "metadata": {"query_id": query.query_id},
        }

        # Validate project_data first
        factsheet = await asyncio.to_thread(
            self.conversation_manager.load_factsheet,
            project_id=query.project_id
        )

        if factsheet and not isinstance(factsheet, FactSheet):
            error_msg = f"load_factsheet returned {type(factsheet).__name__} instead of FactSheet. Value: {factsheet}"
            logger.error(f"❌ update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)

        # Save attachments to vector store and storage
        docs = []
        docs_by_file = {}
        if query.attachments:
            # Parse documents with streaming progress
            for event in self._parse_docs_with_progress(attachments=query.attachments,
                                                        query_id =  query.query_id,
                                                        session_id = query.session_id,
                                                        project_id=query.project_id,
                                                        user_id=user_id):
                yield event
            # Retrieve parsed results from instance variable
            docs = self._last_parse_results

            # Group docs by file_id
            for doc in docs:
                fid = doc.metadata.get("file_id", "unknown")
                docs_by_file.setdefault(fid, []).append(doc)

        # Extract existing data from project (use direct lists, not wrapper models)
        factsheet : FactSheet = factsheet
        events: list[Event] = []
        attachments: list[Attachment] = []
        damages: list[Damage] = []
        claims: list[Claim] = []
        deadlines: list[Deadline] = []
        emails: list[Email] = []

        doc_tasks = self._prepare_analysis_tasks(
            attachments=query.attachments,
            user_id=user_id, query=query,
            input_=factsheet,
            config=thread,
        )

        # ============= PHASE 1 =================
        # Save to vector store sequentially, then file storage + doc analysis in parallel
        # ========================================
        total_storage = len(docs_by_file) + (1 if query.attachments else 0)
        total_tasks = total_storage + len(doc_tasks)
        yield {
            "type": "status",
            "phase": ["analyze_docs", "storage"],
            "status": "starting",
            "data": {"total": total_tasks},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id
        }

        # Save all docs to vector store in a single batched call
        completed_saving_storage = 0
        if docs_by_file and self.embed_to_vectorstore:
            all_docs = [doc for file_docs in docs_by_file.values() for doc in file_docs]
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {"file_count": len(docs_by_file), "doc_count": len(all_docs), "storage_type": ["vector_store"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
            await asyncio.to_thread(self.vs.add_documents, all_docs, collection_id="attachments")
            completed_saving_storage += len(docs_by_file)
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {
                    "file_count": len(docs_by_file),
                    "doc_count": len(all_docs),
                    "progress": completed_saving_storage,
                    "total": total_storage,
                    "storage_type": ["vector_store"]
                },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
            logger.debug(f'Vector store batch save completed: {len(all_docs)} docs across {len(docs_by_file)} files')

        # File storage + doc analysis in parallel
        file_storage_tasks = []
        if query.attachments and self.save_to_storage:
            file_storage_tasks.append(self.storage.save_raw_documents(attachments=query.attachments))

        completed_analyze_doc = 0
        for coro in asyncio.as_completed(file_storage_tasks + doc_tasks):
            result = await coro

            # File storage result (returns None or non-dict)
            if result is None or (not isinstance(result, dict)):
                completed_saving_storage += 1
                yield {
                    "type": "status",
                    "phase": ["storage"],
                    "status": "complete",
                    "data": {
                        "progress": completed_saving_storage,
                        "total": total_storage,
                        "storage_type": ["file_storage"]
                    },
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id
                }
                continue

            if isinstance(result, dict) and "attachments" in result and "events" in result:
                logger.debug("\n\n" + "="*5 + f"Analyzed document: {len(result.get("attachments"))}\n\n")
                # Collect results from analyzed documents
                attachments.extend(result.get("attachments", [])) if result.get("attachments") else None
                damages.extend(result.get("damages", [])) if result.get("damages") else None
                claims.extend(result.get("claims", [])) if result.get("claims") else None
                deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                events.extend(result.get("events", [])) if result.get("events") else None

                filenames = [a.filename for a in result.get("attachments", []) if hasattr(a, 'filename') and a.filename]
                completed_analyze_doc += 1
                yield {
                    "type": "status",
                    "phase": ["analyze_doc"],
                    "status": "complete",
                    "data": {
                        "attachment_count": len(result.get("attachments", [])),
                        "filename": ", ".join(filenames) if filenames else "",
                        "progress": completed_analyze_doc,
                        "total": len(doc_tasks)
                    },
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id
                }
            elif result and isinstance(result, dict) and "attachment" in result:
                # Single doc result from analyze_doc
                att = result.get("attachment")
                if att:
                    attachments.append(att)
                    logger.debug("\n\n" + "="*5 + f"Analyzed single document: {att.filename} (ID: {att.file_id})" + "="*5 + "\n\n")
                damages.extend(result.get("damages", [])) if result.get("damages") else None
                claims.extend(result.get("claims", [])) if result.get("claims") else None
                deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                events.extend(result.get("events", [])) if result.get("events") else None

                completed_analyze_doc += 1
                yield {
                    "type": "status",
                    "phase": ["analyze_doc"],
                    "status": "complete",
                    "data": {
                        "attachment_count": 1 if att else 0,
                        "filename": att.filename if att and hasattr(att, 'filename') else "",
                        "progress": completed_analyze_doc,
                        "total": len(doc_tasks)
                    },
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id
                }
            elif result and isinstance(result, dict) and "emails" in result:
                if result.get("emails"):
                    logger.debug(f'\n\n ======= Email analysis completed with {len(result.get("emails", []))} emails extracted. ========')
                completed_analyze_doc += 1
                emails.extend(result.get("emails", [])) if result.get("emails") else None
                claims.extend(result.get("claims", [])) if result.get("claims") else None
                deadlines.extend(result.get("deadlines", [])) if result.get("deadlines") else None
                damages.extend(result.get("damages", [])) if result.get("damages") else None
                events.extend(result.get("events", [])) if result.get("events") else None
                email_subjects = [e.subject for e in result.get("emails", []) if hasattr(e, 'subject') and e.subject]
                yield {
                    "type": "status",
                    "phase": ["analyze_email"],
                    "status": "complete",
                    "data": {
                        "email_count": len(result.get("emails", [])),
                        "subject": ", ".join(email_subjects) if email_subjects else "",
                        "progress": completed_analyze_doc,
                        "total": len(doc_tasks)
                    },
                    "timestamp": datetime.now().isoformat(),
                    "query_id": query.query_id
                }
        yield {
            "type": "status",
            "phase": ["analyze_docs"],
            "status": "complete",
            "data": {"total": len(doc_tasks)},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id
        }
        
        # ============= PHASE 2 =================
        # Insert new documents to database (must be inserted first to avoid foreign key constraint issues)
        # ========================================
        if attachments and hasattr(attachments[0], "model_dump"):
            await asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data = [file.model_dump(mode="json", exclude = {"claims","damages","deadlines","events"}) for file in attachments],
                project_id=query.project_id,
                table_name = "project_attachments")
            yield {
                        "type": "status",
                        "phase": ["storage"],
                        "status": "complete",
                        "data": {"total" : len(attachments),
                                 "storage_type" : ["database"]
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
        else:
            logger.warning("No valid files to save or missing model_dump method.")

        if emails:
            if not hasattr(emails[0], "model_dump"):
                logger.critical("Email objects are missing model_dump method. Emails will not be saved to database.")

            await asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data=[email.model_dump(mode="json", exclude={"events", "claims", "damages", "deadlines"}) for email in emails],
                project_id=query.project_id,
                table_name="project_emails"
            )

        # ============= PHASE 3 =================
        # Insert new data to database
        # ========================================
        related_tasks = []
        if events and hasattr(events[0], "model_dump"):
            related_tasks.append(asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data = [event.model_dump(mode="json") for event in events],
                project_id=query.project_id,
                table_name = "project_events"))
        else:
            logger.warning("No valid events to save or missing model_dump method.")
        if damages and hasattr(damages[0], "model_dump"):
            related_tasks.append(asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data = [damage.model_dump(mode="json") for damage in damages],
                project_id=query.project_id,
                table_name = "project_damages"))
        else:
            logger.warning("No valid damages to save or missing model_dump method.")
        if claims and hasattr(claims[0], "model_dump"):
            related_tasks.append(asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data = [claim.model_dump(mode="json") for claim in claims],
                project_id=query.project_id,
                table_name = "project_claims"))
        else:
            logger.warning("No valid claims to save or missing model_dump method.")
        if deadlines and hasattr(deadlines[0], "model_dump"):
            related_tasks.append(asyncio.to_thread(
                self.conversation_manager.insert_project_element,
                data = [deadline.model_dump(mode="json") for deadline in deadlines],
                project_id=query.project_id,
                table_name = "project_deadlines"))
        else:
            logger.warning("No valid deadlines to save or missing model_dump method.")

        
        
        if related_tasks:
            completed = 0
            yield {
            "type": "status",
            "phase": ["storage"],
            "status": "starting",
            "data": {"total_operations": len(related_tasks),},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id
        }
            for coro in asyncio.as_completed(related_tasks):
                await coro
                completed += 1
                yield {
                        "type": "status",
                        "phase": ["storage"],
                        "status": "complete",
                        "data": {
                            "progress": completed,
                            "total": len(related_tasks),
                            "storage_type" : ["database"]
                        },
                        "timestamp": datetime.now().isoformat(),
                        "query_id": query.query_id
                    }
                
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {"total_operations": len(related_tasks),},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
        
        # Yield final result for consumers that need the data
        yield {
            "type": "result",
            "data": {
                "events": [event.model_dump(mode="json") for event in events] if events else [],
                "attachments": [file.model_dump(mode="json") for file in attachments] if attachments else [],
                "damages": [damage.model_dump(mode="json") for damage in damages] if damages else [],
                "claims": [claim.model_dump(mode="json") for claim in claims] if claims else [],
                "deadlines": [deadline.model_dump(mode="json") for deadline in deadlines] if deadlines else [],
                "emails": [email.model_dump(mode="json") for email in emails] if emails else []
            }
        }

    async def update_project_from_session(self,
                                        query : AskAgentRequest,
                                        user_id : str,
                                        ):
        '''Update the project with new input and attachments, using session data as context'''
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
        async for event in self.update_project(updated_query, user_id):
            yield event
        
    
    async def cleanup_element(self,
                              query : AskAgentRequest,
                              element_type: str,
                             ):
        '''Cleanup project data if needed'''
        self.context_manager.llm = self._pick_llm(query.llm_model)

        valid_element_types = {
            "events": Events,
            "damages": Damages,
            "claims": Claims,
            "deadlines": Deadlines,
            "parties": Parties,
        }
        if element_type not in list(valid_element_types.keys()):
            raise ValueError(f"Invalid element_type: {element_type}. Must be one of {', '.join(list(valid_element_types.keys()))}")
        
        # == LOAD DATA ==
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if project_data and not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData. Value: {project_data}"
            logger.error(f"Error in update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)

        factsheet = project_data.factsheet

        content = project_data.factsheet.model_dump().get(element_type, []) if factsheet else []

        #content_model = [valid_element_types[element_type].model_validate(c) for c in content] if content else []
        content_model = valid_element_types[element_type].model_validate({element_type : content}) if content else None
        yield {"type": "status",
               "phase" : [f"cleanup_{element_type}"],
               "status": "starting",
               "data": {
                   "element_type": element_type,
                   "original_count": len(getattr(content_model, element_type)) if content_model else 0,
               },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
               }
        cleaned_element = await self.context_manager.clean_element(content = content_model,
                                                                   element_type=element_type,
                                                                   project_data=project_data
                                                                   )
        
        yield {"type": "status",
               "phase" : [f"cleanup_{element_type}"],
               "status": "complete",
               "data": {    
                     "element_type": element_type,
                     "original_count": len(getattr(content_model, element_type)) if content_model else 0,
                     "cleaned_count": len(cleaned_element) if cleaned_element else 0,
                     "removed": (len(getattr(content_model, element_type)) if content_model else 0) - (len(cleaned_element) if cleaned_element else 0)
                },
                 "timestamp": datetime.now().isoformat(),
                 "query_id": query.query_id
                }
        
        yield {"type": "status",
               "phase" : [f"storage"],
                "status": "starting",
                "data": {
                    "element_type": element_type,
                    "cleaned_count": len(cleaned_element) if cleaned_element else 0,
                    "storage_type" : ["database"]
                },
                 "timestamp": datetime.now().isoformat(),
                 "query_id": query.query_id
                }
        self.conversation_manager.replace_project_element(data =cleaned_element,
                                                       project_id=query.project_id,
                                                       table_name = f"project_{element_type}")
        yield {"type": "status",
               "phase" : [f"storage"],
                "status": "complete",
                "data": {
                    "element_type": element_type,
                    "cleaned_count": len(cleaned_element) if cleaned_element else 0,
                    "storage_type" : ["database"]
                },
                 "timestamp": datetime.now().isoformat(),
                 "query_id": query.query_id
                }
        
        # Yield final result for consumers that need the data
        yield {
            "type": "result",
            "data": {
                "success": True,
                "element_type": element_type,
                "cleaned_count": len(cleaned_element) if cleaned_element else 0
            }
        }
    
    
    async def cleanup_attr(self,
                              query : AskAgentRequest,
                              element_type: str,
                                ):
        '''Cleanup simple text attribute in factsheet (e.g. case title)'''
        self.context_manager.llm = self._pick_llm(query.llm_model)
        valid_element_types = ["title", "background",
                               #"disputed_facts","undisputed_facts","governing_law",
                               ]
        if element_type not in valid_element_types:
            raise ValueError(f"Invalid element_type: {element_type}. Must be one of {', '.join(valid_element_types)}")
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        
        if project_data and not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData. Value: {project_data}"
            logger.error(f"Error in update_project: {error_msg}", exc_info=True)
            raise TypeError(error_msg)
        factsheet = project_data.factsheet
        attachments = project_data.attachments
        emails = project_data.emails
        content = getattr(factsheet, element_type, "")
        yield {"type": "status",
               "phase" : [f"cleanup_{element_type}"],
               "status": "starting",
               "data": {
                   "element_type": element_type,
                   "original_content": content,
               },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
               }
        if element_type in ["title", "background"]:
            cleaned_content = await self.context_manager.clean_metadata(content=content, 
                                                                        element_type=element_type,
                                                                        project_data=project_data
                                                                        )
        else:
            logger.warning(f"Element type {element_type} is not configured for metadata cleaning. Returning original content.")
            cleaned_content = content
            # cleaned_content = await self.context_manager.clean_legal_attr(content=content, 
            #                                                               factsheet=factsheet, 
            #                                                                 attachments=attachments,
            #                                                                 emails=emails,
            #                                                               element_type=element_type)
        logger.debug(f"======== Cleaned content for {element_type}: {cleaned_content} ========\n")
        yield {"type": "status",
               "phase" : [f"cleanup_{element_type}"],
               "status": "complete",
               "data": {
                   "element_type": element_type,
                   "original_content": content,
                   "cleaned_content": cleaned_content
               },
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
               }
        if element_type in ["title", "background"]:
            self.conversation_manager.upsert_project(cleaned_content, 
                                                     element_type=element_type,
                                                     project_id=query.project_id)
        else:
            logger.warning(f"Element type {element_type} is not configured for legal attribute upsert. Skipping database update.")
            # self.conversation_manager.upsert_project_custom(data = cleaned_content, 
            #                                                 element_type= element_type,
            #                                                 project_id=query.project_id, 
            #                                                 table_name = f"project_legal")
        yield {"type": "status",
               "phase" : [f"storage"],
                "status": "complete",
                "data": {
                    "element_type": element_type,
                    "cleaned_content": cleaned_content,
                    "storage_type" : ["database"]
                },
                 "timestamp": datetime.now().isoformat(),
                 "query_id": query.query_id
                }

    async def cleanup_all_metadata(self, query: AskAgentRequest):
        '''Clean title and background metadata fields together.'''
        self.context_manager.llm = self._pick_llm(query.llm_model)
        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if project_data and not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData."
            logger.error(error_msg)
            raise TypeError(error_msg)

        yield {
            "type": "status",
            "phase": ["cleanup_metadata"],
            "status": "starting",
            "data": {"element_type": "metadata"},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }
        result = await self.context_manager.clean_all_metadata(project_data=project_data)
        yield {
            "type": "status",
            "phase": ["cleanup_metadata"],
            "status": "complete",
            "data": {"title": result.get("title"), "background": result.get("background")},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }
        yield {
            "type": "status",
            "phase": ["storage"],
            "status": "starting",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }
        self.conversation_manager.upsert_project(result["title"], element_type="title", project_id=query.project_id)
        self.conversation_manager.upsert_project(result["background"], element_type="background", project_id=query.project_id)
        yield {
            "type": "status",
            "phase": ["storage"],
            "status": "complete",
            "data": {"element_type": "metadata", "storage_type": ["database"]},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }
        yield {"type": "result", "data": {"success": True, "element_types": ["title", "background"]}}

    async def cleanup_elements(self, query: CleanupElementsRequest):
        '''Clean multiple relational element types in a single LLM call.'''
        self.context_manager.llm = self._pick_llm(query.llm_model)
        valid_element_types = {"events", "damages", "claims", "deadlines", "parties"}
        element_types = query.element_types
        invalid = [e for e in element_types if e not in valid_element_types]
        if invalid:
            raise ValueError(f"Invalid element_types: {invalid}. Must be subset of {sorted(valid_element_types)}")

        project_data = await asyncio.to_thread(
            self.conversation_manager.load_project,
            project_id=query.project_id
        )
        if project_data and not isinstance(project_data, ProjectData):
            error_msg = f"load_project returned {type(project_data).__name__} instead of ProjectData."
            logger.error(error_msg)
            raise TypeError(error_msg)

        original_counts = {
            et: len(project_data.factsheet.model_dump().get(et, []))
            for et in element_types
        }

        yield {
            "type": "status",
            "phase": ["cleanup_elements"],
            "status": "starting",
            "data": {"element_types": element_types, "original_counts": original_counts},
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }

        # Single LLM call for all element types
        results = await self.context_manager.clean_elements(element_types, project_data)

        yield {
            "type": "status",
            "phase": ["cleanup_elements"],
            "status": "complete",
            "data": {
                "element_types": element_types,
                "cleaned_counts": {et: len(items) for et, items in results.items()},
                "removed": {et: original_counts[et] - len(items) for et, items in results.items()},
            },
            "timestamp": datetime.now().isoformat(),
            "query_id": query.query_id,
        }

        # Save each element type to DB
        for et, cleaned in results.items():
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "starting",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            }
            self.conversation_manager.replace_project_element(
                data=cleaned,
                project_id=query.project_id,
                table_name=f"project_{et}",
            )
            yield {
                "type": "status",
                "phase": ["storage"],
                "status": "complete",
                "data": {"element_type": et, "cleaned_count": len(cleaned), "storage_type": ["database"]},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id,
            }

        yield {"type": "result", "data": {"success": True, "element_types": element_types}}

    async def extract_legal(self, query : AskAgentRequest) :
        
        initial_input = "" #to be read in from supabase
        events = []  #to be read in from supabase
        thread: RunnableConfig = {
            "configurable": {"thread_id": query.session_id, "user_id": query.user_id, "custom_project_id": query.project_id},
            "metadata": {"query_id": query.query_id},
        }
        factual_facts = {}
        governing_law = {}
        
        do_analysis_tasks = False
        if do_analysis_tasks:
            # Analyze factual facts and governing law in parallel
            # Build RAG query from events and run in thread (sync function)
            rag_content_law = await asyncio.to_thread(self.vs.query, query=initial_input.background, collection_id="laws", k=5)
            logger.debug('\n\n' + '='*5 + f" RAG Content for Governing Law Analysis: {rag_content_law} " + '='*5 + '\n\n')

            analysis_tasks = [
                self.context_manager.analyze_factual_facts(initial_input, events, config=thread),
                self.context_manager.analyze_governing_law(events=events, rag_content_law=rag_content_law, config=thread),
            ]
            
            # ============= PHASE 3 =================
            # Analyse factual facts and governing law
            # ========================================
            yield {
                "type": "status",
                "phase": ["final_analysis"],
                "status": "starting",
                "data": {"total_operations": 2},
                "timestamp": datetime.now().isoformat(),
                "query_id": query.query_id
            }
            
            
            completed_analysis = 0
            for coro in asyncio.as_completed(analysis_tasks):
                result = await coro
                completed_analysis += 1
                if result:
                    if isinstance(result, FactualFacts):
                        factual_facts = result
                        logger.debug('\n\n' + '='*5 + f" Analyzed Factual Facts: {str(factual_facts.model_dump(mode = "json"))[:500]} " + '='*5 + '\n\n')
                        yield {
                            "type": "status",
                            "phase": ["factual_facts"],
                            "status": "complete",
                            "data": {
                                "progress": completed_analysis,
                                "total": 2,
                                "disputed_count": len(factual_facts.disputed_facts or []),
                                "undisputed_count": len(factual_facts.undisputed_facts or [])
                            },
                            "timestamp": datetime.now().isoformat(),
                            "query_id": query.query_id
                        }
                    elif isinstance(result, GoverningLaw):
                        governing_law = result
                        logger.debug('\n\n' + '='*5 + f" Analyzed Governing Law: {str(governing_law.model_dump(mode = "json"))[:500]} " + '='*5 + '\n\n')
                        yield {
                                "type": "status",
                                "phase": ["governing_law"],
                                "status": "complete",
                                "data": {
                                    "progress": completed_analysis,
                                    "total": 2,
                                    "jurisdiction": governing_law.primary_jurisdiction
                                },
                                "timestamp": datetime.now().isoformat(),
                                "query_id": query.query_id
                            }
