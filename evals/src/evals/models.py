from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from deepeval.evaluate.types import EvaluationResult


# ── Conversation ───────────────────────────────────────────────────────────────

class ConversationTurn(BaseModel):
    """A single Q&A turn within a session."""
    input: str
    answer: str
    order: Optional[int] = None
    query_id: Optional[str] = None
    model_response: Optional[str] = None  # Populated after agent run
    turn_duration: Optional[float] = None  # Duration in seconds, populated after agent run


# ── Session ────────────────────────────────────────────────────────────────────

class Session(BaseModel):
    """A single evaluation session with its conversation and attachments."""
    session_name: str
    date: str  # YYYY-MM-DD
    init_query: str
    conversation: list[ConversationTurn]
    attachments: list[str] = Field(default_factory=list)  # GCS blob paths
    runtime_session_id: Optional[str] = None  # Populated after agent run
    duration : Optional[float] = None  # Duration in seconds, populated after agent run


# ── Dataset payload ────────────────────────────────────────────────────────────

class DatasetPayload(BaseModel):
    """Raw dataset as loaded from GCS (datasets/<name>/dataset_<name>.json)."""
    dataset_name: str
    project_id: str
    user_id: str
    sessions: list[Session]


# ── Gathered result payload ────────────────────────────────────────────────────

class GatheredResultPayload(DatasetPayload):
    """Dataset enriched with agent run metadata after CollectAgentResult.run_agent()."""
    eval_run_id: str
    llm_model: str
    agent_type: Literal["custom", "baseline", "baseline_rag"]
    runtime_project_id: str
    token_counts: Optional[Any] = None
    time_usage: Optional[Any] = None


# ── Eval output payload ────────────────────────────────────────────────────────

class EvalOutput(BaseModel):
    """Output written to GCS by Evaluater.save_evaluation_results().
    token_counts and time_usage are not stored — they are joined from 04_results at load time."""
    dataset_name: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    eval_run_id: Optional[str] = None
    llm_model: Optional[str] = None
    agent_type: str = "unknown"
    created_at: str
    results: Optional[list[EvaluationResult]] = None
    # Populated at load time by joining 04_results on eval_run_id
    token_counts: Optional[Any] = None
    time_usage: Optional[Any] = None
