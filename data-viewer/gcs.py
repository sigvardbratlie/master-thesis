import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from google.cloud import storage
from google.oauth2 import service_account

_OSLO = ZoneInfo("Europe/Oslo")

BUCKET_NAME = "master-thesis-prod"

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".eml", ".docx", ".xlsx"}

FILE_ICONS = {
    ".pdf": "📄",
    ".txt": "📝",
    ".eml": "📧",
    ".docx": "📝",
    ".xlsx": "📊",
}

_RESULT_RE = re.compile(r"^(.+)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$")
_EVAL_RE = re.compile(r"^llm-as-judge_(.+)_(custom|baseline)_(.+)\.json$")
_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass
class BlobInfo:
    name: str
    size: int | None
    time_created: datetime | None


@st.cache_resource
def get_gcs_client() -> storage.Client:
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"])
    )
    return storage.Client(credentials=creds)


def _bucket() -> storage.Bucket:
    return get_gcs_client().bucket(BUCKET_NAME)


def blob_exists(blob_path: str) -> bool:
    return _bucket().blob(blob_path).exists()


def read_blob_bytes(blob_path: str) -> bytes:
    return _bucket().blob(blob_path).download_as_bytes()


@st.cache_data(ttl=300)
def cached_read_blob_bytes(blob_path: str) -> bytes:
    return read_blob_bytes(blob_path)


def write_blob(blob_path: str, data: bytes) -> None:
    _bucket().blob(blob_path).upload_from_string(
        data, content_type="application/json; charset=utf-8"
    )


def delete_blob(blob_path: str) -> None:
    blob = _bucket().blob(blob_path)
    if blob.exists():
        blob.delete()


def copy_blob(src: str, dst: str) -> None:
    bucket = _bucket()
    bucket.copy_blob(bucket.blob(src), bucket, dst)


def move_blob(src: str, dst: str) -> None:
    copy_blob(src, dst)
    delete_blob(src)


def upload_raw_blob(blob_path: str, data: bytes, content_type: str) -> None:
    _bucket().blob(blob_path).upload_from_string(data, content_type=content_type)


@st.cache_data(ttl=300)
def list_dataset_names() -> list[str]:
    client = get_gcs_client()
    blobs = client.list_blobs(BUCKET_NAME, prefix="datasets/", delimiter="/")
    _ = list(blobs)  # consume iterator to populate prefixes
    dataset = sorted(
        p.replace("datasets/", "").rstrip("/")
        for p in blobs.prefixes
        if p != "datasets/"
    )

    return [d for d in dataset if d and d != "None"]


def dataset_blob_path(ds: str) -> str:
    return f"datasets/{ds}/dataset_{ds}.json"


def draft_blob_path(ds: str) -> str:
    return f"datasets/{ds}/dataset_{ds}_draft.json"


def version_blob_path(ds: str, ts: str) -> str:
    return f"datasets/{ds}/versions/dataset_{ds}_{ts}.json"


@st.cache_data(ttl=300)
def list_versions(ds: str) -> list[BlobInfo]:
    """Return published version blobs, newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{ds}/versions/"
    blobs = [
        BlobInfo(name=b.name, size=b.size, time_created=b.time_created)
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


@st.cache_data(ttl=300)
def list_data_blobs(dataset: str) -> list[BlobInfo]:
    """Return blobs under datasets/<dataset>/01_data/ with supported extensions."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/01_data/"
    return [
        BlobInfo(name=b.name, size=b.size, time_created=b.time_created)
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/")
        and Path(b.name).suffix.lower() in SUPPORTED_EXTENSIONS
    ]


@st.cache_data(ttl=300)
def list_result_blobs(dataset: str) -> list[BlobInfo]:
    """Return blobs under datasets/<dataset>/04_results/ (JSON files), newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/04_results/"
    blobs = [
        BlobInfo(name=b.name, size=b.size, time_created=b.time_created)
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/") and b.name.endswith(".json")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


@st.cache_data(ttl=300)
def list_eval_blobs(dataset: str) -> list[BlobInfo]:
    """Return blobs under datasets/<dataset>/05_evals/ (JSON files), newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/05_evals/"
    blobs = [
        BlobInfo(name=b.name, size=b.size, time_created=b.time_created)
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/") and b.name.endswith(".json")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


def create_dataset(ds_name: str) -> None:
    """Create a new empty dataset JSON in GCS."""
    payload = json.dumps(
        {
            "dataset_name": ds_name,
            "project_id": "",
            "last_updated": datetime.now(_OSLO).isoformat(),
            "sessions": [],
        },
        ensure_ascii=False,
        indent=4,
    ).encode("utf-8")
    write_blob(dataset_blob_path(ds_name), payload)


def trash_dataset(ds_name: str) -> None:
    """Move all blobs for a dataset to _trash/datasets/{ds_name}_{ts}/."""
    client = get_gcs_client()
    prefix = f"datasets/{ds_name}/"
    blobs = list(client.list_blobs(BUCKET_NAME, prefix=prefix))
    ts = datetime.now(_OSLO).strftime("%Y-%m-%dT%H-%M-%S")
    for blob in blobs:
        rel = blob.name[len(prefix):]
        move_blob(blob.name, f"_trash/datasets/{ds_name}_{ts}/{rel}")


def trash_file(dataset: str, blob_name: str) -> None:
    """Move a data file to the dataset's _trash/ folder."""
    filename = blob_name.split("/")[-1]
    ts = datetime.now(_OSLO).strftime("%Y-%m-%dT%H-%M-%S")
    move_blob(blob_name, f"datasets/{dataset}/_trash/{ts}_{filename}")


def trash_result_blob(dataset: str, blob_name: str) -> None:
    """Move a result file to the dataset's _trash/ folder."""
    filename = blob_name.split("/")[-1]
    ts = datetime.now(_OSLO).strftime("%Y-%m-%dT%H-%M-%S")
    move_blob(blob_name, f"datasets/{dataset}/_trash/results_{ts}_{filename}")


def trash_eval_blob(dataset: str, blob_name: str) -> None:
    """Move an eval file to the dataset's _trash/ folder."""
    filename = blob_name.split("/")[-1]
    ts = datetime.now(_OSLO).strftime("%Y-%m-%dT%H-%M-%S")
    move_blob(blob_name, f"datasets/{dataset}/_trash/evals_{ts}_{filename}")


@st.cache_data(ttl=300)
def _build_result_index(dataset: str) -> dict[str, str]:
    """Build a mapping of {eval_run_id: blob_name} by reading all result files once."""
    index: dict[str, str] = {}
    for blob in list_result_blobs(dataset):
        try:
            data = json.loads(read_blob_bytes(blob.name).decode("utf-8"))
            run_id = data.get("eval_run_id")
            if run_id:
                index[run_id] = blob.name
        except Exception:
            continue
    return index


@st.cache_data(ttl=300)
def _load_matched_result(dataset: str, eval_run_id: str) -> dict:
    """Find the result file matching eval_run_id and return its full data dict."""
    index = _build_result_index(dataset)
    blob_name = index.get(eval_run_id)
    if not blob_name:
        return {}
    try:
        return json.loads(read_blob_bytes(blob_name).decode("utf-8"))
    except Exception:
        return {}


def parse_result_filename(name: str) -> tuple[str, str]:
    """Return (model, display_timestamp) from a result filename, or (name, '') on failure."""
    m = _RESULT_RE.match(name)
    if not m:
        return name, ""
    model = m.group(1)
    ts = m.group(2)  # YYYY-MM-DD_HH-MM-SS
    display = ts.replace("_", " ").replace("-", ":", 2)  # YYYY-MM-DD HH:MM:SS
    # Fix: only replace hyphens in the time part
    date_part, time_part = ts.split("_")
    display = f"{date_part} {time_part.replace('-', ':')}"
    return model, display


def parse_eval_filename(name: str) -> tuple[str, str, str]:
    """Return (model, agent_type, eval_run_id) from eval filename, or (name, '', '') on failure."""
    m = _EVAL_RE.match(name)
    if not m:
        return name, "", ""
    return m.group(1), m.group(2), m.group(3)
