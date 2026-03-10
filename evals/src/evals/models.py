from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Literal
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
    order: int | None = None
    query_id: str | None = None
    model_response: str | None = None  # Populated after agent run
    time_counts: TimeCount | None = None  
    token_counts : TokenCount | None = None

# ── Session ────────────────────────────────────────────────────────────────────

class Session(BaseModel):
    """A single evaluation session with its conversation and attachments."""
    session_name: str
    session : int | None = None  # Added session number field
    date: str  # YYYY-MM-DD
    init_query: str
    init_query_id: str | None = None
    init_query_token_count : TokenCount | None = None
    init_query_time_count : TimeCount | None = None
    conversation: list[ConversationTurn]
    attachments: list[str] = Field(default_factory=list)  # GCS blob paths
    runtime_session_id: str | None = None  # Populated after agent run
    time_counts : TimeCount | None = None  # Duration in seconds, populated after agent run
    token_counts : TokenCount | None = None  # Populated after agent run


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
    token_counts: TokenCount | None = None
    time_counts: TimeCount | None = None


# ── Eval output payload ────────────────────────────────────────────────────────

class EvalOutput(BaseModel):
    """Output written to GCS by Evaluater.save_evaluation_results().
    token_counts and time_usage are not stored — they are joined from 04_results at load time."""
    dataset_name: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    eval_run_id: str | None = None
    llm_model: str | None = None
    agent_type: str = "unknown"
    created_at: str
    results: list[EvaluationResult] | None = None
    # # Populated at load time by joining 04_results on eval_run_id
    # token_counts: TokenCount | None = None
    # time_counts: TimeCount | None = None


# ── Base metric ────────────────────────────────────────────────────────────────

class BaseMetric(BaseModel):
    """Shared identity fields for all observation-level metric models."""
    dataset_name: str
    eval_run_id: str
    query_id: str | None = None
    session_id: str | None = None
    session :  int | None = None
    session_name: str | None = None
    llm_model: str
    agent_type: str


# ── Observation-level metrics ──────────────────────────────────────────────────

class DeepEvalObservation(BaseMetric):
    """One observation per query × eval_run from LLM-as-judge evaluation."""
    name: str | None = None
    correctness: float
    relevancy: float
    completeness: float
    success: bool


class ReferenceObservation(BaseMetric):
    """One observation per query × eval_run for reference-based metrics."""
    name: str | None = None
    bert_precision: float
    bert_recall: float
    bert_f1: float
    s_bert_similarity: float


class RougeObservation(BaseMetric):
    """One observation per query × eval_run for ROUGE-based metrics."""
    name: str | None = None
    rouge_precision: float
    rouge_recall: float
    rouge_fmeasure: float
    actual_output: str
    


class ResourceObservation(BaseMetric,TokenCount, TimeCount):
    """One observation per query × eval_run for resource usage metrics."""
    pass

