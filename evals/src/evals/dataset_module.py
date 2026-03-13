import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from google.cloud import storage
from .models import DatasetPayload, GatheredResultPayload, EvalOutput, TokenCount
from deepeval.evaluate.types import EvaluationResult


logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {"pdf", "docx", "xlsx", "csv", "txt", "md", "eml"}
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


class Dataset:
    def __init__(self, name: str = None, client: storage.Client = None, bucket_name: str = "master-thesis-prod"):
        self.name = name
        self.data: DatasetPayload | None = None
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

    def load_dataset(self) -> DatasetPayload | None:
        path = f"datasets/{self.name}/dataset_{self.name}.json"
        try:
            raw = self.bucket.blob(path).download_as_string()
            self.data = DatasetPayload.model_validate_json(raw.decode("utf-8"))
            return self.data
        except Exception:
            logger.warning(f"Dataset file {path} not found or is invalid JSON.")
            return None

    def load_results(self) -> dict[str, GatheredResultPayload] | None:
        data = {}
        path = f"datasets/{self.name}/04_results"
        for file in self.bucket.list_blobs(prefix=path):
            if file.name.endswith(".json"):
                try:
                    content = json.loads(file.download_as_string().decode("utf-8"))
                    data[file.name] = GatheredResultPayload.model_validate(content)
                except Exception as e:
                    logger.warning(f"Failed to load {file.name}: {e}")

        return data

    def load_evaluation_results(self) -> dict[str, EvalOutput] | None:
        collected = self.load_results()
        collected_by_run_id = {v.eval_run_id: v for v in collected.values()} if collected else {}

        data = {}
        path = f"datasets/{self.name}/05_evals"
        for file in self.bucket.list_blobs(prefix=path):
            if file.name.endswith(".json"):
                try:
                    content = json.loads(file.download_as_string().decode("utf-8"))
                    output = EvalOutput.model_validate(content)
                    data[file.name] = output
                except Exception as e:
                    logger.warning(f"Failed to load {file.name}: {e}")

        return data

    def save_results(self, data: GatheredResultPayload) -> None:
        path = (f"datasets/{data.dataset_name}/04_results/"
        f"{data.llm_model.replace("/","-")}_{data.agent_type.replace("/","-")}_{data.eval_run_id.replace("/","-")}.json")
        try:
            self.bucket.blob(path).upload_from_string(
                json.dumps(data.model_dump(mode="json"), indent=4, ensure_ascii = False), content_type="application/json"
            )
            logger.info(f"Results saved to {path}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise

    def update_token_counts(self, result: GatheredResultPayload) -> None:
        """Backfill token counts from LangSmith and re-save the result.

        Safe to call after the fact — avoids race conditions where the last
        LLM run hasn't been ingested into LangSmith yet at collection time.
        """
        from .langsmith_module import get_session_token_counts
        total_input, total_output, total_tokens, total_calls = 0, 0, 0, 0
        for session in result.sessions:
            session_tokens = get_session_token_counts(session.runtime_session_id)
            total_input += session_tokens["input_tokens"]
            total_output += session_tokens["output_tokens"]
            total_tokens += session_tokens["total_tokens"]
            total_calls += session_tokens["llm_calls"]
            session.token_counts = TokenCount(
                input_tokens=session_tokens["input_tokens"],
                output_tokens=session_tokens["output_tokens"],
                total_tokens=session_tokens["total_tokens"],
                llm_calls=session_tokens["llm_calls"],
            )
            if session.init_query_id:
                q_init = session_tokens["per_query"].get(session.init_query_id, {})
                session.init_query_token_count = TokenCount(
                    input_tokens=q_init.get("input_tokens", 0),
                    output_tokens=q_init.get("output_tokens", 0),
                    total_tokens=q_init.get("total_tokens", 0),
                    llm_calls=q_init.get("llm_calls", 0),
                )
            for conv in session.conversation:
                qid = conv.query_id or "unknown"
                q = session_tokens["per_query"].get(qid, {})
                if not q.get("input_tokens") or not q.get("output_tokens") or not q.get("total_tokens"):
                    logger.warning(f"Query ID {qid} in session {session.runtime_session_id} has token counts but query_id is missing in conversation entry. This may indicate a mismatch between LangSmith data and conversation entries.")
                    
                conv.token_counts = TokenCount(
                    input_tokens=q.get("input_tokens", 0),
                    output_tokens=q.get("output_tokens", 0),
                    total_tokens=q.get("total_tokens", 0),
                    llm_calls=q.get("llm_calls", 0),
                )
        result.token_counts = TokenCount(
            input_tokens=total_input,
            output_tokens=total_output,
            total_tokens=total_tokens,
            llm_calls=total_calls,
        )
        logger.info(f"📊 Tokens — in: {total_input}  out: {total_output}  total: {total_tokens}  calls: {total_calls}")
        self.save_results(result)

    def save_evaluation_results(self, results: list[EvaluationResult], data: GatheredResultPayload) -> EvalOutput:
        output = EvalOutput(
            dataset_name=data.dataset_name,
            project_id=data.project_id,
            user_id=data.user_id,
            eval_run_id=data.eval_run_id,
            llm_model=data.llm_model,
            agent_type=data.agent_type,
            created_at=datetime.now().isoformat(),
            results=[r.model_dump() for r in results if isinstance(r, EvaluationResult)] if results else None,
        )
        filepath = (f'datasets/{data.dataset_name.replace("/","-")}/05_evals/'
        f'llm-as-judge_{data.llm_model.replace("/","-")}_{data.agent_type.replace("/","-")}_{data.eval_run_id.replace("/","-")}.json')
        blob = self.bucket.blob(filepath)
        blob.upload_from_string(
            json.dumps(output.model_dump(), indent=4, ensure_ascii=False),
            content_type='application/json'
        )
        return output
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
        if not self.data:
            raise ValueError("No data loaded. Call load_dataset() first.")

        date_to_files, _ = self.get_all_data_files()

        def _parse(s: str | None):
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None

        date_to_files_dt = {_parse(d): files for d, files in date_to_files.items()}
        file_dates_sorted = sorted(date_to_files_dt.keys())

        seen: set[str] = set()
        prev_dt = None

        for session in self.data.sessions:
            current_dt = _parse(session.date)
            if current_dt is None:
                session.attachments = []
                continue

            candidates = [
                f
                for fd in file_dates_sorted
                if (prev_dt is None or fd > prev_dt) and fd <= current_dt
                for f in date_to_files_dt[fd]
            ]
            new_files = [f for f in candidates if f not in seen]
            seen.update(new_files)
            session.attachments = new_files

            logger.info(
                f"Session {session.session_name} | "
                f"{prev_dt or '–'} → {current_dt} | "
                f"{len(candidates)} candidates, {len(new_files)} new"
            )
            prev_dt = current_dt

    def assign_session_attachments_baseline(self) -> None:
        """Assign data files to sessions cumulatively for baseline (non-custom) models.

        Unlike assign_session_attachments(), which uses a sliding window per session,
        this assigns all files up to and including each session's date. This ensures
        baseline models receive the full available context at each session, since they
        have no factsheet or accumulated knowledge from prior sessions.

        Mutates self.data in place. Raises ValueError if data is not loaded.
        """
        if not self.data:
            raise ValueError("No data loaded. Call load_dataset() first.")

        date_to_files, _ = self.get_all_data_files()

        def _parse(s: str | None):
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None

        date_to_files_dt = {_parse(d): files for d, files in date_to_files.items()}
        file_dates_sorted = sorted(date_to_files_dt.keys())

        for session in self.data.sessions:
            current_dt = _parse(session.date)
            if current_dt is None:
                session.attachments = []
                continue

            attachments = [
                f
                for fd in file_dates_sorted
                if fd <= current_dt
                for f in date_to_files_dt[fd]
            ]
            session.attachments = attachments

            logger.info(
                f"Session {session.session_name} | "
                f"– → {current_dt} | "
                f"{len(attachments)} attachments (cumulative)"
            )

