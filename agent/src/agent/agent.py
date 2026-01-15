import os
import base64
import json
import logging
import tiktoken
from datetime import datetime
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

from agent.agent_modules import Summarizer,ContextManager, ToolManager
from database import VectorSearch,AttachmentReader, ConversationManager
from agent.basemodels import FactSheet,AgentState

load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




class Agent:
    '''Main Agent class handling the agent operations'''
    def __init__(self,
                 tools : List[tool],
                 prompt : str,
                 llms : dict,
                 checkpointer = None,
                 agent_type : Literal["fast","expert"] = "fast",
                 llm_provider : Literal["google","openai","claude"] = "google",):
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
        self.llms = llms
        self.llm = llms.get(llm_provider, llms["google"]).get(agent_type, llms["google"]["fast"])

        self.vs = VectorSearch()
        self.summarizer = Summarizer()
        self.attachment_reader = AttachmentReader()
        self.conversation_manager =  ConversationManager()
        self.context_manager = ContextManager(llm = self.llm)
        self.tool_manager = ToolManager()
    
    # =================================
    #         GRAPH ELEMENTS
    # =================================

    def _fetch_attachment_contents(self,
                                    attachments: list,
                                    user_input: str,
                                    session_id: str,
                                    query_id: str) -> dict[str, str]:
        """
        Fetches content for all attachments from vector store (single retrieval).

        Args:
            attachments: List of attachment metadata
            user_input: User's query for RAG retrieval
            session_id: Session ID
            query_id: Query ID

        Returns:
            Dict mapping file_id to content string
        """
        if not attachments:
            return {}

        contents = {}
        try:
            for att in attachments:
                file_id = att.get("file_id", "")

                if user_input:
                    content = self.vs.retrieve_relevant_attachments(query=user_input, query_id=query_id)
                else:
                    content = self.vs.retrieve_txt_content(
                        table="attachments",
                        conditions={"file_id": file_id, "session_id": session_id}
                    )
                    content = " ".join(content) if isinstance(content, list) else content

                contents[file_id] = content if content else ""

        except Exception as e:
            logger.error(f"Error fetching attachment contents: {e}", exc_info=True)

        return contents

    async def _process_attachments_for_update(self,
                                               project_data: dict,
                                               attachments: list,
                                               attachment_contents: dict[str, str],
                                               user_input: str) -> tuple[AgentState, list]:
        """
        Updates factsheet based on new attachments.

        Args:
            state: Current agent state
            attachments: List of attachment metadata
            attachment_contents: Pre-fetched content dict (file_id -> content)
            user_input: User's query

        Returns:
            Tuple of (updated state, list of new files)
        """

        new_files = []
        factsheet = project_data.get("factsheet", {})

        for att in attachments:
            file_id = att.get("file_id", "")
            content = attachment_contents.get(file_id, "")

            try:
                result = await self.context_manager.analyze_new_input(
                    factsheet=factsheet,
                    new_user_input=user_input,
                    new_content=content,
                    file_id=file_id,
                    filename=att.get("filename", ""),
                    path=att.get("path", ""),
                    file_type=att.get("file_type", ""),
                    size=att.get("size", 0),
                )

                if result:
                    # Extend timeline with new events
                    if result.get("events"):
                        events_list = result["events"].events if hasattr(result["events"], "events") else result["events"]
                        for event in events_list:
                            factsheet["timeline"].append(event.model_dump() if hasattr(event, "model_dump") else event)

                    # Extend damages
                    if result.get("damage"):
                        for damage in result["damage"]:
                            factsheet.setdefault("damages", []).append(
                                damage.model_dump() if hasattr(damage, "model_dump") else damage
                            )

                    # Extend deadlines
                    if result.get("deadline"):
                        for deadline in result["deadline"]:
                            factsheet.setdefault("deadlines", []).append(
                                deadline.model_dump() if hasattr(deadline, "model_dump") else deadline
                            )

                    # Extend claims
                    if result.get("claim"):
                        for claim in result["claim"]:
                            factsheet.setdefault("claims", []).append(
                                claim.model_dump() if hasattr(claim, "model_dump") else claim
                            )

                    # Track new file
                    if result.get("file"):
                        new_files.append(result["file"])

            except Exception as e:
                logger.error(f"Error processing attachment {file_id}: {e}", exc_info=True)

        project_data["factsheet"] = factsheet
        return project_data, new_files

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
            content = attachment_contents.get(file_id, "")

            if content:
                prefix = f"-- FILE: {filename} (ID: {file_id}) --\n"
                attachment_texts.append(prefix + content)

        if not attachment_texts:
            return ""

        combined = "\n\n".join(attachment_texts)

        if user_input:
            return f"Relevant content from attachments based on query:\n{combined}"
        else:
            return f"Summary of attachments:\n{self.summarizer.summarize(combined)}"

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

        new_files = []
        attachment_contents = {}

        # ---- FETCH ATTACHMENT CONTENTS ONCE ----
        if attachments:
            attachment_contents = self._fetch_attachment_contents(
                attachments=attachments,
                user_input=user_input,
                session_id=session_id,
                query_id=query_id
            )

        # ---- PROCESS ATTACHMENTS: Update factsheet ----
        project_data = self.conversation_manager.load_project(user_id = config.get("configurable").get("user_id",None) or "",
                                                           project_id = config.get("configurable").get("custom_project_id",None) or "",)
        if attachments and project_data:
            project_data, new_files = await self._process_attachments_for_update(
                project_data=project_data,
                attachments=attachments,
                attachment_contents=attachment_contents,
                user_input=user_input
            )

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
                content="Here is the current FactSheet for the case: " + json.dumps(project_data["factsheet"])
            )
            payload.append(factsheet_message)

        # ---- LONG CONVERSATION HANDLING ----
        sum_rate = 8
        messages = state["messages"][1:-1] + [msg] if msg else state["messages"][1:]

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

        # ---- ADD ATTACHMENT CONTEXT TO USER MESSAGE ----
        if attachment_context and msg:
            msg = HumanMessage(content=[
                {"type": "text", "text": f"Attachment context:\n{attachment_context}"},
                {"type": "text", "text": f"User query: {user_input}"}
            ])
            # Replace last message in payload with enhanced message
            if payload and isinstance(payload[-1], HumanMessage):
                payload[-1] = msg

        config_dict = config.configurable if config and hasattr(config, "configurable") else {}
        logger.info(f"--- Payload Messages for query id {query_id} (session_id {session_id} and project-id {config_dict.get('custom_project_id', '')}) ---")
        for m in payload:
            content_preview = str(m.content)[:100] if m.content else ""
            logger.info(f"{m.type}: {content_preview}")

        try:
            message = await llm_with_tools.ainvoke(payload)
            return {
                "messages": [message],
                "factsheet": project_data.get("factsheet"),
                "attachments": [f.model_dump() for f in new_files] if new_files else []
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
            logger.info(f'Calling Tool: {name} with query: {args}')

            if name in tools_dict:
                # ---- CALL TOOL ----
                tool_to_call = tools_dict[name]
                try:
                    #result = tool_to_call.invoke(input_to_tool)
                    result = await tool_to_call.ainvoke(args)
                except Exception as e:
                    result = f'Something went wrong when calling tool {name} with args {args} : {e}.'
                    logger.info(result)
                
                n_tokens = len(enc.encode(str(result)))
                logger.info(f'Result length: {n_tokens}')

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
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(formatted_result)))

            else:
                logger.info(f'{tool["name"]} does not exists in tools. \nTools available: {tools_dict.keys()}')
                result = "Incorrect Tool Name, Please Retry and Select tool from list of avaible tools"
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(result)))

        logger.debug(f'Tools execution complete')
        return {"messages": results,
                "tool_results": tool_data_results}
    
    def _should_continue(self,state: AgentState) -> bool:
        """Determine if we should continue or end the conversation"""
        result = state["messages"][-1]
        return hasattr(result, "tool_calls") and len(result.tool_calls) > 0

    def _compile_agent(self,llm_provider : Literal["google","openai","claude"], agent_type : Literal["fast","expert"],query_id : str,):
        """
        Compiles the agent graph with the selected LLM.
        Args:
            agent_type (Literal["fast", "expert"]): The type of agent to compile.
        """

        logger.info(f"USER INPUT COMPILE AGENT: Agent type : {agent_type} | LLM PROVIDER : {llm_provider}")

        if not isinstance(agent_type, str):
            raise TypeError(f'Expecting str, but got {type(agent_type)} for agent_type')

        if not isinstance(llm_provider, str):
            raise TypeError(f'Expecting str, but got {type(llm_provider)} for llm_provider')

        llm_dict = self.llms.get(llm_provider,{})

        if not llm_dict:
            raise ValueError(
                f'No selected llm dictionary for {llm_provider}. Valid choices are {list(self.llms.keys())}')

        selected_llm = llm_dict.get(agent_type, None)

        if not selected_llm:
            raise ValueError(f'Invalid agent type: {agent_type}. Expecting "fast" or "expert"')
        logger.info(f'Running agent with llm supplier {llm_provider} and type {agent_type}')


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

    def handle_attachments(self, att, session_id: str, user_id: str, query_id : str):
            '''Function to handle attachment processing, saving to vector store and file storage.
            
            Args:
                att (dict): Attachment dictionary containing file information and content.
                session_id (str): The session ID for the current conversation.
                user_id (str): The user ID of the person uploading the attachment.
                query_id (str): The query ID for tracking the request.
            Returns:
                str: Concatenated string of processed document contents from the attachment.
            '''
            
            vs_attachments = self.vs.init_vector_store(table_name="attachments")
            file_id = att.get("file_id", "")

            # Metadata
            meta = {
                "filename": att.get("filename", ""),
                "file_id": file_id,
                "user_id": user_id,
                "session_id": session_id,
                'query_id': query_id,
                "source_type": att.get("file_type", ""),  # 'application/pdf' eller 'text/plain'
                "uploaded_at": datetime.now().isoformat(),
            }
            content = att.get("content", "") #b64 or human readable text

            #decode content
            if att.get("file_type") == "application/pdf":
                content_bytes = base64.b64decode(content)
                docs = self.vs.parse_pdf(content_bytes, metadata=meta)
                self.attachment_reader.save_attachment(content_bytes, metadata=meta)
            else:
                docs = self.vs.parse_txt(content, metadata=meta)
                self.attachment_reader.save_attachment(content, metadata=meta)

            # VECTOR STORE
            vs_attachments.add_documents(docs) # Save in vector store
            att.pop("content", None) #remove content after processing

            return " ".join([doc.page_content for doc in docs])

    # =================================
    #       STREAM RESPONSE
    # =================================
    async def stream_response(self, user_input: str, 
                              attachments: list[dict],
                              session_id: str, 
                              user_id: str,
                              agent_type: Literal["fast", "expert"],
                              llm_provider: Literal["google", "openai", "claude"],
                                query_id : str,
                              project_id: Optional[str] = None,
                             ):
        """
        This is a generator function that yields status updates and the final response.
        """
        
        
        # =================================
        #               SETUP
        # ================================
        thread = {"configurable":
                      {"thread_id": session_id,
                       "user_id": user_id,
                       "custom_project_id": project_id}
                  }
        agent_instance = self._compile_agent(agent_type=agent_type, llm_provider=llm_provider, query_id=query_id)
        
        # NEW OR EXISTING CONVERSATION
        await self.load_or_create_conversation(agent_instance, thread, session_id)
        # if project_id:
        #     project_data = self.conversation_manager.load_project(user_id=user_id,
        #                                                         project_id=project_id,)

                                                            
        
        #HANDLE USER QUERY
        events = []
        event_counter = 0
        token_stream = ""

        user_msg = message_to_dict(HumanMessage(content=user_input, id = query_id))
        
        if attachments:
            for att in attachments:
                self.handle_attachments(att, session_id=session_id, user_id=user_id,query_id=query_id)
                #att.pop("content", None) #remove content if still present

        
        #[att.pop("content", None) for att in attachments] if attachments else None
        #add attachments without content to user message
        user_msg["data"]["attachments"] = attachments if attachments else []
        event = {
                "order": event_counter,
                "type": "message",
                **user_msg,
                "timestamp": datetime.now().isoformat(),
                "query_id": query_id
            }
        event_counter += 1
        events.append(event) #add first user message event

        #=========================================
        #           STREAM RESPONSE
        #=========================================
        user_msg = HumanMessage(content=user_input, 
                                #id = query_id, 
                                additional_kwargs={"attachments": attachments if attachments else [],
                                                   "session_id": session_id,
                                                   "user_id": user_id,
                                                   "query_id": query_id
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
                    result = self.on_chat_model_stream(data, query_id=query_id, token_stream=token_stream)
                    if result:
                        token_stream += result.get("data","")
                        yield result
                        

                #ai messages
                if name == "call_llm":
                    result = self.on_call_llm(data, query_id=query_id, events=events, event_counter=event_counter, token_stream=token_stream)
                    if result:
                        yield result
                        #token_stream  = "" #reset after yielding

                #direct tool results
                if name == "call_tool" and ev == "on_chain_end":
                    result = self.on_call_tool(data, query_id=query_id, events=events, event_counter=event_counter)
                    if result:
                        yield result
        except Exception as e:
            logger.error(f"Error streaming response: {e}", exc_info=True)

        finally:
            # Save final state
            self.conversation_manager.save_stream(events, 
                                                  attachments=attachments, 
                                                  user_id=user_id, 
                                                  session_id=session_id, 
                                                  agent_type=agent_type, 
                                                  project_id=project_id,
                                                  llm_provider=llm_provider,
                                                  query_id=query_id)
            if project_id:
                state_snapshot = await agent_instance.aget_state(thread)
                state_values = state_snapshot.values if state_snapshot else {}
                factsheet = state_values.get("factsheet")
                files = state_values.get("attachments", [])

                if factsheet:
                    self.conversation_manager.update_factsheet(
                        factsheet=factsheet,
                        files=files,
                        user_id=user_id,
                        session_id=session_id,
                        agent_type=agent_type,
                        llm_provider=llm_provider,
                        query_id=query_id,
                        project_id=project_id
                    )
            

    
    def on_chat_model_stream(self, data : dict, query_id : str, token_stream : str):
        if data.get("chunk"):
            chunk = data.get("chunk")
            if isinstance(chunk,AIMessageChunk) and chunk.content:
                token_stream += chunk.content
                return {"type": "token", "data": chunk.content, "query_id": query_id}

    def on_call_llm(self, data : dict, query_id : str,events : list, event_counter : int, token_stream : str):
        chunk = data.get("chunk")
        if chunk and isinstance(chunk,dict) and chunk.get("messages"):
            ai_msg = data.get("chunk").get("messages")[-1]
            if isinstance(ai_msg, AIMessage):
                msg_payload = messages_to_dict([ai_msg])[0] if messages_to_dict([ai_msg]) and len(messages_to_dict([ai_msg])) > 0 else {}
                if msg_payload.get("data"):
                    msg_payload.get("data")["token_stream"] = token_stream
                else:
                    msg_payload["token_stream"] = token_stream
                event = {
                    "order": event_counter,
                    **msg_payload,
                    "query_id": query_id,
                    "timestamp": datetime.now().isoformat()
                }
                #token_stream = ""
                events.append(event)
                event_counter += 1
                return event

    def on_call_tool(self, data : dict, query_id : str, events : list, event_counter : int):
        output = data.get("output")
        tool_results = output.get("tool_results", [])
        for tool_result in tool_results:
            payload = {"type": "tool_result",
                    "tool_name": tool_result.get("tool_name"),
                    "tool_args": tool_result.get("tool_args"),
                    "data": tool_result.get("tool_data"),
                    #"token_stream" : token_stream,
                    "query_id": query_id
                    }

            events.append({
            "order": event_counter,
            **payload,
            "timestamp": datetime.now().isoformat()
            })
            event_counter += 1
            #token_stream = ""
            return payload

    # =================================
    #       INITIAL PROJECT SCAN
    # ================================= 
    async def initialize_project(self, user_input: str, 
                              attachments: list[dict],
                              session_id: str, 
                              user_id: str,
                              agent_type: Literal["fast", "expert"],
                              llm_provider: Literal["google", "openai", "claude"],
                              query_id : str,
                              project_id: Optional[str] = None):
        '''Initial project scan to generate FactSheet from initial input and attachments'''
        
        thread = {"configurable":
                      {"thread_id": session_id,
                       "user_id": user_id,
                       "custom_project_id": project_id}
                  }
        agent_instance = self._compile_agent(agent_type=agent_type, llm_provider=llm_provider, query_id=query_id)
        # NEW OR EXISTING CONVERSATION
        await self.load_or_create_conversation(agent_instance, thread, session_id)

        
        events = []
        damages = []
        claims = []
        deadlines = []
        files = []

        initial_input = await self.context_manager.analyze_init_input(user_input)
        for att in attachments:
            content_txt = self.handle_attachments(att, session_id=session_id, user_id=user_id, query_id=query_id)
            logger.debug(f"Analyzing attachment: {att.get('filename','')} (ID: {att.get('file_id','')})")
            result = await self.context_manager.analyze_doc(initial_input, content_txt, 
                                                            file_id=att.get("file_id",""),
                                                            filename=att.get("filename",""),
                                                            path="",
                                                            file_type=att.get("file_type",""),
                                                            size=len(content_txt),
                                                            )
            analyzed_doc = result.get("file")
            logger.debug(f"Analyzed document: {analyzed_doc.filename} (ID: {analyzed_doc.file_id}) - Result {analyzed_doc.model_dump()}")

            # Collect results from analyzed documents
            files.append(analyzed_doc)
            damages.extend(analyzed_doc.damage) if analyzed_doc.damage else None
            claims.extend(analyzed_doc.claim) if analyzed_doc.claim else None
            deadlines.extend(analyzed_doc.deadline) if analyzed_doc.deadline else None

            events.extend(result.get("events", [])) if result.get("events") else None

        factual_facts = await self.context_manager.analyze_factual_facts(initial_input, events)

        events_txt = " ".join([f"- {event.description} (Date: {event.date}" for event in events])
        rag_content_law = self.vs.query(query = events_txt, table_name = "laws", n_results=2) #Implement query based on initial input
        governing_law = await self.context_manager.analyze_governing_law(events = events, rag_content_law=rag_content_law) #IMplementer
        result = FactSheet(timeline=events,
                            damages=damages,
                            claims=claims,
                            deadlines=deadlines,
                            governing_law=governing_law,
                            **factual_facts.model_dump(),
                            **initial_input.model_dump(),
                            )
        
        self.conversation_manager.save_init_scan(factsheet=result,
                                                 files=files,
                                                 user_id=user_id,
                                                 session_id=session_id,
                                                 agent_type=agent_type,
                                                 llm_provider=llm_provider,
                                                 query_id=query_id,
                                                 project_id=project_id if project_id else None)

        # Return a JSON-serializable dict with all metadata
        return {
            "agent_type": agent_type,
            "llm_provider": llm_provider,
            "attachments": attachments,
            "factsheet": result.model_dump(mode='json'),
            "created_session_id": session_id
        }


