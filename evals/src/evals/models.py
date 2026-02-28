from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from deepeval.evaluate.types import EvaluationResult
import numpy as np

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



# ── RougeL payload ────────────────────────────────────────────────────────

class RougeLMetric(BaseModel):
    eval_run_id: str
    dataset_name: str
    llm_model: str
    raw_precision: list[float]
    raw_recall: list[float]
    raw_fmeasure: list[float]

    @property
    def precision_avg(self):
        return np.mean(self.raw_precision)
    @property
    def precision_std(self):
        return np.std(self.raw_precision)
    @property
    def recall_avg(self):
        return np.mean(self.raw_recall)
    @property
    def recall_std(self):
        return np.std(self.raw_recall)
    @property
    def fmeasure_avg(self):
        return np.mean(self.raw_fmeasure)
    @property
    def fmeasure_std(self):
        return np.std(self.raw_fmeasure)
    
# ── Token metric payload ──────────────────────────────────────────────────────

class TokenMetric(BaseModel):
    raw_input_tokens: list[int]
    raw_output_tokens: list[int]
    raw_total_tokens: list[int]
    raw_llm_calls: list[int]

    @property
    def input_tokens_avg(self): return float(np.mean(self.raw_input_tokens))
    @property
    def input_tokens_std(self): return float(np.std(self.raw_input_tokens, ddof=1)) if len(self.raw_input_tokens) > 1 else 0.0
    @property
    def output_tokens_avg(self): return float(np.mean(self.raw_output_tokens))
    @property
    def output_tokens_std(self): return float(np.std(self.raw_output_tokens, ddof=1)) if len(self.raw_output_tokens) > 1 else 0.0
    @property
    def total_tokens_avg(self): return float(np.mean(self.raw_total_tokens))
    @property
    def total_tokens_std(self): return float(np.std(self.raw_total_tokens, ddof=1)) if len(self.raw_total_tokens) > 1 else 0.0
    @property
    def llm_calls_avg(self): return float(np.mean(self.raw_llm_calls))
    @property
    def llm_calls_std(self): return float(np.std(self.raw_llm_calls, ddof=1)) if len(self.raw_llm_calls) > 1 else 0.0


# ── Time metric payload ───────────────────────────────────────────────────────

class TimeMetric(BaseModel):
    raw_duration: list[float]  # per-session durations in seconds

    @property
    def duration_avg(self): return float(np.mean(self.raw_duration))
    @property
    def duration_std(self): return float(np.std(self.raw_duration, ddof=1)) if len(self.raw_duration) > 1 else 0.0


# ── RunMetric payload ────────────────────────────────────────────────────────

class RunMetric(BaseModel):
    dataset_name: str
    eval_run_id: str
    llm_model: str
    n_queries: int
    agent_type: str

    # GEval metrics
    raw_correctness: list[float]
    raw_relevancy: list[float]
    raw_completeness: list[float]
    passrate: float

    # RougeL metrics
    raw_rouge_precision: list[float] = []
    raw_rouge_recall: list[float] = []
    raw_rouge_fmeasure: list[float] = []

    # Self-consistency (one score per unique query)
    raw_self_consistency: list[float] = []

    # Token and time metrics
    token_metric: Optional[TokenMetric] = None
    time_metric: Optional[TimeMetric] = None

    @property
    def correctness_avg(self):
        return sum(self.raw_correctness) / len(self.raw_correctness) if self.raw_correctness else 0.0
    @property
    def correctness_std(self):
        return float(np.std(self.raw_correctness, ddof=1)) if len(self.raw_correctness) > 1 else 0.0

    @property
    def relevancy_avg(self):
        return sum(self.raw_relevancy) / len(self.raw_relevancy) if self.raw_relevancy else 0.0
    @property
    def relevancy_std(self):
        return float(np.std(self.raw_relevancy, ddof=1)) if len(self.raw_relevancy) > 1 else 0.0

    @property
    def completeness_avg(self):
        return sum(self.raw_completeness) / len(self.raw_completeness) if self.raw_completeness else 0.0
    @property
    def completeness_std(self):
        return float(np.std(self.raw_completeness, ddof=1)) if len(self.raw_completeness) > 1 else 0.0

    @property
    def rouge_precision_avg(self): return float(np.mean(self.raw_rouge_precision)) if self.raw_rouge_precision else 0.0
    @property
    def rouge_precision_std(self): return float(np.std(self.raw_rouge_precision, ddof=1)) if len(self.raw_rouge_precision) > 1 else 0.0
    @property
    def rouge_recall_avg(self): return float(np.mean(self.raw_rouge_recall)) if self.raw_rouge_recall else 0.0
    @property
    def rouge_recall_std(self): return float(np.std(self.raw_rouge_recall, ddof=1)) if len(self.raw_rouge_recall) > 1 else 0.0
    @property
    def rouge_fmeasure_avg(self): return float(np.mean(self.raw_rouge_fmeasure)) if self.raw_rouge_fmeasure else 0.0
    @property
    def rouge_fmeasure_std(self): return float(np.std(self.raw_rouge_fmeasure, ddof=1)) if len(self.raw_rouge_fmeasure) > 1 else 0.0

    @property
    def self_consistency_avg(self): return float(np.mean(self.raw_self_consistency)) if self.raw_self_consistency else 0.0
    @property
    def self_consistency_std(self): return float(np.std(self.raw_self_consistency, ddof=1)) if len(self.raw_self_consistency) > 1 else 0.0

# ── ReferenceMetric payload ──────────────────────────────────────────────────

class ReferenceMetric(BaseModel):
    query_id: str
    name: str
    agent_type: Optional[str] = None
    dataset_name: Optional[str] = None
    llm_model: Optional[str] = None
    raw_rouge_precision: list[float]
    raw_rouge_recall: list[float]
    raw_rouge_fmeasure: list[float]
    actual_outputs: list[str] = Field(default_factory=list)
    self_consistency: Optional[float] = None

    @property
    def rouge_precision_avg(self): return float(np.mean(self.raw_rouge_precision)) if self.raw_rouge_precision else 0.0
    @property
    def rouge_precision_std(self): return float(np.std(self.raw_rouge_precision, ddof=1)) if len(self.raw_rouge_precision) > 1 else 0.0
    @property
    def rouge_recall_avg(self): return float(np.mean(self.raw_rouge_recall)) if self.raw_rouge_recall else 0.0
    @property
    def rouge_recall_std(self): return float(np.std(self.raw_rouge_recall, ddof=1)) if len(self.raw_rouge_recall) > 1 else 0.0
    @property
    def rouge_fmeasure_avg(self): return float(np.mean(self.raw_rouge_fmeasure)) if self.raw_rouge_fmeasure else 0.0
    @property
    def rouge_fmeasure_std(self): return float(np.std(self.raw_rouge_fmeasure, ddof=1)) if len(self.raw_rouge_fmeasure) > 1 else 0.0


# ── ResourceMetric payload ────────────────────────────────────────────────────

class ResourceMetric(BaseModel):
    agent_type: Optional[str] = None
    dataset_name: Optional[str] = None
    llm_model: Optional[str] = None
    raw_input_tokens: list[int] = Field(default_factory=list)
    raw_output_tokens: list[int] = Field(default_factory=list)
    raw_total_tokens: list[int] = Field(default_factory=list)
    raw_llm_calls: list[int] = Field(default_factory=list)
    raw_duration: list[float] = Field(default_factory=list)

    @property
    def input_tokens_avg(self): return float(np.mean(self.raw_input_tokens)) if self.raw_input_tokens else 0.0
    @property
    def input_tokens_std(self): return float(np.std(self.raw_input_tokens, ddof=1)) if len(self.raw_input_tokens) > 1 else 0.0
    @property
    def output_tokens_avg(self): return float(np.mean(self.raw_output_tokens)) if self.raw_output_tokens else 0.0
    @property
    def output_tokens_std(self): return float(np.std(self.raw_output_tokens, ddof=1)) if len(self.raw_output_tokens) > 1 else 0.0
    @property
    def total_tokens_avg(self): return float(np.mean(self.raw_total_tokens)) if self.raw_total_tokens else 0.0
    @property
    def total_tokens_std(self): return float(np.std(self.raw_total_tokens, ddof=1)) if len(self.raw_total_tokens) > 1 else 0.0
    @property
    def llm_calls_avg(self): return float(np.mean(self.raw_llm_calls)) if self.raw_llm_calls else 0.0
    @property
    def llm_calls_std(self): return float(np.std(self.raw_llm_calls, ddof=1)) if len(self.raw_llm_calls) > 1 else 0.0
    @property
    def duration_avg(self): return float(np.mean(self.raw_duration)) if self.raw_duration else 0.0
    @property
    def duration_std(self): return float(np.std(self.raw_duration, ddof=1)) if len(self.raw_duration) > 1 else 0.0


# ── TurnMetric payload ────────────────────────────────────────────────────────

class TurnMetric(BaseModel):
    query_id: str
    name: str
    agent_type: Optional[str] = None
    dataset_name: Optional[str] = None
    llm_model: Optional[str] = None
    raw_correctness: list[float]
    raw_relevancy: list[float]
    raw_completeness: list[float]
    success_count: int
    n : int
    actual_outputs: list[str] = Field(default_factory=list)
    self_consistency: Optional[float] = None

    @property
    def passrate(self):
        return self.success_count / self.n if self.n > 0 else 0.0

    @property
    def correctness_avg(self):
        return sum(self.raw_correctness) / len(self.raw_correctness) if self.raw_correctness else 0.0
    @property
    def correctness_std(self):
        if not self.raw_correctness or len(self.raw_correctness) <= 1:
            return 0.0
        return np.std(self.raw_correctness, ddof=1)  

    @property
    def relevancy_avg(self):
        return sum(self.raw_relevancy) / len(self.raw_relevancy) if self.raw_relevancy else 0.0
    @property
    def relevancy_std(self):
        if not self.raw_relevancy or len(self.raw_relevancy) <= 1:
            return 0.0
        return np.std(self.raw_relevancy, ddof=1)  

    @property
    def completeness_avg(self):
        return sum(self.raw_completeness) / len(self.raw_completeness) if self.raw_completeness else 0.0
    @property
    def completeness_std(self):
        if not self.raw_completeness or len(self.raw_completeness) <= 1:
            return 0.0
        return np.std(self.raw_completeness, ddof=1) 

