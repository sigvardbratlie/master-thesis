from typing import TypedDict, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime

FileType = Literal["application/pdf", "text/plain", "application/msword","message/rfc822","text/csv",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation", 
                    #"application/vnd.ms-powerpoint", 
                    #"application/msword",
                    #"application/vnd.ms-excel", 
                    ]
FileExt = [".pdf", ".txt",  ".eml", ".csv", ".xlsx",".pptx",".docx",
           #OLD MS
           #".doc", ".xls",  ".ppt",
           ]
           
# ===== User & Company Models =====

class UserDetails(BaseModel):
    """User details stored in Supabase user_details table"""
    user_id: str
    created_at: str | None = None
    user_role: str | None = None
    user_first_name: str | None = None
    user_last_name: str | None = None
    company_id: str | None = None


class CompanyDetails(BaseModel):
    """Company details stored in Supabase company_details table"""
    company_id: str
    company_vat_nr: str | None = None
    company_name: str | None = None

# ===== Backend Request Models =====

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str = Field(description="Unique identifier for the file, e.g., a UUID string")
    content: str  = Field(description="Base64 encoded content")
    path : str = Field(description="Storage path for the attachment, e.g., 'user_id/session_id/file_id.ext'. Should also end with extension")
    file_type: FileType = Field(description="MIME type of the file, e.g., 'application/pdf', 'text/plain', 'message/rfc822', etc.")
    size: int = Field(description="Size of the file in bytes")
    query_id: str = Field(description="ID (uuid) of the query this attachment is associated with")
    event_id: str | None = Field(None, description="ID of the event this attachment is associated with, if applicable")

# class EmailModel(BaseModel):
#     """Email sent to backend API"""
#     email_id : str
#     subject: str
#     sender: str
#     recipients: list[str]
#     cc: list[str] | None = None
#     bcc: list[str] | None = None
#     email_date: datetime | None = None
#     body_text: str
#     body_html: str | None = None
#     headers: dict | None = None
#     attachments: list[str] | None = Field(default=None, description="List of attachment file_ids")
#     query_id: str
#     event_id : str | None = None

class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: list[AttachmentModel] | None = []
    session_id: str
    llm_model: str
    query_id: str
    project_id: str | None = None
    focus_context: str | None = None


class CleanupElementsRequest(AskAgentRequest):
    """POST /cleanup-project-elements request"""
    element_types: list[str]


class StreamlitUserInfo(BaseModel):
    """POST /token-from-streamlit request"""
    sub: str
    email: str
    name: str
    picture: str | None = None


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
    title: str | None | None = None
    llm_model: str | None = None


class SessionHistoryResponse(BaseModel):
    """GET /load-session-history response"""
    events: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    project_id: str | None = None
    title: str | None = None
    llm_model: str | None = None
    last_updated: str | None = None


# ===== SSE Stream Event Models =====

class TokenEvent(BaseModel):
    """SSE event type: token"""
    type: Literal["token"]
    data: str
    query_id: str

# ===== MODELS SAVING TO FIRESTORE =====
class HumanEventData(BaseModel):
    attachments: list[AttachmentModel] | None = None
    content : str | None = None

class ToolResultData(BaseModel):
    tool_name: str
    tool_args: dict
    data : Any | None = None

class AIEventData(BaseModel):
    content : str | None = None
    invalid_tool_calls : list | None = None
    token_stream: str | None = None
    reasoning_stream: str | None = None
    tool_calls : list | None = None

class StreamEvent(BaseModel):
    order: int
    type: Literal["human", "ai", "tool_result"]
    created_at: datetime
    query_id: str
    langchain_id: str | None = None
    data : HumanEventData | ToolResultData | AIEventData

# ===== Session State TypedDict =====

class SessionState(TypedDict, total=False):
    """Type definition for st.session_state"""
    # Initialization
    state_initialized: bool
    is_authenticated: bool

    # User info
    user_id: str | None
    access_token: str | None
    token_type: str | None
    user_name: str | None

    # Session info
    session_id: str
    session_title: str | None

    # Messages & history
    messages: list[dict[str, Any]]
    first_question: bool

    # Agent config
    llm_model: str | None

    # UI state
    question_to_process: str | None
    files_to_process: list[Any]
    sessions_loaded: bool
    current_session_loaded: bool
    is_searching: bool

    # Backend
    backend_url: str

    # Tool results
    tool_results: dict[str, Any]
    company_data: str | None  # JSON string
    industry_data: str | None  # JSON string

    # Misc
    valuation_doc_count: int

