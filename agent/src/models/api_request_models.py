from pydantic import BaseModel, Field, field_serializer
from typing import Literal
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from datetime import datetime,date
import uuid
from langgraph.graph.message import add_messages

file_types = [#Basic MIME types
                   "application/pdf", 
                   "text/plain", 
                   "text/csv",
                   "text/markdown",
                   "message/rfc822",

                   #TO BE IMPLEMENTED
                #    "text/html",
                #    "text/xml",
                #    "application/json",
                #    "application/xml",
                #    "image/jpeg",
                #    "image/png",
                #    "image/webp",
                   
                   
                   #MS Office MIME types                   
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation", 
                    #"application/vnd.ms-powerpoint", 
                    #"application/msword",
                    #"application/vnd.ms-excel", 
                    ]
FileType = Literal[*file_types]
#=================================
# ===== API REQUEST MODELS =======

#=================================

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str
    content: str | None = Field(None, description="Base64 encoded content")
    body : str | None = Field(None, description="Text content of the file, if applicable (e.g., for text files or extracted text from PDFs)")
    path : str = Field(description="Storage path for the attachment, e.g., 'user_id/session_id/file_id.ext'. Should also end with extension")
    file_type: FileType = Field(description="MIME type of the file, e.g., 'application/pdf', 'text/plain', 'message/rfc822', etc.")
    size: int = Field(description="Size of the file in bytes")
    query_id: str = Field(description="ID (uuid) of the query this attachment is associated with")
    event_id: str | None = Field(None, description="ID of the event this attachment is associated with, if applicable")

class EmailModel(BaseModel):
    """Email sent to backend API"""
    file_id : str #foreign key
    path : str
    query_id: str
    event_id: str | None = None

    subject: str
    from_addr: str
    from_name: str | None = None
    to: list[str]
    to_names: list[str] | None = None
    cc: list[str] | None = None
    cc_names: list[str] | None = None
    bcc: list[str] | None = None
    bcc_names: list[str] | None = None
    date: datetime | None = None
    
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    thread_topic: str | None = None
    thread_index: str | None = None
    thread_id: str | None = None

    body_text: str
    body_html: str | None = None
    headers: dict | None = None
    size: int | None = None
    
    attachments: list | None = None #file ids

    reference_paths : list[str] | None = None 

class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: list[AttachmentModel] | None = None
    session_id: str
    llm_model : str
    query_id: str
    project_id: str | None = None
    focus_context: str | None = None


class CleanupElementsRequest(AskAgentRequest):
    """POST /cleanup-project-elements request"""
    element_types: list[Literal["events", "damages", "claims", "deadlines", "parties"]]


class StreamlitUserInfo(BaseModel):
    sub: str  # Unique Google ID
    email: str
    name: str
    picture: str | None = None


class ToolResultData(BaseModel):
    tool_name: str
    tool_args: dict
    data : dict | None = None


class EventData(BaseModel):
    attachments: list[str] | None = Field(None, description="List of file_ids attached to this human message")
    invalid_tool_calls : list | None = None
    tool_calls : list | None = None
    token_stream: str | None = None
    reasoning_stream: str | None = None


class StreamEvent(BaseModel):
    order: int
    type: Literal["human", "ai", "tool_result"]
    created_at: datetime
    query_id: str
    event_id : str 
    session_id : str
    langchain_id: str | None = None
    content : str | None = None
    data : ToolResultData | EventData

class StreamData(BaseModel):
    llm_model : str
    project_id: str | None = None
    title : str | None = None
    last_updated : datetime | None = None
    last_query_id : str
    events : list[StreamEvent]
    attachments : list[AttachmentModel] | None = None

class VectorStoreMetadata(BaseModel):
    #doc_id : str #auto generated
    #content : str #txt content of chunk
    #embedding  : list[float] repeated
    file_id: str
    filename: str
    file_type: FileType
    size : int | None = None
    user_id: str
    session_id: str
    query_id: str
    path : str | None = None
    project_id: str | None = None
    uploaded_at : datetime | None = None
    created_at : datetime | None = None
    updated_at : datetime | None = None
    
    author : str | None = None
    page_count : int | None = None
    creator : str | None = None
    producer : str | None = None
    title : str | None = None
    language : str | None = None
    encryption : str | None = None
    keywords : str | None = None
    comments : str | None = None

    chunk : int | None = None
    total_chunks : int | None = None
    embedding_model : str = None

    @field_serializer("uploaded_at", "created_at", "updated_at")
    def serialize_datetime(self, v: datetime | None) -> str | None:
        return v.isoformat() if v is not None else None

