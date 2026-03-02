from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from deepeval.evaluate.types import EvaluationResult



class TokenCount(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    llm_calls: int

class TimeCount(BaseModel):
    starttime: datetime
    endtime: datetime
    duration_seconds: float

# ── Conversation ───────────────────────────────────────────────────────────────

class ConversationTurn(BaseModel):
    """A single Q&A turn within a session."""
    input: str
    answer: str
    order: Optional[int] = None
    query_id: Optional[str] = None
    model_response: Optional[str] = None  # Populated after agent run
    time_counts: Optional[TimeCount] = None  
    token_counts : Optional[TokenCount] = None

# ── Session ────────────────────────────────────────────────────────────────────

class Session(BaseModel):
    """A single evaluation session with its conversation and attachments."""
    session_name: str
    date: str  # YYYY-MM-DD
    init_query: str
    init_query_id: Optional[str] = None
    conversation: list[ConversationTurn]
    attachments: list[str] = Field(default_factory=list)  # GCS blob paths
    runtime_session_id: Optional[str] = None  # Populated after agent run
    time_counts : Optional[TimeCount] = None  # Duration in seconds, populated after agent run
    token_counts : Optional[TokenCount] = None  # Populated after agent run


# ── Dataset payload ────────────────────────────────────────────────────────────

class DatasetPayload(BaseModel):
    """Raw dataset as loaded from GCS (datasets/<name>/dataset_<name>.json)."""
    dataset_name: str
    project_id: str
    user_id: str
    sessions: list[Session]


# ── Gathered result payload ────────────────────────────────────────────────────

class GatheredResultPayload(DatasetPayload):
    """Dataset enriched with agent run metadata after CollectAgentResult.run_agent().

    Key identity fields:
    - project_id   (from DatasetPayload): original case ID from the dataset JSON — for
                   tracing back to the source legal case.
    - eval_run_id: unique ID generated per run. This is also used as the Supabase
                   project_id during execution, so each run gets a fully isolated
                   Supabase project. To look up agent data in Supabase, use eval_run_id.
    """
    eval_run_id: str
    llm_model: str
    agent_type: Literal["custom", "baseline", "baseline_rag"]
    token_counts: Optional[TokenCount] = None
    time_counts: Optional[TimeCount] = None


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
    # # Populated at load time by joining 04_results on eval_run_id
    # token_counts: Optional[TokenCount] = None
    # time_counts: Optional[TimeCount] = None


# ── Base metric ────────────────────────────────────────────────────────────────

class BaseMetric(BaseModel):
    """Shared identity fields for all observation-level metric models."""
    dataset_name: str
    eval_run_id: str
    query_id: Optional[str] = None
    session_id: Optional[str] = None
    llm_model: str
    agent_type: str


# ── Observation-level metrics ──────────────────────────────────────────────────

class DeepEvalObservation(BaseMetric):
    """One observation per query × eval_run from LLM-as-judge evaluation."""
    name: Optional[str] = None
    correctness: float
    relevancy: float
    completeness: float
    success: bool


class RougeObservation(BaseMetric):
    """One observation per query × eval_run for reference-based metrics."""
    name: Optional[str] = None
    rouge_precision: float
    rouge_recall: float
    rouge_fmeasure: float
    actual_output: str


class ResourceObservation(BaseMetric,TokenCount, TimeCount):
    """One observation per query × eval_run for resource usage metrics."""
    pass

