import json
import logging
import re
from collections import defaultdict
from datetime import datetime

from google.cloud import storage

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx", "xlsx", "csv", "txt", "md", "eml"}
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


class Dataset:
    def __init__(self, name: str = None, client: storage.Client = None, bucket_name: str = "master-thesis-prod"):
        self.name = name
        self.data: dict | None = None
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_datasets(self) -> list[str]:
        seen = set()
        for blob in self.bucket.list_blobs(prefix="datasets/"):
            parts = blob.name.split("/")
            if len(parts) > 1 and parts[1]:
                seen.add(parts[1])
        return sorted(seen)

    # ── Format check ──────────────────────────────────────────────────────────

    def run_format_check(self) -> list[str]:
        wrong = []
        for blob in self.bucket.list_blobs(prefix=f"datasets/{self.name}/01_data/"):
            if not DATE_PATTERN.search(blob.name):
                logger.warning(f"Filename {blob.name} does not match expected date pattern.")
                wrong.append(blob.name)
        if not wrong:
            logger.info("All files have the correct date format.")
        return wrong

    # ── Load / save ───────────────────────────────────────────────────────────

    def load_dataset(self) -> dict | None:
        path = f"datasets/{self.name}/dataset_{self.name}.json"
        try:
            raw = self.bucket.blob(path).download_as_string()
            self.data = json.loads(raw.decode("utf-8"))
            return self.data
        except Exception:
            logger.warning(f"Dataset file {path} not found or is invalid JSON.")
            return None

    def save_results(self, data: dict) -> None:
        dataset_name = data.get("dataset_name")
        llm_model = data.get("llm_model")
        if not dataset_name or not llm_model:
            raise ValueError("data must contain 'dataset_name' and 'llm_model' keys.")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = f"datasets/{dataset_name}/04_results/{llm_model}_{timestamp}.json"
        try:
            self.bucket.blob(path).upload_from_string(
                json.dumps(data, indent=4), content_type="application/json"
            )
            logger.info(f"Results saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise

    # ── File helpers ──────────────────────────────────────────────────────────

    def get_all_data_files(self) -> tuple[dict[str, list[str]], list[str]]:
        """Return (date → [blob_paths], sorted_dates) for all supported files."""
        prefix = f"datasets/{self.name}/01_data/"
        date_to_files: dict[str, list[str]] = defaultdict(list)

        for blob in self.bucket.list_blobs(prefix=prefix):
            ext = blob.name.rsplit(".", 1)[-1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            match = DATE_PATTERN.search(blob.name)
            if not match:
                logger.debug(f"File without date: {blob.name}")
                continue
            date_to_files[match.group(1)].append(blob.name)

        sorted_dates = sorted(date_to_files.keys())
        logger.info(f"Found {sum(len(v) for v in date_to_files.values())} files under {prefix}")
        return dict(date_to_files), sorted_dates

    def get_attachments(self, start_date: str = None, end_date: str = None) -> list[str]:
        """Return blob paths filtered by optional date range (inclusive, YYYY-MM-DD strings)."""
        date_to_files, _ = self.get_all_data_files()
        result = []
        for date_str, paths in date_to_files.items():
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            result.extend(paths)
        if not result:
            logger.warning("No attachments found within the specified date range.")
        return result

    # ── Attachment assignment ─────────────────────────────────────────────────

    def assign_session_attachments(self) -> None:
        """Assign data files to sessions based on chronological date windows.

        For each session, files whose extracted date falls in the half-open
        interval (previous_session_date, session_date] are assigned as
        attachments. Files already assigned to an earlier session are excluded.

        Mutates self.data in place. Raises ValueError if data is not loaded.
        """
        if not self.data or "sessions" not in self.data:
            raise ValueError("No data loaded. Call load_dataset() first.")

        date_to_files, _ = self.get_all_data_files()

        def _parse(s: str | None):
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None

        date_to_files_dt = {_parse(d): files for d, files in date_to_files.items()}
        file_dates_sorted = sorted(date_to_files_dt.keys())

        seen: set[str] = set()
        prev_dt = None

        for session in self.data["sessions"]:
            current_dt = _parse(session.get("date"))
            if current_dt is None:
                session["attachments"] = []
                continue

            candidates = [
                f
                for fd in file_dates_sorted
                if (prev_dt is None or fd > prev_dt) and fd <= current_dt
                for f in date_to_files_dt[fd]
            ]
            new_files = [f for f in candidates if f not in seen]
            seen.update(new_files)
            session["attachments"] = new_files

            logger.info(
                f"Session {session.get('session_name', '?')} | "
                f"{prev_dt or '–'} → {current_dt} | "
                f"{len(candidates)} candidates, {len(new_files)} new"
            )
            prev_dt = current_dt
