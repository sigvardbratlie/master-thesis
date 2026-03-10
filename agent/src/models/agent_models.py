from typing import Annotated, Sequence
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)
    attachments: list[str] | None = None
