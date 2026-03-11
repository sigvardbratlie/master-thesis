import os
import base64
import json
import logging
from langchain_openai import ChatOpenAI
import tiktoken
from datetime import datetime
import asyncio

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
from .context_manager import ContextManager
from database import SupabaseManager,SupabaseStorageManager, BQVectorStore, ChromaVectorStore
from documents import DocumentProcessor, EmailHandler
from models import *  
from uuid import uuid4
from utils import AppConfig
from .pipelines import ProjectPipeline


project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)


class Agent:
    '''Main Agent class handling the agent operations'''
    def __init__(self,
                 tools : list[tool],
                 prompt : str,
                 checkpointer = None,
                 use_factsheet : bool = True,
                 embed_to_vectorstore : bool = True,
                 save_to_storage : bool = True,
                 config: AppConfig = None,
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

        self.query : AskAgentRequest | None = None

        self.config = config or AppConfig()
        self._semaphore = asyncio.Semaphore(self.config.async_tasks.max_concurrent_requests)
        logger.debug(f"⚙️  AgentConfig: max_concurrent={self.config.async_tasks.max_concurrent_requests}, throttle_value={self.config.async_tasks.throttle_value}s")
    
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

    async def _call_llm(self, state: AgentState, llm_with_tools: BaseChatModel, thread: RunnableConfig) -> AgentState:
        """
        Calls the LLM with RAG from BigQuery Vector Store for attachments.

        Args:
            state: The current state of the agent.
            llm_with_tools: The LLM model with tools bound.

        Returns:
            AgentState: The updated state with the LLM's response.
        """
        msg = state.messages[-1] if isinstance(state.messages[-1], HumanMessage) else None
        query_id = msg.additional_kwargs.get("query_id", "") if msg else ""
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
        messages = state.messages[1:]  # All messages except SystemMessage

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
            # Stream and accumulate manually to prevent Gemini 2.5 thinking-model truncation:
            # when LangGraph's astream_events wraps ainvoke, pure-text responses only store
            # the first streaming chunk in state. Using astream fixes this while still
            # forwarding all chunks (including reasoning) as on_chat_model_stream events.
            accumulated: AIMessageChunk | None = None
            async with self._semaphore:
                async for chunk in llm_with_tools.astream(payload, config=thread):
                    accumulated = chunk if accumulated is None else accumulated + chunk
                if self.config.throttle_value > 0:
                    await asyncio.sleep(self.config.throttle_value)
            if accumulated is None:
                raise ValueError("LLM returned no response chunks")

            # Extract full text from accumulated content.
            # LangChain content type is str | list[str | Dict], so after
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
        result = state.messages[-1]
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
                        base_url=self.config.models.together.base_url,
                        api_key=os.getenv("TOGETHER_API_KEY"),
                        model=model_name,
                        max_tokens=self.config.models.together.max_tokens,
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

        async def call_llm_node(state, thread: RunnableConfig):
            return await self._call_llm(state, llm_with_tools=llm, thread=thread)

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
    # def delete_project_vectorstore(self, project_id: str):
    #     """Delete project documents from BigQuery vector store."""
    #     try:
    #         self.vs.delete_project(project_id)
    #         logger.info(f"🗑️  Deleted project {project_id} from vector store")
    #         return {"success": True, "project_id": project_id}
    #     except Exception as e:
    #         logger.error(f"❌ Error deleting project {project_id} from vector store: {e}", exc_info=True)
    #         return {"success": False, "error": str(e)}
    
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
