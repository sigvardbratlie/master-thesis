"""Tests for evals.models Pydantic models."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from evals.models import (
    BaseMetric,
    ConversationTurn,
    DatasetPayload,
    DeepEvalObservation,
    EvalOutput,
    GatheredResultPayload,
    ResourceObservation,
    RougeObservation,
    Session,
    TimeCount,
    TokenCount,
)

_DT = datetime(2024, 1, 15, 10, 0, 0)
_DT2 = datetime(2024, 1, 15, 10, 0, 30)


# ── TokenCount ────────────────────────────────────────────────────────────────


class TestTokenCount:
    def test_valid(self):
        tc = TokenCount(input_tokens=100, output_tokens=50, total_tokens=150, llm_calls=2)
        assert tc.input_tokens == 100
        assert tc.output_tokens == 50
        assert tc.total_tokens == 150
        assert tc.llm_calls == 2

    def test_zero_values_accepted(self):
        tc = TokenCount(input_tokens=0, output_tokens=0, total_tokens=0, llm_calls=0)
        assert tc.total_tokens == 0

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            TokenCount(input_tokens=100, output_tokens=50)  # missing total_tokens and llm_calls


# ── TimeCount ─────────────────────────────────────────────────────────────────


class TestTimeCount:
    def test_valid(self):
        tc = TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=30.0)
        assert tc.starttime == _DT
        assert tc.endtime == _DT2
        assert tc.duration_seconds == 30.0

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            TimeCount(starttime=_DT, endtime=_DT2)  # missing duration_seconds


# ── ConversationTurn ──────────────────────────────────────────────────────────


class TestConversationTurn:
    def test_minimal(self):
        t = ConversationTurn(input="What is the claim?", answer="The claim is X.")
        assert t.order is None
        assert t.query_id is None
        assert t.model_response is None
        assert t.token_counts is None
        assert t.time_counts is None

    def test_with_all_optional_fields(self):
        tc = TokenCount(input_tokens=10, output_tokens=5, total_tokens=15, llm_calls=1)
        time = TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=30.0)
        t = ConversationTurn(
            input="Q",
            answer="A",
            order=3,
            query_id="q-abc",
            model_response="Agent response",
            token_counts=tc,
            time_counts=time,
        )
        assert t.order == 3
        assert t.query_id == "q-abc"
        assert t.model_response == "Agent response"
        assert t.token_counts.total_tokens == 15
        assert t.time_counts.duration_seconds == 30.0

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            ConversationTurn(input="Q")  # missing answer


# ── Session ───────────────────────────────────────────────────────────────────


class TestSession:
    def test_minimal(self):
        s = Session(session_name="S1", date="2024-01-15", init_query="Init", conversation=[])
        assert s.attachments == []
        assert s.runtime_session_id is None
        assert s.time_counts is None

    def test_with_conversation(self):
        turn = ConversationTurn(input="Q", answer="A")
        s = Session(
            session_name="S1", date="2024-01-15", init_query="Init", conversation=[turn]
        )
        assert len(s.conversation) == 1
        assert s.conversation[0].input == "Q"

    def test_with_attachments(self):
        s = Session(
            session_name="S1",
            date="2024-01-15",
            init_query="Init",
            conversation=[],
            attachments=["datasets/X/01_data/2024-01-15_doc.pdf"],
        )
        assert len(s.attachments) == 1

    def test_runtime_fields_can_be_set(self):
        s = Session(
            session_name="S1",
            date="2024-01-15",
            init_query="Init",
            conversation=[],
            runtime_session_id="sess-99",
            time_counts=TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=30.0),
        )
        assert s.runtime_session_id == "sess-99"
        assert s.time_counts.duration_seconds == 30.0

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Session(session_name="S1", date="2024-01-15", conversation=[])  # missing init_query


# ── DatasetPayload ────────────────────────────────────────────────────────────


class TestDatasetPayload:
    def test_valid(self):
        dp = DatasetPayload(
            dataset_name="THRD-2021",
            project_id="proj-1",
            user_id="user-1",
            sessions=[],
        )
        assert dp.dataset_name == "THRD-2021"
        assert dp.sessions == []

    def test_with_sessions(self):
        session = Session(session_name="S1", date="2024-01-15", init_query="Init", conversation=[])
        dp = DatasetPayload(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[session],
        )
        assert len(dp.sessions) == 1

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            DatasetPayload(project_id="p", user_id="u", sessions=[])  # missing dataset_name


# ── GatheredResultPayload ─────────────────────────────────────────────────────


class TestGatheredResultPayload:
    def _build(self, **kw):
        defaults = dict(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[],
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="custom",
            runtime_project_id="p",
        )
        return GatheredResultPayload(**{**defaults, **kw})

    @pytest.mark.parametrize("agent_type", ["custom", "baseline", "baseline_rag"])
    def test_valid_agent_types(self, agent_type):
        grp = self._build(agent_type=agent_type)
        assert grp.agent_type == agent_type

    def test_invalid_agent_type_raises(self):
        with pytest.raises(ValidationError):
            self._build(agent_type="unknown_type")

    def test_optional_fields_default_none(self):
        grp = self._build()
        assert grp.token_counts is None
        assert grp.time_counts is None

    def test_with_token_and_time_counts(self):
        tc = TokenCount(input_tokens=100, output_tokens=50, total_tokens=150, llm_calls=3)
        time = TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=30.0)
        grp = self._build(token_counts=tc, time_counts=time)
        assert grp.token_counts.llm_calls == 3
        assert grp.time_counts.duration_seconds == 30.0

    def test_runtime_project_id_differs_for_baseline(self):
        """Verify the model stores runtime_project_id independently of project_id."""
        grp = self._build(project_id="proj-A", runtime_project_id="proj-A_baseline")
        assert grp.runtime_project_id == "proj-A_baseline"
        assert grp.project_id == "proj-A"


# ── EvalOutput ────────────────────────────────────────────────────────────────


class TestEvalOutput:
    def test_defaults(self):
        eo = EvalOutput(created_at="2024-01-15T10:00:00")
        assert eo.agent_type == "unknown"
        assert eo.results is None
        assert eo.dataset_name is None

    def test_all_optional_fields(self):
        eo = EvalOutput(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
            created_at="2024-01-15T10:00:00",
        )
        assert eo.dataset_name == "THRD"
        assert eo.eval_run_id == "run-1"

    def test_missing_created_at_raises(self):
        with pytest.raises(ValidationError):
            EvalOutput()  # created_at is required


# ── BaseMetric ────────────────────────────────────────────────────────────────


class TestBaseMetric:
    def test_valid(self):
        bm = BaseMetric(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
        )
        assert bm.query_id is None
        assert bm.session_id is None

    def test_with_optional_ids(self):
        bm = BaseMetric(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
            query_id="q-1",
            session_id="sess-1",
        )
        assert bm.query_id == "q-1"
        assert bm.session_id == "sess-1"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            BaseMetric(dataset_name="THRD")  # missing eval_run_id, llm_model, agent_type


# ── DeepEvalObservation ───────────────────────────────────────────────────────


class TestDeepEvalObservation:
    def test_valid(self):
        obs = DeepEvalObservation(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
            correctness=0.9,
            relevancy=0.8,
            completeness=0.7,
            success=True,
        )
        assert obs.name is None
        assert obs.success is True
        assert obs.correctness == pytest.approx(0.9)
        assert obs.relevancy == pytest.approx(0.8)
        assert obs.completeness == pytest.approx(0.7)

    def test_with_name(self):
        obs = DeepEvalObservation(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="m",
            agent_type="custom",
            correctness=0.0,
            relevancy=0.0,
            completeness=0.0,
            success=False,
            name="Turn 1 in session S1",
        )
        assert obs.name == "Turn 1 in session S1"

    def test_missing_score_field_raises(self):
        with pytest.raises(ValidationError):
            DeepEvalObservation(
                dataset_name="THRD",
                eval_run_id="run-1",
                llm_model="m",
                agent_type="baseline",
                correctness=0.9,
                # missing relevancy, completeness, success
            )


# ── RougeObservation ──────────────────────────────────────────────────────────


class TestRougeObservation:
    def test_valid(self):
        obs = RougeObservation(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
            rouge_precision=0.5,
            rouge_recall=0.6,
            rouge_fmeasure=0.55,
            actual_output="The agent's answer.",
        )
        assert obs.rouge_precision == pytest.approx(0.5)
        assert obs.rouge_recall == pytest.approx(0.6)
        assert obs.rouge_fmeasure == pytest.approx(0.55)
        assert obs.actual_output == "The agent's answer."
        assert obs.name is None

    def test_missing_score_raises(self):
        with pytest.raises(ValidationError):
            RougeObservation(
                dataset_name="THRD",
                eval_run_id="run-1",
                llm_model="m",
                agent_type="baseline",
                actual_output="x",
                # missing rouge_precision, rouge_recall, rouge_fmeasure
            )


# ── ResourceObservation ───────────────────────────────────────────────────────


class TestResourceObservation:
    def test_valid(self):
        obs = ResourceObservation(
            dataset_name="THRD",
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            llm_calls=2,
            starttime=_DT,
            endtime=_DT2,
            duration_seconds=30.0,
        )
        assert obs.total_tokens == 150
        assert obs.llm_calls == 2
        assert obs.duration_seconds == 30.0
        assert obs.dataset_name == "THRD"

    def test_inherits_all_three_parents(self):
        """ResourceObservation must satisfy BaseMetric, TokenCount, and TimeCount."""
        obs = ResourceObservation(
            dataset_name="D",
            eval_run_id="r",
            llm_model="m",
            agent_type="custom",
            query_id="q-1",
            session_id="s-1",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            llm_calls=0,
            starttime=_DT,
            endtime=_DT2,
            duration_seconds=0.0,
        )
        # BaseMetric fields
        assert obs.query_id == "q-1"
        assert obs.session_id == "s-1"
        # TokenCount fields
        assert obs.input_tokens == 0
        # TimeCount fields
        assert obs.starttime == _DT

    def test_missing_token_fields_raises(self):
        with pytest.raises(ValidationError):
            ResourceObservation(
                dataset_name="THRD",
                eval_run_id="run-1",
                llm_model="m",
                agent_type="baseline",
                starttime=_DT,
                endtime=_DT2,
                duration_seconds=30.0,
                # missing input_tokens, output_tokens, total_tokens, llm_calls
            )

    def test_missing_time_fields_raises(self):
        with pytest.raises(ValidationError):
            ResourceObservation(
                dataset_name="THRD",
                eval_run_id="run-1",
                llm_model="m",
                agent_type="baseline",
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                llm_calls=0,
                # missing starttime, endtime, duration_seconds
            )
