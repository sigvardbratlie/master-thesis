from typing import TypedDict, Optional, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime

# ===== Backend Request Models =====

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str
    content: str  # Base64 for PDF, text for others
    path : str
    file_type: str
    size: int
    query_id: str
    event_id: Optional[str] = None

class EmailModel(BaseModel):
    """Email sent to backend API"""
    email_id : str
    subject: str
    sender: str
    recipients: list[str]
    cc: Optional[list[str]] = None
    bcc: Optional[list[str]] = None
    email_date: Optional[datetime] = None
    body_text: str
    body_html: Optional[str] = None
    headers: Optional[dict] = None
    attachments: Optional[list[str]] = Field(default=None, description="List of attachment file_ids")
    query_id: str
    event_id : Optional[str] = None

class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: Optional[list[AttachmentModel]] = []
    emails: Optional[list[EmailModel]] = []
    session_id: str
    llm_model: str
    query_id: str
    project_id: Optional[str] = None


class StreamlitUserInfo(BaseModel):
    """POST /token-from-streamlit request"""
    sub: str
    email: str
    name: str
    picture: Optional[str] = None


# ===== Backend Response Models =====

class TokenResponse(BaseModel):
    """POST /token-from-streamlit response"""
    access_token: str
    token_type: str
    user_id: str
    user_name: str


class SessionInfo(BaseModel):
    """Single session in user sessions list"""
    session_id: str
    title: Optional[Optional[str]] = None
    llm_model: Optional[str] = None


class SessionHistoryResponse(BaseModel):
    """GET /load-session-history response"""
    events: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    project_id: Optional[str] = None
    title: Optional[str] = None
    llm_model: Optional[str] = None
    last_updated: Optional[str] = None


# ===== SSE Stream Event Models =====

class TokenEvent(BaseModel):
    """SSE event type: token"""
    type: Literal["token"]
    data: str
    query_id: str


# class ToolCallData(BaseModel): #UTDATERT
#     """Tool call within AI message"""
#     name: str
#     args: dict[str, Any]


# class AIMessageData(BaseModel):  #UTDAERT
#     """Data for AI message"""
#     content: str
#     tool_calls: Optional[list[ToolCallData]] = None
#     token_stream: Optional[str] = None


# class AIEvent(BaseModel): #UTDATERT
#     """SSE event type: ai"""
#     type: Literal["ai"]
#     data: AIMessageData
#     query_id: str


# class ToolResultEvent(BaseModel): #UTDATERT
#     """SSE event type: tool_result"""
#     type: Literal["tool_result"]
#     tool_name: str
#     tool_args: Optional[dict[str, Any]] = None
#     data: Any
#     query_id: str
#     token_stream: Optional[str] = None


# ===== MODELS SAVING TO FIRESTORE =====
class HumanEventData(BaseModel):
    attachments: Optional[list[AttachmentModel]] = None
    content : Optional[str] = None

class ToolResultData(BaseModel):
    tool_name: str
    tool_args: dict
    data : Optional[dict] = None

class AIEventData(BaseModel):
    content : Optional[str] = None
    invalid_tool_calls : Optional[list] = None
    token_stream: Optional[str] = None
    tool_calls : Optional[list] = None

class StreamEvent(BaseModel):
    order: int
    type: Literal["human", "ai", "tool_result"]
    created_at: datetime
    query_id: str
    langchain_id: Optional[str] = None
    data : HumanEventData | ToolResultData | AIEventData

# ===== Session State TypedDict =====

class SessionState(TypedDict, total=False):
    """Type definition for st.session_state"""
    # Initialization
    state_initialized: bool
    is_authenticated: bool

    # User info
    user_id: Optional[str]
    access_token: Optional[str]
    token_type: Optional[str]
    user_name: Optional[str]

    # Session info
    session_id: str
    session_title: Optional[str]

    # Messages & history
    messages: list[dict[str, Any]]
    first_question: bool

    # Agent config
    llm_model: Optional[str]

    # UI state
    question_to_process: Optional[str]
    files_to_process: list[Any]
    sessions_loaded: bool
    current_session_loaded: bool
    is_searching: bool

    # Backend
    backend_url: str

    # Tool results
    tool_results: dict[str, Any]
    company_data: Optional[str]  # JSON string
    industry_data: Optional[str]  # JSON string

    # Misc
    valuation_doc_count: int

