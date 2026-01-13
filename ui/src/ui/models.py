from typing import TypedDict, Optional, Literal, Any
from pydantic import BaseModel


# ===== Backend Request Models =====

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str
    content: str  # Base64 for PDF, text for others
    file_type: str
    size: int


class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: list[AttachmentModel]
    session_id: str
    domain: str
    agent_type: Literal["fast", "expert"]
    llm_provider: Literal["google", "openai", "claude"]
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
    title: str
    agent_type: Optional[str] = None
    llm_provider: Optional[str] = None


class SessionHistoryResponse(BaseModel):
    """GET /load-session-history response"""
    events: list[dict[str, Any]]
    title: str
    domain: str
    agent_type: Optional[str] = None
    llm_provider: Optional[str] = None
    last_updated: Optional[str] = None


# ===== SSE Stream Event Models =====

class TokenEvent(BaseModel):
    """SSE event type: token"""
    type: Literal["token"]
    data: str
    query_id: str


class ToolCallData(BaseModel):
    """Tool call within AI message"""
    name: str
    args: dict[str, Any]


class AIMessageData(BaseModel):
    """Data for AI message"""
    content: str
    tool_calls: Optional[list[ToolCallData]] = None
    token_stream: Optional[str] = None


class AIEvent(BaseModel):
    """SSE event type: ai"""
    type: Literal["ai"]
    data: AIMessageData
    query_id: str


class ToolResultEvent(BaseModel):
    """SSE event type: tool_result"""
    type: Literal["tool_result"]
    tool_name: str
    tool_args: Optional[dict[str, Any]] = None
    data: Any
    query_id: str
    token_stream: Optional[str] = None


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
    domain: str

    # Messages & history
    messages: list[dict[str, Any]]
    first_question: bool

    # Agent config
    agent_type: Literal["fast", "expert"]
    llm_provider: Literal["google", "openai", "claude"]

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

