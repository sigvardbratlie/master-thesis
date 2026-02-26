from typing import TypedDict, Optional, Literal, Any
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
    created_at: Optional[str] = None
    user_role: Optional[str] = None
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    company_id: Optional[str] = None


class CompanyDetails(BaseModel):
    """Company details stored in Supabase company_details table"""
    company_id: str
    company_vat_nr: Optional[str] = None
    company_name: Optional[str] = None

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
    event_id: Optional[str] = Field(None, description="ID of the event this attachment is associated with, if applicable")

# class EmailModel(BaseModel):
#     """Email sent to backend API"""
#     email_id : str
#     subject: str
#     sender: str
#     recipients: list[str]
#     cc: Optional[list[str]] = None
#     bcc: Optional[list[str]] = None
#     email_date: Optional[datetime] = None
#     body_text: str
#     body_html: Optional[str] = None
#     headers: Optional[dict] = None
#     attachments: Optional[list[str]] = Field(default=None, description="List of attachment file_ids")
#     query_id: str
#     event_id : Optional[str] = None

class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: Optional[list[AttachmentModel]] = []
    session_id: str
    llm_model: str
    query_id: str
    project_id: Optional[str] = None
    focus_context: Optional[str] = None


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

