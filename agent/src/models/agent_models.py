from typing import Annotated, Sequence
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from .api_request_models import AskAgentRequest, CleanupElementsRequest
from .project_models import InitialInput, FactSheet
from .response_models import ProjectData
from typing_extensions import Annotated
import operator
from pydantic import BaseModel, Field

class AgentState(BaseModel):
    messages: Annotated[Sequence[BaseMessage], add_messages] = Field(default_factory=list)
    attachments: list[str] | None = None

class PipelineState(BaseModel):
    # Inputs
    query: AskAgentRequest | CleanupElementsRequest

    # Intermediate
    email_models: list = Field(default_factory=list)
    docs_by_file: dict = Field(default_factory=dict)
    collapsed_emails: dict = Field(default_factory=dict)
    input_: InitialInput | ProjectData | None = None

    # Collected results — reducer-syntaks fungerer med Annotated også på Pydantic
    events:      Annotated[list, operator.add] = Field(default_factory=list)
    damages:     Annotated[list, operator.add] = Field(default_factory=list)
    claims:      Annotated[list, operator.add] = Field(default_factory=list)
    deadlines:   Annotated[list, operator.add] = Field(default_factory=list)
    attachments: Annotated[list, operator.add] = Field(default_factory=list)
    emails:      Annotated[list, operator.add] = Field(default_factory=list)
