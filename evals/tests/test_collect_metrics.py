"""Tests for CollectMetrics.

CollectMetrics is currently defined in eval_analysis.ipynb.
These tests assume it has been extracted to evals/src/evals/collect_metrics.py.

All tests in this file are skipped automatically until that module exists.
Once extracted, remove or update the importorskip call at the top.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# All tests skip until CollectMetrics is extracted from the notebook.
collect_metrics_mod = pytest.importorskip(
    "evals.collect_metrics",
    reason="CollectMetrics not yet extracted from eval_analysis.ipynb to evals/src/evals/collect_metrics.py",
)
CollectMetrics = collect_metrics_mod.CollectMetrics

from evals.models import (
    ConversationTurn,
    DeepEvalObservation,
    GatheredResultPayload,
    ResourceObservation,
    RougeObservation,
    Session,
    TimeCount,
    TokenCount,
)

_DT = datetime(2024, 1, 15, 10, 0, 0)
_DT2 = datetime(2024, 1, 15, 10, 0, 30)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cm():
    """CollectMetrics instance with SentenceTransformer mocked out."""
    mock_st = MagicMock()
    mock_st.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
    with patch("evals.collect_metrics.SentenceTransformer", return_value=mock_st):
        obj = CollectMetrics()
    obj.sentence_transformer = mock_st
    return obj


# ── Helpers for building fake deepeval structures ─────────────────────────────


def _metric_data(name: str, score: float) -> MagicMock:
    m = MagicMock()
    m.name = name
    m.score = score
    return m


def _test_result(
    name: str = "Turn 1 in session S1",
    query_id: str = "q-1",
    session_id: str = "sess-1",
    correctness: float = 0.9,
    relevancy: float = 0.8,
    completeness: float = 0.7,
    success: bool = True,
    expected_output: str = "Expected answer.",
    actual_output: str = "Actual answer.",
) -> MagicMock:
    tr = MagicMock()
    tr.name = name
    tr.success = success
    tr.expected_output = expected_output
    tr.actual_output = actual_output
    tr.additional_metadata = {"query_id": query_id, "session_id": session_id}
    tr.metrics_data = [
        _metric_data("correctness [GEval]", correctness),
        _metric_data("relevancy", relevancy),
        _metric_data("completeness [GEval]", completeness),
    ]
    return tr


def _eval_result(test_results: list) -> MagicMock:
    er = MagicMock()
    er.test_results = test_results
    return er


def _eval_output(
    dataset_name: str = "THRD",
    eval_run_id: str = "run-1",
    llm_model: str = "gpt-4o",
    agent_type: str = "baseline",
    test_results: list = None,
) -> MagicMock:
    eo = MagicMock()
    eo.dataset_name = dataset_name
    eo.eval_run_id = eval_run_id
    eo.llm_model = llm_model
    eo.agent_type = agent_type
    eo.results = [_eval_result(test_results or [_test_result()])]
    return eo


def _gathered(
    dataset_name: str = "THRD",
    eval_run_id: str = "run-1",
    llm_model: str = "gpt-4o",
    agent_type: str = "baseline",
    sessions: list = None,
) -> GatheredResultPayload:
    tc = TokenCount(input_tokens=10, output_tokens=5, total_tokens=15, llm_calls=1)
    time = TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=30.0)
    turn = ConversationTurn(
        input="Q",
        answer="A",
        order=1,
        query_id="q-1",
        model_response="M",
        token_counts=tc,
        time_counts=time,
    )
    session = Session(
        session_name="S1",
        date="2024-01-15",
        init_query="Init",
        conversation=[turn],
        runtime_session_id="sess-1",
    )
    return GatheredResultPayload(
        dataset_name=dataset_name,
        project_id="p",
        user_id="u",
        sessions=sessions or [session],
        eval_run_id=eval_run_id,
        llm_model=llm_model,
        agent_type=agent_type,
        runtime_project_id="p",
    )


# ── _extract_run_type ──────────────────────────────────────────────────────────


class TestExtractRunType:
    @pytest.mark.parametrize(
        "path,expected",
        [
            (
                "datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_abc123.json",
                "gpt-4o_baseline",
            ),
            (
                "datasets/THRD/05_evals/llm-as-judge_gpt-4o_custom_abc123.json",
                "gpt-4o_custom",
            ),
            (
                "datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_rag_abc123.json",
                "gpt-4o_baseline_rag",
            ),
            (
                "datasets/THRD/05_evals/llm-as-judge_google_gemini-2.5-flash_baseline_abc123.json",
                "google_gemini-2.5-flash_baseline",
            ),
        ],
    )
    def test_extracts_run_type(self, cm, path, expected):
        assert cm._extract_run_type(path) == expected


# ── organize_runs_by_type ─────────────────────────────────────────────────────


class TestOrganizeRunsByType:
    def test_groups_by_run_type(self, cm):
        eo_a1 = _eval_output(agent_type="baseline")
        eo_a2 = _eval_output(eval_run_id="run-2", agent_type="baseline")
        eo_b = _eval_output(agent_type="custom")

        eval_res = {
            "datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_run-1.json": eo_a1,
            "datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_run-2.json": eo_a2,
            "datasets/THRD/05_evals/llm-as-judge_gpt-4o_custom_run-3.json": eo_b,
        }
        result = cm.organize_runs_by_type(eval_res)

        assert "gpt-4o_baseline" in result
        assert "gpt-4o_custom" in result
        assert len(result["gpt-4o_baseline"]) == 2
        assert len(result["gpt-4o_custom"]) == 1

    def test_empty_input_returns_empty_dict(self, cm):
        assert cm.organize_runs_by_type({}) == {}

    def test_single_run(self, cm):
        eo = _eval_output()
        result = cm.organize_runs_by_type(
            {"datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_run-1.json": eo}
        )
        assert len(result) == 1
        assert result["gpt-4o_baseline"] == [eo]


# ── _extract_query_metrics ────────────────────────────────────────────────────


class TestExtractQueryMetrics:
    def test_extracts_all_three_metrics(self, cm):
        query = _test_result(correctness=0.9, relevancy=0.8, completeness=0.7)
        metrics = cm._extract_query_metrics(query)
        assert metrics["correctness"] == pytest.approx(0.9)
        assert metrics["relevancy"] == pytest.approx(0.8)
        assert metrics["completeness"] == pytest.approx(0.7)

    def test_defaults_to_zero_for_missing_metrics(self, cm):
        query = MagicMock()
        query.metrics_data = []
        metrics = cm._extract_query_metrics(query)
        assert metrics["correctness"] == 0.0
        assert metrics["relevancy"] == 0.0
        assert metrics["completeness"] == 0.0

    def test_ignores_unknown_metric_names(self, cm):
        query = MagicMock()
        query.metrics_data = [_metric_data("unknown_metric", 0.5)]
        metrics = cm._extract_query_metrics(query)
        assert metrics["correctness"] == 0.0
        assert metrics["relevancy"] == 0.0
        assert metrics["completeness"] == 0.0

    def test_partial_metrics(self, cm):
        query = MagicMock()
        query.metrics_data = [_metric_data("correctness [GEval]", 0.6)]
        metrics = cm._extract_query_metrics(query)
        assert metrics["correctness"] == pytest.approx(0.6)
        assert metrics["relevancy"] == 0.0
        assert metrics["completeness"] == 0.0


# ── self_consistency_score ────────────────────────────────────────────────────


class TestSelfConsistencyScore:
    def test_empty_list_returns_one(self, cm):
        assert cm.self_consistency_score([]) == 1.0

    def test_single_output_returns_one(self, cm):
        assert cm.self_consistency_score(["only one output"]) == 1.0

    def test_identical_embeddings_return_one(self, cm):
        cm.sentence_transformer.encode.return_value = np.array([[1.0, 0.0], [1.0, 0.0]])
        score = cm.self_consistency_score(["output a", "output a"])
        assert score == pytest.approx(1.0)

    def test_orthogonal_embeddings_return_zero(self, cm):
        cm.sentence_transformer.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
        score = cm.self_consistency_score(["output a", "output b"])
        assert score == pytest.approx(0.0)

    def test_returns_mean_of_upper_triangle(self, cm):
        # Three outputs: sim(0,1)=1.0, sim(0,2)=0.0, sim(1,2)=0.0 → mean ≈ 0.333
        cm.sentence_transformer.encode.return_value = np.array(
            [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        )
        score = cm.self_consistency_score(["a", "b", "c"])
        assert score == pytest.approx(1 / 3, abs=1e-6)


# ── _rouge_l ──────────────────────────────────────────────────────────────────


class TestRougeL:
    def test_identical_texts_return_one(self, cm):
        text = "The defendant breached the contract."
        score = cm._rouge_l(text, text)
        assert score["rougeL"].fmeasure == pytest.approx(1.0)
        assert score["rougeL"].precision == pytest.approx(1.0)
        assert score["rougeL"].recall == pytest.approx(1.0)

    def test_empty_actual_returns_zero(self, cm):
        score = cm._rouge_l("expected text here", "")
        assert score["rougeL"].fmeasure == pytest.approx(0.0)
        assert score["rougeL"].recall == pytest.approx(0.0)

    def test_partial_overlap_between_zero_and_one(self, cm):
        score = cm._rouge_l("the cat sat on the mat", "the cat")
        assert 0.0 < score["rougeL"].fmeasure < 1.0

    def test_returns_rougeL_key(self, cm):
        score = cm._rouge_l("some text", "some text")
        assert "rougeL" in score


# ── collect_deepeval_metrics ──────────────────────────────────────────────────


class TestCollectDeepEvalMetrics:
    def test_returns_one_observation_per_test_result(self, cm):
        tr1 = _test_result(name="T1", query_id="q-1", correctness=0.9, relevancy=0.8, completeness=0.7, success=True)
        tr2 = _test_result(name="T2", query_id="q-2", correctness=0.5, relevancy=0.6, completeness=0.4, success=False)
        runs = [_eval_output(test_results=[tr1, tr2])]
        obs = cm.collect_deepeval_metrics(runs)
        assert len(obs) == 2

    def test_observation_fields_are_populated(self, cm):
        tr = _test_result(
            name="Turn 1",
            query_id="q-99",
            session_id="sess-42",
            correctness=0.9,
            relevancy=0.8,
            completeness=0.7,
            success=True,
        )
        run = _eval_output(
            dataset_name="THRD", eval_run_id="run-X", llm_model="gpt-4o", agent_type="baseline",
            test_results=[tr],
        )
        obs = cm.collect_deepeval_metrics([run])
        assert len(obs) == 1
        o = obs[0]
        assert isinstance(o, DeepEvalObservation)
        assert o.dataset_name == "THRD"
        assert o.eval_run_id == "run-X"
        assert o.query_id == "q-99"
        assert o.session_id == "sess-42"
        assert o.llm_model == "gpt-4o"
        assert o.agent_type == "baseline"
        assert o.name == "Turn 1"
        assert o.correctness == pytest.approx(0.9)
        assert o.relevancy == pytest.approx(0.8)
        assert o.completeness == pytest.approx(0.7)
        assert o.success is True

    def test_empty_runs_returns_empty_list(self, cm):
        assert cm.collect_deepeval_metrics([]) == []

    def test_multiple_runs_are_flattened(self, cm):
        runs = [
            _eval_output(eval_run_id="run-1", test_results=[_test_result()]),
            _eval_output(eval_run_id="run-2", test_results=[_test_result(), _test_result()]),
        ]
        obs = cm.collect_deepeval_metrics(runs)
        assert len(obs) == 3


# ── collect_reference_metrics ─────────────────────────────────────────────────


class TestCollectReferenceMetrics:
    def test_returns_one_observation_per_test_result(self, cm):
        runs = [_eval_output(test_results=[_test_result(), _test_result()])]
        obs = cm.collect_reference_metrics(runs)
        assert len(obs) == 2

    def test_observation_type_is_rouge(self, cm):
        runs = [_eval_output(test_results=[_test_result()])]
        obs = cm.collect_reference_metrics(runs)
        assert isinstance(obs[0], RougeObservation)

    def test_rouge_scores_are_valid_floats(self, cm):
        tr = _test_result(
            expected_output="The defendant is liable.",
            actual_output="The defendant is liable.",
        )
        runs = [_eval_output(test_results=[tr])]
        obs = cm.collect_reference_metrics(runs)
        o = obs[0]
        assert 0.0 <= o.rouge_precision <= 1.0
        assert 0.0 <= o.rouge_recall <= 1.0
        assert 0.0 <= o.rouge_fmeasure <= 1.0

    def test_identical_outputs_yield_high_fmeasure(self, cm):
        text = "The plaintiff claims damages of 100 000 NOK."
        tr = _test_result(expected_output=text, actual_output=text)
        runs = [_eval_output(test_results=[tr])]
        obs = cm.collect_reference_metrics(runs)
        assert obs[0].rouge_fmeasure == pytest.approx(1.0)

    def test_actual_output_stored_verbatim(self, cm):
        tr = _test_result(actual_output="verbatim agent response")
        runs = [_eval_output(test_results=[tr])]
        obs = cm.collect_reference_metrics(runs)
        assert obs[0].actual_output == "verbatim agent response"

    def test_empty_runs_returns_empty_list(self, cm):
        assert cm.collect_reference_metrics([]) == []


# ── collect_resource_metrics ──────────────────────────────────────────────────


class TestCollectResourceMetrics:
    def test_returns_one_observation_per_turn_with_counts(self, cm):
        run = _gathered()
        obs = cm.collect_resource_metrics([run])
        assert len(obs) == 1

    def test_observation_type_is_resource(self, cm):
        run = _gathered()
        obs = cm.collect_resource_metrics([run])
        assert isinstance(obs[0], ResourceObservation)

    def test_observation_fields_match_turn(self, cm):
        run = _gathered(dataset_name="THRD", eval_run_id="run-42", llm_model="gpt-4o")
        obs = cm.collect_resource_metrics([run])
        o = obs[0]
        assert o.dataset_name == "THRD"
        assert o.eval_run_id == "run-42"
        assert o.llm_model == "gpt-4o"
        assert o.query_id == "q-1"
        assert o.session_id == "sess-1"
        assert o.input_tokens == 10
        assert o.output_tokens == 5
        assert o.total_tokens == 15
        assert o.llm_calls == 1
        assert o.duration_seconds == pytest.approx(30.0)

    def test_skips_turns_without_token_counts(self, cm):
        turn = ConversationTurn(
            input="Q", answer="A", order=1, query_id="q-1", model_response="M",
            token_counts=None,
            time_counts=TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=5.0),
        )
        session = Session(
            session_name="S1", date="2024-01-15", init_query="Init",
            conversation=[turn], runtime_session_id="sess-1",
        )
        run = GatheredResultPayload(
            dataset_name="D", project_id="p", user_id="u", sessions=[session],
            eval_run_id="r", llm_model="m", agent_type="baseline", runtime_project_id="p",
        )
        obs = cm.collect_resource_metrics([run])
        assert obs == []

    def test_skips_turns_without_time_counts(self, cm):
        turn = ConversationTurn(
            input="Q", answer="A", order=1, query_id="q-1", model_response="M",
            token_counts=TokenCount(input_tokens=1, output_tokens=1, total_tokens=2, llm_calls=1),
            time_counts=None,
        )
        session = Session(
            session_name="S1", date="2024-01-15", init_query="Init",
            conversation=[turn], runtime_session_id="sess-1",
        )
        run = GatheredResultPayload(
            dataset_name="D", project_id="p", user_id="u", sessions=[session],
            eval_run_id="r", llm_model="m", agent_type="baseline", runtime_project_id="p",
        )
        obs = cm.collect_resource_metrics([run])
        assert obs == []

    def test_multiple_sessions_and_turns(self, cm):
        tc = TokenCount(input_tokens=1, output_tokens=1, total_tokens=2, llm_calls=1)
        time = TimeCount(starttime=_DT, endtime=_DT2, duration_seconds=1.0)

        def _turn(qid):
            return ConversationTurn(
                input="Q", answer="A", order=1, query_id=qid,
                model_response="M", token_counts=tc, time_counts=time,
            )

        sessions = [
            Session(session_name="S1", date="2024-01-15", init_query="Init",
                    conversation=[_turn("q-1"), _turn("q-2")], runtime_session_id="sess-1"),
            Session(session_name="S2", date="2024-02-15", init_query="Init",
                    conversation=[_turn("q-3")], runtime_session_id="sess-2"),
        ]
        run = GatheredResultPayload(
            dataset_name="D", project_id="p", user_id="u", sessions=sessions,
            eval_run_id="r", llm_model="m", agent_type="baseline", runtime_project_id="p",
        )
        obs = cm.collect_resource_metrics([run])
        assert len(obs) == 3

    def test_empty_runs_returns_empty_list(self, cm):
        assert cm.collect_resource_metrics([]) == []
