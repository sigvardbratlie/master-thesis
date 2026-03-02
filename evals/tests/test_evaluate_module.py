"""Tests for evals.evaluate_module.Evaluater and related Dataset methods.

Also covers Dataset methods not present in test_dataset.py:
  - load_results
  - load_evaluation_results
  - save_evaluation_results
  - assign_session_attachments_baseline
"""
import json
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from evals.dataset_module import Dataset
from evals.evaluate_module import Evaluater
from evals.models import (
    ConversationTurn,
    EvalOutput,
    GatheredResultPayload,
    Session,
    TimeCount,
    TokenCount,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def ev():
    return Evaluater(client=MagicMock())


@pytest.fixture
def mock_bucket():
    return MagicMock()


@pytest.fixture
def ds(mock_bucket):
    client = MagicMock()
    client.bucket.return_value = mock_bucket
    return Dataset(name="THRD", client=client)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _turn(
    input_text: str = "What is the claim?",
    answer: str = "The claim is X.",
    model_response: str = "The agent says X.",
    order: int = 1,
    query_id: str = "q-1",
) -> ConversationTurn:
    return ConversationTurn(
        input=input_text,
        answer=answer,
        model_response=model_response,
        order=order,
        query_id=query_id,
    )


def _session(
    name: str = "S1",
    session_id: str = "sess-1",
    turns: list = None,
) -> Session:
    return Session(
        session_name=name,
        date="2024-01-15",
        init_query="Initial query",
        conversation=turns or [_turn()],
        runtime_session_id=session_id,
    )


def _gathered(n_sessions: int = 1, agent_type: str = "baseline") -> GatheredResultPayload:
    return GatheredResultPayload(
        dataset_name="THRD",
        project_id="proj-1",
        user_id="user-1",
        sessions=[_session(f"S{i}", f"sess-{i}") for i in range(n_sessions)],
        eval_run_id="run-1",
        llm_model="gpt-4o",
        agent_type=agent_type,
        runtime_project_id="proj-1",
    )


def _blob(name: str) -> MagicMock:
    b = MagicMock()
    b.name = name
    return b


# ── Evaluater.collect_single ──────────────────────────────────────────────────


class TestCollectSingle:
    def test_returns_test_case_when_all_fields_present(self, ev):
        turn = _turn()
        tc = ev.collect_single(turn, session_name="S1", session_id="sess-1")
        assert tc is not None
        assert tc.input == "What is the claim?"
        assert tc.actual_output == "The agent says X."
        assert tc.expected_output == "The claim is X."

    def test_name_contains_order_and_session_name(self, ev):
        turn = _turn(order=5)
        tc = ev.collect_single(turn, session_name="MySession", session_id="sess-1")
        assert "5" in tc.name
        assert "MySession" in tc.name

    def test_metadata_fields_are_populated(self, ev):
        turn = _turn(order=2, query_id="q-42")
        tc = ev.collect_single(turn, session_name="S1", session_id="sess-99")
        assert tc.additional_metadata["query_id"] == "q-42"
        assert tc.additional_metadata["session_name"] == "S1"
        assert tc.additional_metadata["session_id"] == "sess-99"
        assert tc.additional_metadata["turn_order"] == 2

    def test_missing_input_returns_none(self, ev):
        turn = ConversationTurn(input="", answer="A", model_response="M")
        assert ev.collect_single(turn) is None

    def test_missing_model_response_returns_none(self, ev):
        turn = ConversationTurn(input="Q", answer="A")  # model_response defaults to None
        assert ev.collect_single(turn) is None

    def test_missing_answer_returns_none(self, ev):
        turn = ConversationTurn(input="Q", answer="", model_response="M")
        assert ev.collect_single(turn) is None

    def test_defaults_for_session_args(self, ev):
        """collect_single should not crash when session args are omitted."""
        turn = _turn()
        tc = ev.collect_single(turn)
        assert tc is not None
        assert tc.additional_metadata["session_name"] == "unknown"
        assert tc.additional_metadata["session_id"] == "unknown"


# ── Evaluater.run_session_eval ────────────────────────────────────────────────


class TestRunSessionEval:
    def test_calls_evaluate_with_collected_test_cases(self, ev):
        session = _session(turns=[_turn(order=1), _turn(order=2)])
        mock_result = MagicMock()

        with (
            patch("evals.evaluate_module.evaluate", return_value=mock_result) as mock_eval,
            patch("evals.evaluate_module.GEval"),
            patch("evals.evaluate_module.AnswerRelevancyMetric"),
        ):
            result = ev.run_session_eval(session)

        assert result is mock_result
        mock_eval.assert_called_once()
        _, kwargs = mock_eval.call_args
        assert len(kwargs["test_cases"]) == 2

    def test_skips_turns_with_missing_fields(self, ev):
        incomplete = ConversationTurn(input="Q", answer="A")  # no model_response
        complete = _turn(order=2)
        session = _session(turns=[incomplete, complete])

        with (
            patch("evals.evaluate_module.evaluate") as mock_eval,
            patch("evals.evaluate_module.GEval"),
            patch("evals.evaluate_module.AnswerRelevancyMetric"),
        ):
            ev.run_session_eval(session)

        _, kwargs = mock_eval.call_args
        assert len(kwargs["test_cases"]) == 1

    def test_returns_evaluate_output(self, ev):
        session = _session()
        expected = MagicMock()

        with (
            patch("evals.evaluate_module.evaluate", return_value=expected),
            patch("evals.evaluate_module.GEval"),
            patch("evals.evaluate_module.AnswerRelevancyMetric"),
        ):
            result = ev.run_session_eval(session)

        assert result is expected


# ── Evaluater.run_evaluation ──────────────────────────────────────────────────


class TestRunEvaluation:
    def test_runs_for_every_session(self, ev):
        data = _gathered(n_sessions=3)
        mock_result = MagicMock()

        with patch.object(ev, "run_session_eval", return_value=mock_result) as mock_run:
            results = ev.run_evaluation(data)

        assert mock_run.call_count == 3
        assert results == [mock_result, mock_result, mock_result]

    def test_returns_list(self, ev):
        data = _gathered(n_sessions=1)

        with (
            patch("evals.evaluate_module.evaluate", return_value=MagicMock()),
            patch("evals.evaluate_module.GEval"),
            patch("evals.evaluate_module.AnswerRelevancyMetric"),
        ):
            results = ev.run_evaluation(data)

        assert isinstance(results, list)

    def test_empty_sessions_returns_empty_list(self, ev):
        data = _gathered(n_sessions=0)
        with patch.object(ev, "run_session_eval", return_value=MagicMock()):
            results = ev.run_evaluation(data)
        assert results == []


# ── Dataset.save_evaluation_results ──────────────────────────────────────────


class TestSaveEvaluationResults:
    def test_uploads_to_correct_gcs_path(self, ds, mock_bucket):
        data = _gathered()
        ds.save_evaluation_results(results=[], data=data)

        path = mock_bucket.blob.call_args[0][0]
        assert path.startswith("datasets/THRD/05_evals/")
        assert "run-1" in path
        assert path.endswith(".json")

    def test_path_includes_model_and_agent_type(self, ds, mock_bucket):
        data = _gathered()
        ds.save_evaluation_results(results=[], data=data)

        path = mock_bucket.blob.call_args[0][0]
        assert "gpt-4o" in path
        assert "baseline" in path

    def test_returns_eval_output_instance(self, ds, mock_bucket):
        data = _gathered()
        output = ds.save_evaluation_results(results=[], data=data)
        assert isinstance(output, EvalOutput)

    def test_eval_output_fields_match_gathered_payload(self, ds, mock_bucket):
        data = _gathered()
        output = ds.save_evaluation_results(results=[], data=data)
        assert output.dataset_name == "THRD"
        assert output.eval_run_id == "run-1"
        assert output.llm_model == "gpt-4o"
        assert output.agent_type == "baseline"
        assert output.project_id == "proj-1"
        assert output.user_id == "user-1"

    def test_empty_results_stored_as_none(self, ds, mock_bucket):
        """Empty list of EvaluationResult objects is stored as None (list comprehension filters them)."""
        data = _gathered()
        output = ds.save_evaluation_results(results=[], data=data)
        assert output.results is None


# ── Dataset.load_results ──────────────────────────────────────────────────────


class TestLoadResults:
    def _valid_payload(self) -> dict:
        return {
            "dataset_name": "THRD",
            "project_id": "p",
            "user_id": "u",
            "sessions": [],
            "eval_run_id": "run-1",
            "llm_model": "gpt-4o",
            "agent_type": "baseline",
            "runtime_project_id": "p",
        }

    def test_returns_gathered_result_payloads(self, ds, mock_bucket):
        blob = _blob("datasets/THRD/04_results/gpt-4o_baseline_run-1.json")
        blob.download_as_string.return_value = json.dumps(self._valid_payload()).encode()
        mock_bucket.list_blobs.return_value = [blob]

        results = ds.load_results()
        assert len(results) == 1
        key = list(results.keys())[0]
        assert isinstance(results[key], GatheredResultPayload)

    def test_empty_bucket_returns_empty_dict(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = []
        assert ds.load_results() == {}

    def test_non_json_files_are_skipped(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/04_results/readme.txt"),
        ]
        assert ds.load_results() == {}

    def test_invalid_json_is_skipped_and_others_loaded(self, ds, mock_bucket):
        good = _blob("datasets/THRD/04_results/good.json")
        good.download_as_string.return_value = json.dumps(self._valid_payload()).encode()
        bad = _blob("datasets/THRD/04_results/bad.json")
        bad.download_as_string.return_value = b"not valid json {"

        mock_bucket.list_blobs.return_value = [bad, good]
        results = ds.load_results()
        assert len(results) == 1


# ── Dataset.load_evaluation_results ──────────────────────────────────────────


class TestLoadEvaluationResults:
    def _valid_eval_payload(self) -> dict:
        return {
            "dataset_name": "THRD",
            "eval_run_id": "run-1",
            "llm_model": "gpt-4o",
            "agent_type": "baseline",
            "created_at": "2024-01-15T10:00:00",
        }

    def test_returns_eval_output_instances(self, ds, mock_bucket):
        eval_blob = _blob("datasets/THRD/05_evals/llm-as-judge_gpt-4o_baseline_run-1.json")
        eval_blob.download_as_string.return_value = json.dumps(self._valid_eval_payload()).encode()

        # load_evaluation_results also calls load_results → list_blobs is called twice
        mock_bucket.list_blobs.side_effect = [
            [],  # first call: load_results (04_results)
            [eval_blob],  # second call: 05_evals
        ]
        results = ds.load_evaluation_results()

        assert len(results) == 1
        key = list(results.keys())[0]
        assert isinstance(results[key], EvalOutput)

    def test_empty_evals_dir_returns_empty_dict(self, ds, mock_bucket):
        mock_bucket.list_blobs.side_effect = [[], []]
        assert ds.load_evaluation_results() == {}

    def test_invalid_json_in_evals_is_skipped(self, ds, mock_bucket):
        good = _blob("datasets/THRD/05_evals/good.json")
        good.download_as_string.return_value = json.dumps(self._valid_eval_payload()).encode()
        bad = _blob("datasets/THRD/05_evals/bad.json")
        bad.download_as_string.return_value = b"{"

        mock_bucket.list_blobs.side_effect = [[], [bad, good]]
        results = ds.load_evaluation_results()
        assert len(results) == 1

    def test_non_json_files_are_skipped(self, ds, mock_bucket):
        mock_bucket.list_blobs.side_effect = [
            [],
            [_blob("datasets/THRD/05_evals/notes.txt")],
        ]
        assert ds.load_evaluation_results() == {}


# ── Dataset.assign_session_attachments_baseline ───────────────────────────────


class TestAssignSessionAttachmentsBaseline:
    def test_raises_when_data_not_loaded(self, ds):
        ds.data = None
        with pytest.raises(ValueError, match="load_dataset"):
            ds.assign_session_attachments_baseline()

    def test_assigns_all_files_up_to_session_date(self, ds, mock_bucket):
        from evals.models import DatasetPayload

        ds.data = DatasetPayload(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[
                _session("S1", turns=[]),
                _session("S2", turns=[]),
            ],
        )
        ds.data.sessions[0].date = "2024-01-20"
        ds.data.sessions[1].date = "2024-02-20"

        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
            _blob("datasets/THRD/01_data/2024-01-18_b.pdf"),
            _blob("datasets/THRD/01_data/2024-02-05_c.pdf"),
        ]
        ds.assign_session_attachments_baseline()

        s1, s2 = ds.data.sessions
        # S1 sees only files up to 2024-01-20
        assert len(s1.attachments) == 2
        assert all("2024-01" in f for f in s1.attachments)
        # S2 sees all files up to 2024-02-20 (cumulative, not sliding window)
        assert len(s2.attachments) == 3

    def test_does_not_deduplicate_across_sessions(self, ds, mock_bucket):
        """Unlike sliding-window, baseline gives each session its own cumulative set."""
        from evals.models import DatasetPayload

        ds.data = DatasetPayload(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[_session("S1", turns=[]), _session("S2", turns=[])],
        )
        ds.data.sessions[0].date = "2024-01-20"
        ds.data.sessions[1].date = "2024-02-20"

        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
        ]
        ds.assign_session_attachments_baseline()

        s1, s2 = ds.data.sessions
        # Both sessions get the file — it is NOT consumed by S1
        assert len(s1.attachments) == 1
        assert len(s2.attachments) == 1

    def test_session_without_date_gets_empty_list(self, ds, mock_bucket):
        from evals.models import DatasetPayload

        ds.data = DatasetPayload(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[_session("S1", turns=[])],
        )
        ds.data.sessions[0].date = None  # type: ignore[assignment]

        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
        ]
        ds.assign_session_attachments_baseline()
        assert ds.data.sessions[0].attachments == []

    def test_no_files_yields_empty_attachments(self, ds, mock_bucket):
        from evals.models import DatasetPayload

        ds.data = DatasetPayload(
            dataset_name="THRD",
            project_id="p",
            user_id="u",
            sessions=[_session("S1", turns=[])],
        )
        ds.data.sessions[0].date = "2024-01-20"
        mock_bucket.list_blobs.return_value = []
        ds.assign_session_attachments_baseline()
        assert ds.data.sessions[0].attachments == []
