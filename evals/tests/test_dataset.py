"""Tests for evals.dataset.Dataset."""
import json
import pytest
from collections import defaultdict
from datetime import date
from unittest.mock import MagicMock, patch, call

from evals.dataset_module import Dataset
from evals.models import DatasetPayload, GatheredResultPayload, Session


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _blob(name: str, size: int = 100) -> MagicMock:
    b = MagicMock()
    b.name = name
    b.size = size
    return b


@pytest.fixture
def mock_bucket() -> MagicMock:
    return MagicMock()


@pytest.fixture
def ds(mock_bucket) -> Dataset:
    client = MagicMock()
    client.bucket.return_value = mock_bucket
    return Dataset(name="THRD-2021-163881", client=client)


# ── list_datasets ─────────────────────────────────────────────────────────────

class TestListDatasets:
    def test_returns_unique_dataset_names(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/DS-A/dataset_DS-A.json"),
            _blob("datasets/DS-A/01_data/2024-01-01_file.pdf"),
            _blob("datasets/DS-B/dataset_DS-B.json"),
        ]
        result = ds.list_datasets()
        assert result == ["DS-A", "DS-B"]

    def test_empty_bucket(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = []
        assert ds.list_datasets() == []

    def test_ignores_root_level_blobs(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/"),
            _blob("datasets/DS-A/file.json"),
        ]
        result = ds.list_datasets()
        assert result == ["DS-A"]


# ── run_format_check ──────────────────────────────────────────────────────────

class TestRunFormatCheck:
    def test_all_correct(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD-2021-163881/01_data/2024-01-15_doc.pdf"),
            _blob("datasets/THRD-2021-163881/01_data/2024-02-20_email.eml"),
        ]
        result = ds.run_format_check()
        assert result == []

    def test_detects_files_without_date(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD-2021-163881/01_data/nodatehere.pdf"),
            _blob("datasets/THRD-2021-163881/01_data/2024-01-15_ok.pdf"),
        ]
        result = ds.run_format_check()
        assert len(result) == 1
        assert "nodatehere.pdf" in result[0]


# ── load_dataset ──────────────────────────────────────────────────────────────

class TestLoadDataset:
    def test_loads_valid_json(self, ds, mock_bucket):
        payload = {"dataset_name": "THRD-2021-163881", "project_id": "p", "user_id": "u", "sessions": []}
        mock_bucket.blob.return_value.download_as_string.return_value = (
            json.dumps(payload).encode("utf-8")
        )
        result = ds.load_dataset()
        assert result is not None
        assert result.dataset_name == "THRD-2021-163881"
        assert ds.data.dataset_name == "THRD-2021-163881"

    def test_returns_none_on_error(self, ds, mock_bucket):
        mock_bucket.blob.return_value.download_as_string.side_effect = Exception("not found")
        result = ds.load_dataset()
        assert result is None

    def test_uses_correct_blob_path(self, ds, mock_bucket):
        payload = {"dataset_name": "THRD-2021-163881", "project_id": "p", "user_id": "u", "sessions": []}
        mock_bucket.blob.return_value.download_as_string.return_value = json.dumps(payload).encode()
        ds.load_dataset()
        mock_bucket.blob.assert_called_once_with(
            "datasets/THRD-2021-163881/dataset_THRD-2021-163881.json"
        )


# ── save_results ──────────────────────────────────────────────────────────────

class TestSaveResults:
    def _make_data(self) -> GatheredResultPayload:
        return GatheredResultPayload(
            dataset_name="THRD-2021-163881",
            project_id="p",
            user_id="u",
            sessions=[],
            eval_run_id="run-1",
            llm_model="gpt-4o",
            agent_type="baseline",
        )

    def test_uploads_to_correct_prefix(self, ds, mock_bucket):
        ds.save_results(self._make_data())
        path = mock_bucket.blob.call_args[0][0]
        assert path.startswith("datasets/THRD-2021-163881/04_results/gpt-4o_")
        assert path.endswith(".json")

    def test_path_contains_agent_type_and_eval_run_id(self, ds, mock_bucket):
        ds.save_results(self._make_data())
        path = mock_bucket.blob.call_args[0][0]
        assert "baseline" in path
        assert "run-1" in path

    def test_raises_when_upload_fails(self, ds, mock_bucket):
        mock_bucket.blob.return_value.upload_from_string.side_effect = Exception("GCS error")
        with pytest.raises(Exception, match="GCS error"):
            ds.save_results(self._make_data())


# ── get_all_data_files ────────────────────────────────────────────────────────

class TestGetAllDataFiles:
    def test_groups_files_by_date(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
            _blob("datasets/THRD/01_data/2024-01-10_b.pdf"),
            _blob("datasets/THRD/01_data/2024-02-05_c.docx"),
        ]
        date_to_files, sorted_dates = ds.get_all_data_files()
        assert sorted_dates == ["2024-01-10", "2024-02-05"]
        assert len(date_to_files["2024-01-10"]) == 2
        assert len(date_to_files["2024-02-05"]) == 1

    def test_filters_unsupported_extensions(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_doc.pdf"),
            _blob("datasets/THRD/01_data/2024-01-10_image.png"),
            _blob("datasets/THRD/01_data/2024-01-10_video.mp4"),
        ]
        date_to_files, _ = ds.get_all_data_files()
        all_files = [f for files in date_to_files.values() for f in files]
        assert all(f.endswith(".pdf") for f in all_files)

    def test_skips_files_without_date(self, ds, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_ok.pdf"),
            _blob("datasets/THRD/01_data/no-date-here.pdf"),
        ]
        date_to_files, sorted_dates = ds.get_all_data_files()
        assert len(sorted_dates) == 1
        assert sorted_dates == ["2024-01-10"]


# ── get_attachments ───────────────────────────────────────────────────────────

class TestGetAttachments:
    def _setup(self, mock_bucket):
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
            _blob("datasets/THRD/01_data/2024-02-15_b.pdf"),
            _blob("datasets/THRD/01_data/2024-03-20_c.pdf"),
        ]

    def test_no_filter_returns_all(self, ds, mock_bucket):
        self._setup(mock_bucket)
        result = ds.get_attachments()
        assert len(result) == 3

    def test_start_date_filters_older(self, ds, mock_bucket):
        self._setup(mock_bucket)
        result = ds.get_attachments(start_date="2024-02-01")
        assert all("2024-02" in f or "2024-03" in f for f in result)
        assert len(result) == 2

    def test_end_date_filters_newer(self, ds, mock_bucket):
        self._setup(mock_bucket)
        result = ds.get_attachments(end_date="2024-02-28")
        assert len(result) == 2

    def test_range_both_bounds(self, ds, mock_bucket):
        self._setup(mock_bucket)
        result = ds.get_attachments(start_date="2024-02-01", end_date="2024-02-28")
        assert len(result) == 1
        assert "2024-02-15" in result[0]


# ── assign_session_attachments ────────────────────────────────────────────────

class TestAssignSessionAttachments:
    def test_raises_when_data_not_loaded(self, ds):
        ds.data = None
        with pytest.raises(ValueError, match="load_dataset"):
            ds.assign_session_attachments()

    def _make_ds_data(self, *session_specs) -> DatasetPayload:
        sessions = [
            Session(
                session_name=s.get("session_name", "S"),
                date=s.get("date", "2024-01-01"),
                init_query="Init",
                conversation=[],
            )
            for s in session_specs
        ]
        return DatasetPayload(dataset_name="THRD", project_id="p", user_id="u", sessions=sessions)

    def test_assigns_files_in_date_window(self, ds, mock_bucket):
        ds.data = self._make_ds_data(
            {"date": "2024-01-15", "session_name": "S1"},
            {"date": "2024-02-20", "session_name": "S2"},
        )
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
            _blob("datasets/THRD/01_data/2024-01-14_b.pdf"),
            _blob("datasets/THRD/01_data/2024-02-01_c.pdf"),
        ]
        ds.assign_session_attachments()

        s1, s2 = ds.data.sessions
        assert len(s1.attachments) == 2   # a + b fall in (−∞, 2024-01-15]
        assert len(s2.attachments) == 1   # c falls in (2024-01-15, 2024-02-20]

    def test_file_not_assigned_twice(self, ds, mock_bucket):
        """A file on session 1's exact date must NOT also appear in session 2."""
        ds.data = self._make_ds_data(
            {"date": "2024-01-15", "session_name": "S1"},
            {"date": "2024-02-20", "session_name": "S2"},
        )
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-15_boundary.pdf"),
        ]
        ds.assign_session_attachments()
        assert len(ds.data.sessions[0].attachments) == 1
        assert len(ds.data.sessions[1].attachments) == 0

    def test_session_without_date_gets_empty_list(self, ds, mock_bucket):
        ds.data = self._make_ds_data({"session_name": "No date", "date": "2000-01-01"})
        ds.data.sessions[0].date = None  # type: ignore[assignment]
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-01-10_a.pdf"),
        ]
        ds.assign_session_attachments()
        assert ds.data.sessions[0].attachments == []

    def test_no_files_yields_empty_attachments(self, ds, mock_bucket):
        ds.data = self._make_ds_data({"date": "2024-01-15", "session_name": "S1"})
        mock_bucket.list_blobs.return_value = []
        ds.assign_session_attachments()
        assert ds.data.sessions[0].attachments == []

    def test_file_after_last_session_not_assigned(self, ds, mock_bucket):
        ds.data = self._make_ds_data({"date": "2024-01-15", "session_name": "S1"})
        mock_bucket.list_blobs.return_value = [
            _blob("datasets/THRD/01_data/2024-06-01_future.pdf"),
        ]
        ds.assign_session_attachments()
        assert ds.data.sessions[0].attachments == []


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestDatasetIntegration:
    """Requires real GCS credentials and a live 'master-thesis-prod' bucket."""

    DATASET = "THRD-2021-163881"

    @pytest.fixture
    def live_ds(self):
        return Dataset(name=self.DATASET)

    def test_list_datasets_returns_nonempty(self, live_ds):
        result = live_ds.list_datasets()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_load_dataset_returns_sessions(self, live_ds):
        data = live_ds.load_dataset()
        assert data is not None
        assert len(data.sessions) > 0

    def test_get_all_data_files_returns_files(self, live_ds):
        date_to_files, sorted_dates = live_ds.get_all_data_files()
        assert len(sorted_dates) > 0
        assert all(isinstance(d, str) and len(d) == 10 for d in sorted_dates)

    def test_assign_session_attachments_no_duplicates(self, live_ds):
        live_ds.load_dataset()
        live_ds.assign_session_attachments()
        all_assigned = [
            f
            for s in live_ds.data.sessions
            for f in s.attachments
        ]
        assert len(all_assigned) == len(set(all_assigned)), "Duplicate files assigned"

    def test_run_format_check_clean(self, live_ds):
        wrong = live_ds.run_format_check()
        assert isinstance(wrong, list)
