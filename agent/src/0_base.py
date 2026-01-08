import json
#import pandas as pd
from langgraph.graph import StateGraph,END
from typing import Dict,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
import ast
import random
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,BaseMessage,ToolMessage,AIMessageChunk
#from langchain_openai import ChatOpenAI,OpenAIEmbeddings
#from langchain_tavily import TavilySearch
from langchain_core.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from google.cloud import bigquery
import os
import tiktoken
import logging
from geopy.geocoders import Nominatim

logger = logging.getLogger("agent")

#logger.set_level("INFO")
#langgraph.debug = True
#os.chdir("..")


# ==== SETUP TOOLS ====

# @tool
# def ask_user_for_info(question : str) -> str:
#     """A function to ask the user for additional information."""
#     return question

# @tool
# def execute_bq_query(query: str) -> str:
#     """Executes a SQL query on Google BigQuery and returns the result as a JSON string."""
#     try:
#         client = bigquery.Client()
#         #print(f"\n--- EXECUTING QUERY ---\n{query}\n-----------------------\n")
#         df = client.query(query).to_dataframe()
#         result_json = df.to_json(orient='records', date_format='iso')
#         logger.info(f'Read in {len(df)} rows with `execute_bq_query` tool')
#         return result_json if not df.empty else "Query executed successfully, but returned no results."
#     except Exception as e:
#         return f"An error occurred: {e}"

@tool
def get_geoinfo(address : str) -> dict:
    """A function to find basic geographical information about an address"""
    geo = Nominatim(user_agent="predict_homes")
    try:
        coor = geo.geocode(address)
        if coor:
            data = {"lat" : coor.latitude,
                    "lng" : coor.longitude,}
            data["display_name"] = coor.raw.get("display_name","")

            postal_code = (coor.raw.get("display_name")).split(",")[-2].strip()
            if len(postal_code) == 4 and isinstance(int(postal_code), int):
                data["postal_code"] = postal_code
            else:
                for i in coor.raw.get("display_name").split(","):
                    if len(i.strip()) == 4 and isinstance(int(i.strip()), int):
                        data["postal_code"] = i.strip()
            return data
        else:
            print('No data from address')
            raise Exception("No data from address")
    except Exception as e:
        print(e)

@tool
def list_table_info(table_id : str,dataset_id : str) -> str:
    """
    Lists the schema information for the specified BigQuery table.
    Use this tool to understand the structure of the tables you are querying.

    Args:
        table_id (str): The table id
        dataset_id (str): The dataset id

    Example
    list_table_info with query {'table_id': 'homes', 'dataset_id': 'agent'}
    
    """
    client = bigquery.Client()
    table = client.get_table(f"{dataset_id}.{table_id}")
    schema_info = [{"name": field.name, "type": field.field_type, "mode": field.mode} for field in table.schema]
    return json.dumps(schema_info, indent=2)   


# BASE_TOOLS = [#ask_user_for_info,
#               #execute_bq_query,
#               get_geoinfo,
#               list_table_info,
#               #tavily_search,
#               ]

class AgentState(TypedDict):
    messages : Annotated[Sequence[BaseMessage],add_messages]

class Agent:
    """
    An Agent designet to give property valuations and answer questions on the norwegian housing market.
    """
    def __init__(self,
                 llms : dict,
                 tools : List[tool],
                 prompt : str,
                 domain : str,
                 checkpointer,
                 ):
        """
                Initializes the HomeAgent.
                Args:
                    llms (dict[str, BaseChatModel]): A dictionary mapping agent types to LLM models.
                    tools (List[tool]): A list of tools the agent can use.
                    logger (Logger, optional): The logger instance. Defaults to None.
                """
        self.logger = logger
        # Use standard logging API
        try:
            self.logger.setLevel("DEBUG")
        except Exception:
            pass
        self.tools = tools
        self.llms = llms
        self.domain = domain
        self.prompt = prompt
        self.checkpointer = checkpointer


    def _should_continue(self,state: AgentState) -> bool:
        """Determine if we should continue or end the conversation"""
        result = state["messages"][-1]
        return hasattr(result, "tool_calls") and len(result.tool_calls) > 0

    def _format_tool_result(self, result: Any) -> str:
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return str(result)

    def _safe_parse_content(self, content: Any) -> Optional[Any]:
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            try:
                return ast.literal_eval(content)
            except (ValueError, SyntaxError):
                return None

    def _get_last_tool_payload(self, messages: Sequence[BaseMessage], tool_name: str) -> Optional[Any]:
        for msg in reversed(messages[:-1]):
            if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == tool_name:
                parsed = self._safe_parse_content(msg.content)
                if parsed:
                    return parsed
        return None

    async def _call_tool(self,state: AgentState) -> AgentState:
        """Executes tool calls from the LLM's response"""

        if not isinstance(state["messages"][-1], AIMessage):
            raise TypeError(f'The last message is not an AI message and has not attr "tool_calls"')

        tool_calls = state["messages"][-1].tool_calls
        tools_dict = {our_tool.name: our_tool for our_tool in self.tools}
        results = []

        if not tool_calls:
            self.logger.info(f'No tool calls found')
            # Return an empty list to avoid an error, as there's nothing to append
            return {"messages": []}

        for tool in tool_calls:
            name = tool.get("name", "")
            args = tool.get("args", "")
            self.logger.info(f'Calling Tool: {name} with query: {args}')

            if name in tools_dict:
                tool_to_call = tools_dict[name]
                try:
                    #result = tool_to_call.invoke(input_to_tool)
                    result = await tool_to_call.ainvoke(args)
                except Exception as e:
                    result = f'Something went wrong when calling tool {name} with args {args} : {e}.'
                    self.logger.info(result)

                self.logger.info(f'Result length: {len(str(result))}')

                # CORRECT: Use the proper keyword 'tool_call_id'
                formatted_result = self._format_tool_result(result)
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=formatted_result))
            else:
                self.logger.info(f'{tool["name"]} does not exists in tools. \nTools available: {tools_dict.keys()}')
                result = "Incorrect Tool Name, Please Retry and Select tool from list of avaible tools"
                # CORRECT: Use the proper keyword 'tool_call_id'
                results.append(ToolMessage(tool_call_id=tool["id"], name=tool["name"], content=str(result)))

        self.logger.info(f'Tools execution complete')
        return {"messages": results}


    def _truncate_tokens(self, messages, max_tokens=7000):
        """Truncate messages to fit within max_tokens while preserving tool-call structure."""
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        token_count = 0
        truncated = []

        for msg in reversed(messages):
            token_count += len(enc.encode(msg.content or ""))
            truncated.insert(0, msg)

            if token_count > max_tokens:
                break

        # As a final safety check: drop any orphan tool messages at the start
        while truncated and isinstance(truncated[0], ToolMessage):
            truncated.pop(0)

        return truncated

    def _call_llm(self, state: AgentState, llm_with_tools : BaseChatModel) -> AgentState:
        """Function to call the LLM with the current state.

        """
        base_prompt = SystemMessage(content=self.prompt)
        #messages = self._truncate_messages(state["messages"], max_messages=6)
        messages = self._truncate_tokens(state["messages"], max_tokens=6000)
        try:
            message = llm_with_tools.invoke([base_prompt] + messages) 
            #message = llm_with_tools.invoke(state["messages"])
            return {'messages': [message]}
        except Exception as e:
            self.logger.error(f"Error invoking LLM: {e}")
            raise e
        

    def _compile_agent(self,llm_provider : Literal["google","openai","claude"], agent_type : Literal["fast","expert"]):
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
        #selected_llm = self.llms.get(agent_type).bind_tools(tools)
        logger.info(f'Running agent with llm supplier {llm_provider} and type {agent_type}')


        llm = selected_llm.bind_tools(self.tools)

        graph = StateGraph(AgentState)
        graph.add_node("call_llm", lambda state: self._call_llm(state,llm_with_tools=llm))
        graph.add_node("call_tool", self._call_tool)
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

    async def stream_response(self, user_input: str, session_id: str, user_id: str,
                              agent_type: Literal["fast", "expert"],
                              llm_provider: Literal["google", "openai", "claude"]):
        """
        This is a generator function that yields status updates and the final response.
        """
        agent_instance = self._compile_agent(agent_type=agent_type, llm_provider=llm_provider)
        thread = {"configurable":
                      {"thread_id": session_id,
                       "user_id": user_id,
                       "domain": self.domain}
                  }

        try:
            current_state = await agent_instance.aget_state(thread)
            is_new_conv = not current_state.values.get("messages", [])
        except Exception:
            is_new_conv = True

        if is_new_conv:
            self.logger.info(f'Creating new conversation. Thread: {thread}. Choosing type of question...')
            system_message = SystemMessage(content=self.prompt)
            await agent_instance.aupdate_state(thread, {"messages": [system_message]})
        else:
            self.logger.info(f'Continueing conversation (thread: {session_id})')

        # STREAM RESPONSE
        async for chunk in agent_instance.astream_events({"messages": [HumanMessage(content=user_input)]}, config=thread):
            ev = chunk.get("event")
            data = chunk.get("data")
            name = chunk.get("name")

            #token for token streaming
            if ev == "on_chat_model_stream":
                if data.get("chunk"):
                    chunk = data.get("chunk")
                    if isinstance(chunk,AIMessageChunk):
                        if chunk.content:
                            #print(f'CHUNK CONTENT ; {chunk.content}')
                            yield {"type" : "token", "content": chunk.content}
            
            
            if name == "call_llm":
                chunk = data.get("chunk")
                if chunk and isinstance(chunk,dict) and chunk.get("messages"):
                    ai_msg = data.get("chunk").get("messages")[-1]

                    if ai_msg.tool_calls:
                        for tool_call in ai_msg.tool_calls:
                            tool_name = tool_call['name']
                            #adapt to your own tool names
                            yield {"type": "status", "content": f"⚙️ Running tool: {tool_name}..."}

                    # === FINAL LLM RESPONSE ===
                    if ai_msg.content:
                        final_response_content = ai_msg.content
                        yield {"type": "final_answer", "content": final_response_content}
