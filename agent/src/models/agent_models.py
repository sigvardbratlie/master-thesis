from typing import Annotated, Optional, Sequence, TypedDict
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages



# def add_tool_results(existing: list, new: list) -> list:
#     return existing + new

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    attachments : Optional[list[str]] = None #list of file_ids for attachments associated with this agent state, can be used to retrieve metadata and content from storage when needed
