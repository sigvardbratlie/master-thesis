from pydantic import BaseModel, Field
from typing import Optional, Literal
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from datetime import datetime,date
import uuid
from langgraph.graph.message import add_messages

FileType = Literal["application/pdf", "text/plain", "application/msword","message/rfc822","text/csv",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation", 
                    #"application/vnd.ms-powerpoint", 
                    #"application/msword",
                    #"application/vnd.ms-excel", 
                    ]
#=================================
# ===== API REQUEST MODELS =======

#=================================

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str
    content: Optional[str] = Field(None, description="Base64 encoded content")
    path : str = Field(description="Storage path for the attachment, e.g., 'user_id/session_id/file_id.ext'. Should also end with extension")
    file_type: FileType = Field(description="MIME type of the file, e.g., 'application/pdf', 'text/plain', 'message/rfc822', etc.")
    size: int = Field(description="Size of the file in bytes")
    query_id: str = Field(description="ID (uuid) of the query this attachment is associated with")
    event_id: Optional[str] = Field(None, description="ID of the event this attachment is associated with, if applicable")

class EmailModel(BaseModel):
    """Email sent to backend API"""
    file_id : str #foreign key
    path : str
    query_id: str
    event_id: Optional[str] = None

    subject: str
    from_addr: str
    to: list[str]
    cc: Optional[list[str]] = None
    bcc: Optional[list[str]] = None
    date: Optional[datetime] = None
    
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[str] = None
    thread_topic: Optional[str] = None
    thread_index: Optional[str] = None
    thread_id: Optional[str] = None

    body_text: str
    body_html: Optional[str] = None
    headers: Optional[dict] = None
    size: Optional[int] = None
    
    attachments: Optional[list] = None #file ids

class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: Optional[list[AttachmentModel]] = None
    session_id: str
    llm_model : str
    query_id: str
    project_id: Optional[str] = None


class StreamlitUserInfo(BaseModel):
    sub: str  # Unique Google ID
    email: str
    name: str
    picture: Optional[str] = None


class ToolResultData(BaseModel):
    tool_name: str
    tool_args: dict
    data : Optional[dict] = None


class EventData(BaseModel):
    attachments: Optional[list[str]] = Field(None, description="List of file_ids attached to this human message")
    invalid_tool_calls : Optional[list] = None
    tool_calls : Optional[list] = None
    token_stream: Optional[str] = None


class StreamEvent(BaseModel):
    order: int
    type: Literal["human", "ai", "tool_result"]
    created_at: datetime
    query_id: str
    event_id : str 
    session_id : str
    langchain_id: Optional[str] = None
    content : Optional[str] = None
    data : EventData | ToolResultData

class StreamData(BaseModel):
    llm_model : str
    project_id: Optional[str] = None
    title : Optional[str] = None
    last_updated : Optional[datetime] = None
    last_query_id : str
    events : list[StreamEvent]
    attachments : Optional[list[AttachmentModel]] = None


class VectorStoreMetadata(BaseModel):
    #doc_id : str #auto generated
    #content : str #txt content of chunk
    #embedding  : list[float] repeated
    file_id: str
    filename: str
    file_type: FileType
    file_size : Optional[int] = None
    user_id: str
    session_id: str
    query_id: str
    path : Optional[str] = None
    uploaded_at : Optional[datetime] = None
    created_at : Optional[datetime] = None
    updated_at : Optional[datetime] = None
    chunk : Optional[int] = None
    total_chunks : Optional[int] = None
    creator : Optional[str] = None
    producer : Optional[str] = None
    embedding_model : str = None
    title : Optional[str] = None
    language : Optional[str] = None
    comments : Optional[str] = None
    keywords : Optional[str] = None

