import copy
import email
import json
import logging
import math
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_OSLO = ZoneInfo("Europe/Oslo")
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import streamlit as st
from docx import Document
from google.api_core.exceptions import NotFound
from google.cloud import storage
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not Path(".").resolve().name == "data-viewer":
    os.chdir("./data-viewer")

st.set_page_config(page_title="📂 Dataset Viewer", layout="wide")

# ── GCS Setup ─────────────────────────────────────────────────────────────────

BUCKET_NAME = "master-thesis-prod"


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


def list_versions(ds: str) -> list[storage.Blob]:
    """Return published version blobs, newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{ds}/versions/"
    blobs = [
        b
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


def list_data_blobs(dataset: str) -> list[storage.Blob]:
    """Return blobs under datasets/<dataset>/01_data/ with supported extensions."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/01_data/"
    return [
        b
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/")
        and Path(b.name).suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def list_result_blobs(dataset: str) -> list[storage.Blob]:
    """Return blobs under datasets/<dataset>/04_results/ (JSON files), newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/04_results/"
    blobs = [
        b
        for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/") and b.name.endswith(".json")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


def list_eval_blobs(dataset: str) -> list[storage.Blob]:
    """Return blobs under datasets/<dataset>/05_evals/ (JSON files), newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/05_evals/"
    blobs = [
        b
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
        rel = blob.name[len(prefix) :]
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


_RESULT_RE = re.compile(r"^(.+)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$")
_EVAL_RE = re.compile(r"^llm-as-judge_(.+)_(custom|baseline)_(.+)\.json$")
_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


@st.cache_data(ttl=120)
def _load_matched_result(dataset: str, eval_run_id: str) -> dict:
    """Find the result file matching eval_run_id and return its full data dict."""
    for blob in list_result_blobs(dataset):
        try:
            data = json.loads(read_blob_bytes(blob.name).decode("utf-8"))
            if data.get("eval_run_id") == eval_run_id:
                return data
        except Exception:
            continue
    return {}


# ── LangSmith token counts ─────────────────────────────────────────────────────

def _get_langsmith_client():
    import os
    from langsmith import Client
    api_key = st.secrets["langsmith"].get("LANGSMITH_API_KEY")
    if api_key:
        os.environ["LANGSMITH_API_KEY"] = api_key
    return Client()


def _get_session_token_counts(client, runtime_session_id: str, project_name: str) -> dict:
    runs = list(client.list_runs(
        project_name=project_name,
        filter=f'has(metadata, \'{{"thread_id": "{runtime_session_id}"}}\')',
        run_type="llm",
    ))
    per_query: dict[str, dict] = {}
    for r in runs:
        qid = (r.extra or {}).get("metadata", {}).get("query_id", "unknown")
        entry = per_query.setdefault(qid, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0})
        entry["input_tokens"] += r.prompt_tokens or 0
        entry["output_tokens"] += r.completion_tokens or 0
        entry["total_tokens"] += r.total_tokens or 0
        entry["llm_calls"] += 1
    return {
        "input_tokens": sum(r.prompt_tokens or 0 for r in runs),
        "output_tokens": sum(r.completion_tokens or 0 for r in runs),
        "total_tokens": sum(r.total_tokens or 0 for r in runs),
        "llm_calls": len(runs),
        "per_query": per_query,
    }


def update_token_counts(blob_name: str, result_data: dict) -> None:
    """Fetch token counts from LangSmith for each session and re-save the result blob."""
    import os
    client = _get_langsmith_client()
    project_name = st.secrets.get("LANGCHAIN_PROJECT") or os.environ.get("LANGCHAIN_PROJECT", "default")

    total_input, total_output, total_tokens, total_calls = 0, 0, 0, 0
    for session in result_data.get("sessions", []):
        rid = session.get("runtime_session_id")
        if not rid:
            continue
        s_tok = _get_session_token_counts(client, rid, project_name)
        total_input += s_tok["input_tokens"]
        total_output += s_tok["output_tokens"]
        total_tokens += s_tok["total_tokens"]
        total_calls += s_tok["llm_calls"]

        session["token_counts"] = {
            "input_tokens": s_tok["input_tokens"],
            "output_tokens": s_tok["output_tokens"],
            "total_tokens": s_tok["total_tokens"],
            "llm_calls": s_tok["llm_calls"],
        }

        init_qid = session.get("init_query_id")
        if init_qid:
            q_init = s_tok["per_query"].get(init_qid, {})
            session["init_query_token_count"] = {
                "input_tokens": q_init.get("input_tokens", 0),
                "output_tokens": q_init.get("output_tokens", 0),
                "total_tokens": q_init.get("total_tokens", 0),
                "llm_calls": q_init.get("llm_calls", 0),
            }

        for conv in session.get("conversation", []):
            qid = conv.get("query_id", "unknown")
            q = s_tok["per_query"].get(qid, {})
            conv["token_counts"] = {
                "input_tokens": q.get("input_tokens", 0),
                "output_tokens": q.get("output_tokens", 0),
                "total_tokens": q.get("total_tokens", 0),
                "llm_calls": q.get("llm_calls", 0),
            }

    result_data["token_counts"] = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "total_tokens": total_tokens,
        "llm_calls": total_calls,
    }

    write_blob(blob_name, json.dumps(result_data, ensure_ascii=False, indent=4).encode("utf-8"))
    logger.info(f"Token counts updated and saved to {blob_name}")


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


# ── Header ────────────────────────────────────────────────────────────────────

st.title("📂 Dataset Viewer")
st.caption("Select a dataset, edit the content, and publish the revised version.")

st.divider()

# ── Dataset selection ─────────────────────────────────────────────────────────

dataset_names = list_dataset_names()

st.markdown("#### 🗂️ Select dataset")
_ds_col, _btn_new, _btn_del = st.columns([0.6, 0.2, 0.2])
with _ds_col:
    dataset = st.selectbox(
        "Dataset",
        dataset_names,
        index=0,
        label_visibility="collapsed",
    )
with _btn_new:
    if st.button("➕ New dataset", use_container_width=True):
        st.session_state["_show_new_dataset"] = not st.session_state.get(
            "_show_new_dataset", False
        )
with _btn_del:
    if dataset and st.button("🗑️ Delete dataset", use_container_width=True):
        st.session_state["_confirm_delete_dataset"] = dataset

if st.session_state.get("_show_new_dataset"):
    with st.form("form_new_dataset", clear_on_submit=True):
        _new_name = st.text_input("Dataset name", placeholder="e.g. my-dataset-01")
        if st.form_submit_button("Create") and _new_name:
            if _new_name in dataset_names:
                st.error(f"Dataset **{_new_name}** already exists.")
            else:
                create_dataset(_new_name)
                st.session_state["_show_new_dataset"] = False
                st.rerun()

if _ds_to_del := st.session_state.get("_confirm_delete_dataset"):
    st.warning(f"⚠️ Move dataset **{_ds_to_del}** and all its files to trash?")
    _col_yes, _col_no, _ = st.columns([0.1, 0.1, 0.8])
    if _col_yes.button("Yes", key="del_ds_yes"):
        trash_dataset(_ds_to_del)
        st.session_state.pop("_confirm_delete_dataset", None)
        if st.session_state.get("_loaded_dataset") == _ds_to_del:
            st.session_state.pop("_loaded_dataset", None)
        st.rerun()
    if _col_no.button("Cancel", key="del_ds_no"):
        st.session_state.pop("_confirm_delete_dataset", None)
        st.rerun()

if not dataset:
    st.stop()

# ── Load into session_state (reset on dataset change) ────────────────────────

if st.session_state.get("_loaded_dataset") != dataset:
    _draft = draft_blob_path(dataset)
    _force_original = st.session_state.pop("_reset_to_original", False)

    try:
        if not _force_original and blob_exists(_draft):
            raw: dict = json.loads(read_blob_bytes(_draft).decode("utf-8"))
            st.session_state["_from_draft"] = True
        else:
            raw: dict = json.loads(
                read_blob_bytes(dataset_blob_path(dataset)).decode("utf-8")
            )
            st.session_state["_from_draft"] = False
    except NotFound:
        st.error(
            f"⚠️ No dataset file found for **{dataset}**.\n\n"
            f"`datasets/{dataset}/dataset_{dataset}.json` does not exist in the bucket.",
            icon=None,
        )
        st.stop()

    # Backfill missing query_id / init_query_id and fix session/order numbering on load
    for s_idx, session in enumerate(raw.get("sessions", [])):
        session["session"] = s_idx
        if not session.get("init_query_id"):
            session["init_query_id"] = str(uuid.uuid4())
        for q_idx, query in enumerate(session.get("conversation", [])):
            if not query.get("query_id"):
                query["query_id"] = str(uuid.uuid4())
            query["order"] = q_idx

    st.session_state["_raw"] = raw
    st.session_state["_loaded_dataset"] = dataset
    st.session_state["_last_saved"] = None
    st.session_state["_last_published"] = None

    for s_idx, session in enumerate(raw["sessions"]):
        st.session_state[f"sname_{s_idx}"] = session.get("session_name", "")
        st.session_state[f"sdate_{s_idx}"] = session.get("date", "")
        st.session_state[f"sinit_{s_idx}"] = session.get("init_query", "")
        for q_idx, query in enumerate(session["conversation"]):
            st.session_state[f"inp_{s_idx}_{q_idx}"] = query.get("input", "").strip()
            st.session_state[f"ans_{s_idx}_{q_idx}"] = query.get("answer", "").strip()

raw = st.session_state["_raw"]


# ── Helpers ───────────────────────────────────────────────────────────────────


def text_height(
    text: str, min_height: int = 100, max_height: int = 800, chars_per_line: int = 90
) -> int:
    lines = text.split("\n")
    total_lines = sum(max(1, math.ceil(len(line) / chars_per_line)) for line in lines)
    return max(min_height, min(max_height, total_lines * 22 + 50))


def _render_token_metrics(token_counts: dict) -> None:
    """Render token counts dict as Streamlit metric widgets."""
    st.write("")
    tc_cols = st.columns(len(token_counts))
    for col, (k, v) in zip(tc_cols, token_counts.items()):
        col.metric(k.replace("_", " ").title(), f"{v:,}" if isinstance(v, int) else v)


def _render_time_inputs(time_usage: dict, key_prefix: str = "") -> None:
    """Render time usage (starttime/endtime/duration_seconds) as disabled text inputs."""
    duration = time_usage.get("duration_seconds")
    start_time = time_usage.get("starttime")
    end_time = time_usage.get("endtime")
    t1, t2, t3, _ = st.columns(4)
    t1.text_input("Duration", value=f"{duration:.1f}s" if duration else "—", disabled=True, key=f"{key_prefix}_dur" if key_prefix else None)
    t2.text_input("Start Time", value=start_time or "—", disabled=True, key=f"{key_prefix}_start" if key_prefix else None)
    t3.text_input("End Time", value=end_time or "—", disabled=True, key=f"{key_prefix}_end" if key_prefix else None)


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".eml", ".docx", ".xlsx"}

FILE_ICONS = {
    ".pdf": "📄",
    ".txt": "📝",
    ".eml": "📧",
    ".docx": "📝",
    ".xlsx": "📊",
}


def render_file(filename: str, content: bytes) -> None:
    """Render a supported file inline."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        st.pdf(BytesIO(content))

    elif ext == ".txt":
        with st.container(height=600, border=True):
            st.text(content.decode("utf-8", errors="ignore"))

    elif ext == ".eml":
        msg = email.message_from_bytes(content)
        with st.container(height=600, border=True):
            st.markdown(f"**From:** {msg.get('From', '')}")
            st.markdown(f"**To:** {msg.get('To', '')}")
            st.markdown(f"**Subject:** {msg.get('Subject', '')}")
            st.markdown(f"**Date:** {msg.get('Date', '')}")
            st.divider()
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        st.text(
                            part.get_payload(decode=True).decode(
                                "utf-8", errors="ignore"
                            )
                        )
            else:
                st.text(msg.get_payload(decode=True).decode("utf-8", errors="ignore"))

    elif ext == ".docx":
        document = Document(BytesIO(content))
        st.text("\n".join(p.text for p in document.paragraphs))

    elif ext == ".xlsx":
        df = pd.read_excel(BytesIO(content))
        st.dataframe(df, use_container_width=True)

    else:
        st.warning(f"Unsupported file type: `{ext}`")


def _sync_widgets_to_raw() -> None:
    """Write current widget values back into _raw before structural changes."""
    for s_idx, session in enumerate(st.session_state["_raw"]["sessions"]):
        session["session_name"] = st.session_state.get(
            f"sname_{s_idx}", session.get("session_name", "")
        )
        session["date"] = st.session_state.get(
            f"sdate_{s_idx}", session.get("date", "")
        )
        session["init_query"] = st.session_state.get(
            f"sinit_{s_idx}", session.get("init_query", "")
        )
        for q_idx, query in enumerate(session["conversation"]):
            query["input"] = st.session_state.get(
                f"inp_{s_idx}_{q_idx}", query.get("input", "")
            )
            query["answer"] = st.session_state.get(
                f"ans_{s_idx}_{q_idx}", query.get("answer", "")
            )


def _rebuild_session_keys() -> None:
    """Clear and re-initialise all index-based widget keys from _raw."""
    for key in [
        k
        for k in st.session_state
        if k.startswith(("sname_", "sdate_", "sinit_", "inp_", "ans_"))
    ]:
        del st.session_state[key]
    for s_idx, session in enumerate(st.session_state["_raw"]["sessions"]):
        st.session_state[f"sname_{s_idx}"] = session.get("session_name", "")
        st.session_state[f"sdate_{s_idx}"] = session.get("date", "")
        st.session_state[f"sinit_{s_idx}"] = session.get("init_query", "")
        for q_idx, query in enumerate(session["conversation"]):
            st.session_state[f"inp_{s_idx}_{q_idx}"] = query.get("input", "").strip()
            st.session_state[f"ans_{s_idx}_{q_idx}"] = query.get("answer", "").strip()


def _fix_mojibake(obj):
    """Recursively fix UTF-8 text that was incorrectly decoded as latin-1."""
    if isinstance(obj, str):
        try:
            return obj.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return obj
    elif isinstance(obj, dict):
        return {k: _fix_mojibake(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_fix_mojibake(item) for item in obj]
    return obj


def fix_encoding() -> None:
    """Fix mojibake encoding in _raw, rebuild widgets, and save draft."""
    _sync_widgets_to_raw()
    st.session_state["_raw"] = _fix_mojibake(st.session_state["_raw"])
    _rebuild_session_keys()


def _renumber() -> None:
    """Reassign sequential 'session' and per-session 'order' fields after structural changes."""
    for s_idx, session in enumerate(st.session_state["_raw"]["sessions"]):
        session["session"] = s_idx
        for q_idx, query in enumerate(session["conversation"]):
            query["order"] = q_idx


def _push_undo() -> None:
    """Push a deep copy of _raw onto the undo stack before a structural change."""
    stack = st.session_state.setdefault("_undo_stack", [])
    stack.append(copy.deepcopy(st.session_state["_raw"]))
    if len(stack) > 20:
        stack.pop(0)


def undo_last() -> None:
    """Restore the previous state from the undo stack."""
    stack = st.session_state.get("_undo_stack", [])
    if stack:
        st.session_state["_raw"] = stack.pop()
        _rebuild_session_keys()


def delete_session(s_idx: int) -> None:
    _push_undo()
    _sync_widgets_to_raw()
    del st.session_state["_raw"]["sessions"][s_idx]
    _renumber()
    _rebuild_session_keys()


def move_session(s_idx: int, direction: int) -> None:
    """Swap session at s_idx with neighbour. direction: -1 = up, +1 = down."""
    _push_undo()
    _sync_widgets_to_raw()
    sessions = st.session_state["_raw"]["sessions"]
    target = s_idx + direction
    sessions[s_idx], sessions[target] = sessions[target], sessions[s_idx]
    _renumber()
    _rebuild_session_keys()


def delete_query(s_idx: int, q_idx: int) -> None:
    _push_undo()
    _sync_widgets_to_raw()
    del st.session_state["_raw"]["sessions"][s_idx]["conversation"][q_idx]
    _renumber()
    _rebuild_session_keys()


def move_query(s_idx: int, q_idx: int, direction: int) -> None:
    _push_undo()
    _sync_widgets_to_raw()
    conv = st.session_state["_raw"]["sessions"][s_idx]["conversation"]
    target = q_idx + direction
    conv[q_idx], conv[target] = conv[target], conv[q_idx]
    _renumber()
    _rebuild_session_keys()


def add_query(s_idx: int) -> None:
    _push_undo()
    _sync_widgets_to_raw()
    conv = st.session_state["_raw"]["sessions"][s_idx]["conversation"]
    conv.append({"input": "", "answer": "", "query_id": str(uuid.uuid4()), "order": 0})
    _renumber()
    _rebuild_session_keys()


def add_session() -> None:
    _push_undo()
    _sync_widgets_to_raw()
    sessions = st.session_state["_raw"]["sessions"]
    sessions.append(
        {
            "session": 0,
            "date": datetime.now(_OSLO).strftime("%Y-%m-%d"),
            "session_id": str(uuid.uuid4()),
            "session_name": f"New session {len(sessions) + 1}",
            "init_query": "",
            "init_query_id": str(uuid.uuid4()),
            "conversation": [
                {"input": "", "answer": "", "query_id": str(uuid.uuid4()), "order": 0}
            ],
        }
    )
    _renumber()
    _rebuild_session_keys()


def build_export() -> str:
    _sync_widgets_to_raw()
    data = copy.deepcopy(st.session_state["_raw"])
    data["last_updated"] = datetime.now(_OSLO).isoformat()
    return json.dumps(data, ensure_ascii=False, indent=4)


def save_draft() -> None:
    """Sync widgets → _raw, write draft blob to GCS, update last-saved timestamp."""
    _sync_widgets_to_raw()
    data = copy.deepcopy(st.session_state["_raw"])
    data["last_updated"] = datetime.now(_OSLO).isoformat()
    write_blob(
        draft_blob_path(st.session_state["_loaded_dataset"]),
        json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8"),
    )
    st.session_state["_last_saved"] = datetime.now(_OSLO).strftime("%H:%M:%S")
    st.session_state["_from_draft"] = True


def publish() -> None:
    """Publish current state: save timestamped version snapshot + update canonical dataset."""
    _sync_widgets_to_raw()
    data = copy.deepcopy(st.session_state["_raw"])
    data["last_updated"] = datetime.now(_OSLO).isoformat()
    payload = json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8")
    ds = st.session_state["_loaded_dataset"]

    ts = datetime.now(_OSLO).strftime("%Y-%m-%dT%H-%M-%S")
    write_blob(version_blob_path(ds, ts), payload)
    write_blob(dataset_blob_path(ds), payload)
    delete_blob(draft_blob_path(ds))

    st.session_state["_from_draft"] = False
    st.session_state["_last_published"] = datetime.now(_OSLO).strftime("%H:%M:%S")
    st.session_state["_last_saved"] = None
    st.session_state["_show_publish_toast"] = True


def reset_to_original() -> None:
    """Delete draft blob from GCS and force reload from last published canonical on next rerun."""
    delete_blob(draft_blob_path(st.session_state["_loaded_dataset"]))
    st.session_state["_reset_to_original"] = True
    del st.session_state["_loaded_dataset"]


# ── Session attachment computation ────────────────────────────────────────────


@st.cache_data(ttl=120)
def _get_data_files_by_date(dataset: str) -> dict[str, list[str]]:
    """Return {date_str: [blob_paths]} for all supported data files in 01_data/."""
    from collections import defaultdict

    date_to_files: dict[str, list[str]] = defaultdict(list)
    for blob in list_data_blobs(dataset):
        match = _DATE_PATTERN.search(blob.name)
        if match:
            date_to_files[match.group(1)].append(blob.name)
    return dict(date_to_files)


def compute_session_attachments(dataset: str, sessions: list[dict]) -> list[list[str]]:
    """Compute attachment lists per session using the date-window logic.

    Mirrors assign_session_attachments() in dataset_module.py:
    each session gets files whose date falls in (prev_date, session_date].
    """
    date_to_files = _get_data_files_by_date(dataset)

    def _parse(s: str | None):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date() if s else None
        except ValueError:
            return None

    date_to_files_dt = {_parse(d): files for d, files in date_to_files.items() if _parse(d)}
    file_dates_sorted = sorted(date_to_files_dt.keys())

    seen: set[str] = set()
    prev_dt = None
    result: list[list[str]] = []

    for session in sessions:
        current_dt = _parse(session.get("date"))
        if current_dt is None:
            result.append([])
            continue

        candidates = [
            f
            for fd in file_dates_sorted
            if (prev_dt is None or fd > prev_dt) and fd <= current_dt
            for f in date_to_files_dt[fd]
        ]
        new_files = [f for f in candidates if f not in seen]
        seen.update(new_files)
        result.append(new_files)
        prev_dt = current_dt

    return result


# ── Attachment helpers ────────────────────────────────────────────────────────


def render_attachment_popover(path: str) -> None:
    """Render a popover button for a single attachment.

    File bytes are loaded lazily into session state on first user request —
    nothing is downloaded at render time.
    """
    fname = path.split("/")[-1]
    ext = Path(fname).suffix.lower()
    icon = FILE_ICONS.get(ext, "📎")
    bytes_key = f"_att_{path}"

    with st.popover(f"{icon} {fname}"):
        if bytes_key not in st.session_state:
            if st.button("📂 Load preview", key=f"load_{bytes_key}"):
                try:
                    st.session_state[bytes_key] = read_blob_bytes(path)
                except Exception as e:
                    st.error(f"Could not load: {e}")
        if st.session_state.get(bytes_key):
            render_file(fname, st.session_state[bytes_key])


def render_attachments_section(attachments: list[str]) -> None:
    """Render an attachments expander with a lazy popover preview per file."""
    if not attachments:
        return
    with st.expander(f"📎 Attachments ({len(attachments)})", expanded=False):
        for path in attachments:
            render_attachment_popover(path)


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dataset, tab_files, tab_results, tab_evals = st.tabs(
    ["📋 Dataset", "📁 Files", "📊 Results", "📈 Evals"]
)

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Dataset editor
# ════════════════════════════════════════════════════════════════════════════

with tab_dataset:
    # ── Autosave draft on every rerun ────────────────────────────────────────
    save_draft()

    # ── Status bar ───────────────────────────────────────────────────────────
    if st.session_state.pop("_show_publish_toast", False):
        st.toast(
            f"🚀 Published successfully at {st.session_state.get('_last_published')}",
            icon="✅",
        )

    if st.session_state.get("_last_published"):
        st.success(f"✅ Published at {st.session_state['_last_published']}", icon=None)
    elif st.session_state.get("_from_draft"):
        last = st.session_state.get("_last_saved")
        msg = f"📝 Draft — autosaved at {last}" if last else "📝 Loaded from draft"
        st.info(msg, icon=None)

    # Detect and offer fix for mojibake encoding
    _sample = json.dumps(st.session_state["_raw"], ensure_ascii=False)
    if "Ã" in _sample or "â€" in _sample or "Â§" in _sample:
        st.warning(
            "⚠️ Encoding corruption detected (Norwegian characters appear as `Ã¥`, `Ã¦` etc.). "
            "Click **Fix encoding** to repair.",
            icon=None,
        )
        st.button("🔧 Fix encoding", on_click=fix_encoding, type="primary")

    with st.expander("ℹ️ Dataset metadata", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.text_input(
            "📛 Dataset name", value=raw.get("dataset_name", ""), disabled=True
        )
        c2.text_input("🔑 Project ID", value=raw.get("project_id", ""), disabled=True)
        c3.text_input(
            "🕐 Last updated", value=raw.get("last_updated", ""), disabled=True
        )

    st.divider()

    sessions = st.session_state["_raw"]["sessions"]
    n_sessions = len(sessions)
    ds_session_attachments = compute_session_attachments(dataset, sessions)

    hdr_left, hdr_right = st.columns([0.7, 0.3])
    hdr_left.markdown(
        f"#### 💬 Sessions &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({n_sessions} total)</span>",
        unsafe_allow_html=True,
    )
    collapsed = st.session_state.get("_all_collapsed", False)
    if hdr_right.button(
        "⬆️ Collapse all" if not collapsed else "⬇️ Expand all",
        key="toggle_collapse",
        type="tertiary",
        use_container_width=True,
    ):
        st.session_state["_all_collapsed"] = not collapsed
        st.rerun()

    st.caption(
        "Click a session to expand or collapse it. You can edit all text directly in the fields."
    )
    st.write("")

    for s_idx, session in enumerate(sessions):
        n_queries = len(session["conversation"])
        sname = st.session_state.get(f"sname_{s_idx}", session.get("session_name", ""))
        sdate = st.session_state.get(f"sdate_{s_idx}", session.get("date", ""))
        label = f"📁 {sname or 'Unnamed session'}" + (f" — {sdate}" if sdate else "")

        with st.expander(
            label, expanded=not st.session_state.get("_all_collapsed", False)
        ):
            col_name, col_date, col_up, col_down, col_del = st.columns(
                [0.62, 0.16, 0.07, 0.07, 0.08]
            )
            col_name.text_input(
                "Session name",
                key=f"sname_{s_idx}",
                placeholder="Session name",
                help="Give the session a descriptive name",
            )
            col_date.text_input(
                "📅 Date",
                key=f"sdate_{s_idx}",
                placeholder="YYYY-MM-DD",
                help="Date of the session",
            )
            col_up.write("")
            col_up.button(
                "↑",
                key=f"up_session_{s_idx}",
                on_click=move_session,
                args=(s_idx, -1),
                help="Move session up",
                disabled=s_idx == 0,
                type="tertiary",
            )
            col_down.write("")
            col_down.button(
                "↓",
                key=f"down_session_{s_idx}",
                on_click=move_session,
                args=(s_idx, 1),
                help="Move session down",
                disabled=s_idx == n_sessions - 1,
                type="tertiary",
            )
            col_del.write("")
            col_del.button(
                "🗑️",
                key=f"del_session_{s_idx}",
                on_click=delete_session,
                args=(s_idx,),
                help="Permanently remove this session",
                type="tertiary",
            )

            with st.expander(
                "📝 Initial instruction", expanded=bool(session.get("init_query"))
            ):
                st.text_area(
                    "Initial instruction",
                    key=f"sinit_{s_idx}",
                    height=text_height(
                        st.session_state.get(
                            f"sinit_{s_idx}", session.get("init_query", "")
                        )
                    ),
                    label_visibility="collapsed",
                    placeholder="Add an opening instruction for this session...",
                    help="The opening instruction given to the agent for this session",
                )
                st.caption(f"🔑 `{session.get('init_query_id', '—')}`")

            render_attachments_section(ds_session_attachments[s_idx])

            cap_col, btn_col = st.columns([0.65, 0.35])
            cap_col.caption(
                f"🔢 {n_queries} {'query' if n_queries == 1 else 'queries'} in this session"
            )
            q_collapsed = st.session_state.get(f"_q_collapsed_{s_idx}", False)
            if btn_col.button(
                "⬆️ Collapse queries" if not q_collapsed else "⬇️ Expand queries",
                key=f"toggle_q_{s_idx}",
                type="tertiary",
                use_container_width=True,
            ):
                st.session_state[f"_q_collapsed_{s_idx}"] = not q_collapsed
                st.rerun()
            st.write("")

            for q_idx, query in enumerate(session["conversation"]):
                inp_val = st.session_state.get(
                    f"inp_{s_idx}_{q_idx}", query.get("input", "").strip()
                )
                ans_val = st.session_state.get(
                    f"ans_{s_idx}_{q_idx}", query.get("answer", "").strip()
                )
                has_answer = bool(ans_val.strip())
                n_queries = len(session["conversation"])

                with st.expander(
                    f"{'✅' if has_answer else '⬜'} Query {q_idx + 1}",
                    expanded=not st.session_state.get(f"_q_collapsed_{s_idx}", False),
                ):
                    qc_up, qc_down, qc_del, qc_spacer = st.columns(
                        [0.07, 0.07, 0.09, 0.77]
                    )
                    qc_up.button(
                        "↑",
                        key=f"up_q_{s_idx}_{q_idx}",
                        on_click=move_query,
                        args=(s_idx, q_idx, -1),
                        help="Move query up",
                        disabled=q_idx == 0,
                        type="tertiary",
                    )
                    qc_down.button(
                        "↓",
                        key=f"down_q_{s_idx}_{q_idx}",
                        on_click=move_query,
                        args=(s_idx, q_idx, 1),
                        help="Move query down",
                        disabled=q_idx == n_queries - 1,
                        type="tertiary",
                    )
                    qc_del.button(
                        "🗑️ Delete",
                        key=f"del_q_{s_idx}_{q_idx}",
                        on_click=delete_query,
                        args=(s_idx, q_idx),
                        help="Remove this query",
                        type="tertiary",
                    )
                    qc_spacer.caption(f"🔑 `{query.get('query_id', '—')}`")

                    st.markdown("**🧑‍💼 Query from lawyer**")
                    st.text_area(
                        "Query",
                        key=f"inp_{s_idx}_{q_idx}",
                        height=text_height(inp_val),
                        label_visibility="collapsed",
                        help="The question or instruction sent to the AI agent",
                    )
                    st.write("")
                    st.markdown("**✍️ Expected answer (ground truth)**")
                    st.text_area(
                        "Expected answer",
                        key=f"ans_{s_idx}_{q_idx}",
                        height=text_height(ans_val) if has_answer else 100,
                        label_visibility="collapsed",
                        placeholder="Fill in the expected answer...",
                        help="The correct answer as assessed by the lawyer — used as ground truth for evaluation",
                    )

            st.button(
                "➕ Add query",
                key=f"add_q_{s_idx}",
                on_click=add_query,
                args=(s_idx,),
                type="secondary",
                use_container_width=True,
            )

        st.write("")

    add_col, undo_col = st.columns([0.75, 0.25])
    add_col.button(
        "➕ Add session",
        on_click=add_session,
        type="secondary",
        use_container_width=True,
    )
    undo_col.button(
        "↩️ Undo",
        on_click=undo_last,
        type="secondary",
        use_container_width=True,
        disabled=not st.session_state.get("_undo_stack"),
        help="Undo the last structural change (delete, move, add). Up to 20 steps.",
    )

    st.divider()

    col_pub, col_reset = st.columns([0.75, 0.25])
    col_pub.button(
        "🚀 Publish",
        on_click=publish,
        type="primary",
        use_container_width=True,
        help="Save a versioned snapshot and update the canonical dataset file",
    )
    col_reset.button(
        "↩️ Reset to last published",
        on_click=reset_to_original,
        type="secondary",
        use_container_width=True,
        help="Discard draft and reload the last published version",
    )

    st.download_button(
        label="⬇️ Download current draft",
        data=build_export(),
        file_name=f"dataset_{dataset}_draft.json",
        mime="application/json",
        type="secondary",
        use_container_width=True,
    )

    with st.expander("🕘 Version history", expanded=False):
        versions = list_versions(dataset)
        if not versions:
            st.info(
                "No published versions yet. Hit **Publish** to create the first snapshot."
            )
        else:
            for blob in versions:
                vname = blob.name.split("/")[-1]
                ts_display = (
                    vname.replace(f"dataset_{dataset}_", "")
                    .replace(".json", "")
                    .replace("T", " ")
                    .replace("-", ":", 2)
                )
                vcol_name, vcol_size, vcol_dl = st.columns([0.55, 0.2, 0.25])
                vcol_name.markdown(f"📄 `{ts_display}`")
                vcol_size.caption(f"{(blob.size or 0) / 1024:.1f} KB")
                vcol_dl.download_button(
                    "⬇️ Download",
                    data=read_blob_bytes(blob.name),
                    file_name=vname,
                    mime="application/json",
                    key=f"dl_version_{blob.name}",
                    use_container_width=True,
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — File browser
# ════════════════════════════════════════════════════════════════════════════

with tab_files:
    all_blobs = list_data_blobs(dataset)
    all_blobs = sorted(all_blobs, key=lambda b: b.name)

    st.markdown(
        f"#### 📁 Files &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({len(all_blobs)} supported files)</span>",
        unsafe_allow_html=True,
    )

    with st.expander("⬆️ Upload file"):
        _uploaded = st.file_uploader(
            "Choose a file",
            type=[ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS],
            key="file_uploader",
        )
        if _uploaded is not None:
            _dest_path = f"datasets/{dataset}/01_data/{_uploaded.name}"
            if st.button("Upload to GCS", key="btn_upload_file"):
                _ct = (
                    mimetypes.guess_type(_uploaded.name)[0]
                    or "application/octet-stream"
                )
                upload_raw_blob(_dest_path, _uploaded.getvalue(), _ct)
                st.success(f"✅ Uploaded `{_uploaded.name}`")
                st.rerun()

    if not all_blobs:
        st.info(
            f"No supported files in `01_data/` for **{dataset}**. Upload one above."
        )
    else:
        # ── Filter & sort controls ────────────────────────────────────────────
        _fc1, _fc2, _fc3 = st.columns([0.4, 0.3, 0.3])

        _available_types = sorted({Path(b.name).suffix.lower() for b in all_blobs})
        _type_filter = _fc1.multiselect(
            "File type",
            options=_available_types,
            default=_available_types,
            format_func=lambda x: x.upper().lstrip("."),
            label_visibility="collapsed",
            placeholder="Filter by type…",
        )
        _sort_by = _fc2.selectbox(
            "Sort by",
            ["Name A→Z", "Name Z→A", "Date newest", "Date oldest", "Type"],
            label_visibility="collapsed",
            key="files_sort_by",
        )
        _search = _fc3.text_input(
            "Search",
            placeholder="Search filename…",
            label_visibility="collapsed",
            key="files_search",
        )

        # Apply type filter and search
        filtered_blobs = [
            b for b in all_blobs
            if Path(b.name).suffix.lower() in (_type_filter or _available_types)
            and _search.lower() in b.name.split("/")[-1].lower()
        ]

        # Apply sort
        def _blob_date(b):
            m = _DATE_PATTERN.search(b.name)
            return m.group(1) if m else ""

        if _sort_by == "Name A→Z":
            filtered_blobs.sort(key=lambda b: b.name.split("/")[-1].lower())
        elif _sort_by == "Name Z→A":
            filtered_blobs.sort(key=lambda b: b.name.split("/")[-1].lower(), reverse=True)
        elif _sort_by == "Date newest":
            filtered_blobs.sort(key=_blob_date, reverse=True)
        elif _sort_by == "Date oldest":
            filtered_blobs.sort(key=_blob_date)
        elif _sort_by == "Type":
            filtered_blobs.sort(key=lambda b: (Path(b.name).suffix.lower(), b.name.split("/")[-1].lower()))

        st.caption(
            f"{len(filtered_blobs)} of {len(all_blobs)} files · select a file on the left to preview"
        )
        st.write("")

        col_list, col_preview = st.columns([0.28, 0.72])

        filenames = [b.name.split("/")[-1] for b in filtered_blobs]
        file_labels = [
            f"{FILE_ICONS.get(Path(name).suffix.lower(), '📎')} {name}"
            for name in filenames
        ]

        with col_list:
            with st.container(height=550, border=True):
                selected_label = st.radio(
                    "Files",
                    file_labels,
                    label_visibility="collapsed",
                )
            if st.button(
                "🗑️ Move to trash", key="btn_trash_file", use_container_width=True
            ):
                st.session_state["_confirm_trash_file"] = selected_label
            _cur_name = selected_label.split(" ", 1)[-1]
            with st.expander("✏️ Rename"):
                _new_name = st.text_input(
                    "New filename",
                    value=_cur_name,
                    key=f"rename_{_cur_name}",
                    label_visibility="collapsed",
                )
                if st.button("Rename", key="btn_rename_file", use_container_width=True):
                    if _new_name and _new_name != _cur_name:
                        move_blob(
                            f"datasets/{dataset}/01_data/{_cur_name}",
                            f"datasets/{dataset}/01_data/{_new_name}",
                        )
                        st.success(f"Renamed to `{_new_name}`")
                        st.rerun()

        selected_idx = file_labels.index(selected_label)
        selected_blob = filtered_blobs[selected_idx]
        selected_name = filenames[selected_idx]
        selected_ext = Path(selected_name).suffix.lower()

        if st.session_state.get("_confirm_trash_file") == selected_label:
            st.warning(f"⚠️ Move **{selected_name}** to trash?")
            _col_yes, _col_no, _ = st.columns([0.12, 0.1, 0.78])
            if _col_yes.button("Yes", key="confirm_trash_file_yes"):
                trash_file(dataset, selected_blob.name)
                st.session_state.pop("_confirm_trash_file", None)
                st.rerun()
            if _col_no.button("Cancel", key="confirm_trash_file_no"):
                st.session_state.pop("_confirm_trash_file", None)
                st.rerun()

        with col_preview:
            st.markdown(f"**{FILE_ICONS.get(selected_ext, '📎')} {selected_name}**")
            size_kb = (selected_blob.size or 0) / 1024
            st.caption(f"{selected_ext.upper().lstrip('.')} · {size_kb:.1f} KB")
            st.divider()
            try:
                content = read_blob_bytes(selected_blob.name)
                if selected_ext == ".txt":
                    _txt_content = content.decode("utf-8", errors="ignore")
                    _edited_txt = st.text_area(
                        "Edit content",
                        value=_txt_content,
                        height=text_height(_txt_content, min_height=300),
                        key=f"txt_editor_{selected_blob.name}",
                        label_visibility="collapsed",
                    )
                    if st.button("💾 Save", key="btn_save_txt"):
                        upload_raw_blob(
                            selected_blob.name,
                            _edited_txt.encode("utf-8"),
                            "text/plain; charset=utf-8",
                        )
                        st.success("Saved.")
                        st.rerun()
                else:
                    render_file(selected_name, content)
            except Exception as e:
                st.error(f"❌ Could not render file: {e}")
                logger.error(f"Error rendering {selected_name}: {e}", exc_info=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Results viewer
# ════════════════════════════════════════════════════════════════════════════

with tab_results:
    result_blobs = list_result_blobs(dataset)

    if not result_blobs:
        st.warning(
            f"⚠️ No result files found in `04_results` for dataset **{dataset}**."
        )
        st.stop()

    # Build display labels for the selectbox
    result_labels = []
    for blob in result_blobs:
        fname = blob.name.split("/")[-1]
        model, ts_display = parse_result_filename(fname)
        result_labels.append(f"{model} — {ts_display}" if ts_display else fname)

    st.markdown(
        f"#### 📊 Results &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({len(result_blobs)} runs)</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Select a result run to compare model responses against the ground-truth answers."
    )
    st.write("")

    col_sel, col_tok, col_del = st.columns([0.72, 0.16, 0.12])
    with col_sel:
        selected_result_label = st.selectbox(
            "Result run",
            result_labels,
            index=0,
            label_visibility="collapsed",
        )
    with col_tok:
        if st.button("🔢 Update tokens", key="btn_update_tokens", use_container_width=True):
            st.session_state["_confirm_update_tokens"] = selected_result_label
    with col_del:
        if st.button("🗑️ Delete", key="btn_del_res", use_container_width=True):
            st.session_state["_confirm_del_res"] = selected_result_label

    if st.session_state.get("_confirm_update_tokens") == selected_result_label:
        st.info(f"⏳ Fetch token counts from LangSmith for **{selected_result_label}**?")
        _col_yes, _col_no, _ = st.columns([0.12, 0.1, 0.78])
        if _col_yes.button("Yes", key="confirm_update_tokens_yes"):
            selected_idx = result_labels.index(selected_result_label)
            selected_blob = result_blobs[selected_idx]
            try:
                _rd = json.loads(read_blob_bytes(selected_blob.name).decode("utf-8"))
                with st.spinner("Fetching token counts from LangSmith…"):
                    update_token_counts(selected_blob.name, _rd)
                st.session_state.pop("_confirm_update_tokens", None)
                st.success("✅ Token counts updated.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed to update token counts: {e}")
                logger.error("update_token_counts failed", exc_info=True)
        if _col_no.button("Cancel", key="confirm_update_tokens_no"):
            st.session_state.pop("_confirm_update_tokens", None)
            st.rerun()

    if st.session_state.get("_confirm_del_res") == selected_result_label:
        st.warning(f"⚠️ Move **{selected_result_label}** to trash?")
        _col_yes, _col_no, _ = st.columns([0.12, 0.1, 0.78])
        if _col_yes.button("Yes", key="confirm_del_res_yes"):
            selected_idx = result_labels.index(selected_result_label)
            selected_blob = result_blobs[selected_idx]
            trash_result_blob(dataset, selected_blob.name)
            st.session_state.pop("_confirm_del_res", None)
            st.rerun()
        if _col_no.button("Cancel", key="confirm_del_res_no"):
            st.session_state.pop("_confirm_del_res", None)
            st.rerun()

    selected_result_idx = result_labels.index(selected_result_label)
    selected_result_blob = result_blobs[selected_result_idx]

    try:
        result_data: dict = json.loads(
            read_blob_bytes(selected_result_blob.name).decode("utf-8")
        )
    except Exception as e:
        st.error(f"❌ Could not load result file: {e}")
        st.stop()

    # ── Metadata strip ────────────────────────────────────────────────────────
    with st.expander("ℹ️ Run metadata", expanded=False):
        m1, m2, m3, m4 = st.columns(4)
        m1.text_input("Model", value=result_data.get("llm_model", "—"), disabled=True, key="res_meta_model")
        m2.text_input("Agent type", value=result_data.get("agent_type", "—"), disabled=True, key="res_meta_agent")
        m3.text_input("Eval run ID", value=result_data.get("eval_run_id", "—"), disabled=True, key="res_meta_run_id")
        m4.text_input("Dataset", value=result_data.get("dataset_name", "—"), disabled=True, key="res_meta_dataset")

        n1, n2, n3, n4 = st.columns(4)
        n1.text_input("Project ID", value=result_data.get("project_id", "—"), disabled=True, key="res_meta_proj")
        n2.text_input("User ID", value=result_data.get("user_id", "—"), disabled=True, key="res_meta_user")
        n3.text_input("Last updated", value=result_data.get("last_updated", "—"), disabled=True, key="res_meta_updated")

        time_usage = result_data.get("time_counts") or result_data.get("time_usage") or {}
        if time_usage:
            _render_time_inputs(time_usage, key_prefix="res_meta")

        token_counts = result_data.get("token_counts")
        if token_counts and isinstance(token_counts, dict):
            _render_token_metrics(token_counts)

    st.divider()

    # ── Sessions & conversations ───────────────────────────────────────────────
    result_sessions = result_data.get("sessions", [])
    n_result_sessions = len(result_sessions)

    # Summary counts
    total_queries = sum(len(s.get("conversation", [])) for s in result_sessions)
    answered = sum(
        1
        for s in result_sessions
        for q in s.get("conversation", [])
        if q.get("model_response", "").strip()
    )
    st.caption(
        f"**{n_result_sessions}** sessions · **{total_queries}** queries · **{answered}** with model response"
    )
    st.write("")

    for s_idx, session in enumerate(result_sessions):
        sname = session.get("session_name", f"Session {s_idx + 1}")
        sdate = session.get("date", "")
        label = f"📁 {sname}" + (f" — {sdate}" if sdate else "")

        with st.expander(label, expanded=True):
            conversation = session.get("conversation", [])
            res_cap_col, res_btn_col = st.columns([0.65, 0.35])
            _runtime_sid = session.get("runtime_session_id", "")
            res_cap_col.caption(
                f"🔢 {len(conversation)} {'query' if len(conversation) == 1 else 'queries'}"
                + (f" · session_id: `{_runtime_sid}`" if _runtime_sid else "")
            )
            res_q_collapsed = st.session_state.get(f"_res_q_collapsed_{s_idx}", False)
            if res_btn_col.button(
                "⬆️ Collapse queries" if not res_q_collapsed else "⬇️ Expand queries",
                key=f"toggle_res_q_{s_idx}",
                type="tertiary",
                use_container_width=True,
            ):
                st.session_state[f"_res_q_collapsed_{s_idx}"] = not res_q_collapsed
                st.rerun()

            render_attachments_section(session.get("attachments", []))

            session_tokens = session.get("token_counts")
            if session_tokens and isinstance(session_tokens, dict):
                _render_token_metrics(session_tokens)

            if session.get("init_query"):
                with st.expander("📝 Initial instruction", expanded=False):
                    st.text(session["init_query"])
                    init_tokens = session.get("init_query_token_count")
                    if init_tokens and isinstance(init_tokens, dict):
                        _render_token_metrics(init_tokens)

            for q_idx, q in enumerate(conversation):
                inp = q.get("input", "").strip()
                answer = q.get("answer", "").strip()
                model_response = q.get("model_response", "").strip()
                has_response = bool(model_response)
                q_time = q.get("time_counts") or {}
                turn_duration = q_time.get("duration_seconds") or q.get("turn_duration")
                duration_str = f" ⏱️ {turn_duration:.1f}s" if turn_duration else ""

                with st.expander(
                    f"{'✅' if has_response else '⬜'} Query {q_idx + 1}{duration_str}",
                    expanded=not st.session_state.get(
                        f"_res_q_collapsed_{s_idx}", False
                    ),
                ):
                    st.markdown(f"**🧑‍💼 Query**")
                    st.markdown(inp or "_No input_")
                    st.write("")

                    col_gt, col_mr = st.columns(2)
                    with col_gt:
                        st.markdown("**✍️ Ground truth**")
                        st.text_area(
                            "Ground truth",
                            value=answer or "No ground truth",
                            height=text_height(answer) if answer else 100,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"res_gt_{s_idx}_{q_idx}",
                        )
                    with col_mr:
                        st.markdown("**🤖 Model response**")
                        st.text_area(
                            "Model response",
                            value=model_response or "No response",
                            height=text_height(model_response)
                            if model_response
                            else 100,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"res_mr_{s_idx}_{q_idx}",
                        )

                    q_tokens = q.get("token_counts")
                    if q_tokens and isinstance(q_tokens, dict):
                        _render_token_metrics(q_tokens)

        st.write("")


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — LLM-as-judge eval viewer
# ════════════════════════════════════════════════════════════════════════════

with tab_evals:
    eval_blobs = list_eval_blobs(dataset)

    if not eval_blobs:
        st.warning(f"⚠️ No eval files found in `05_evals` for dataset **{dataset}**.")
        st.stop()

    # Build display labels
    eval_labels = []
    for blob in eval_blobs:
        fname = blob.name.split("/")[-1]
        model, agent_type, run_id = parse_eval_filename(fname)
        if agent_type:
            eval_labels.append(f"{model} · {agent_type} · {run_id}")
        else:
            eval_labels.append(fname)

    n_eval_runs = len(eval_blobs)
    st.markdown(
        f"#### 📈 Evals &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({n_eval_runs} run{'s' if n_eval_runs != 1 else ''})</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        "LLM-as-judge evaluation results. Select a run to inspect scores per test case."
    )
    st.write("")

    selected_eval_label = st.selectbox(
        "Eval run",
        eval_labels,
        index=0,
        label_visibility="collapsed",
    )

    selected_eval_idx = eval_labels.index(selected_eval_label)
    selected_eval_blob = eval_blobs[selected_eval_idx]

    try:
        eval_data: dict = json.loads(
            read_blob_bytes(selected_eval_blob.name).decode("utf-8")
        )
    except Exception as e:
        st.error(f"❌ Could not load eval file: {e}")
        st.stop()

    # ── Join matching result file ──────────────────────────────────────────────
    _eval_run_id = eval_data.get("eval_run_id", "")
    _matched_result = _load_matched_result(dataset, _eval_run_id) if _eval_run_id else {}
    _result_sessions = {
        s["session_name"]: s
        for s in _matched_result.get("sessions", [])
        if s.get("session_name")
    }

    # ── Metadata strip ─────────────────────────────────────────────────────────
    with st.expander("ℹ️ Run metadata", expanded=False):
        e1, e2, e3, e4 = st.columns(4)
        e1.text_input("LLM model", value=eval_data.get("llm_model", "—"), disabled=True, key="eval_meta_model")
        e2.text_input("Agent type", value=eval_data.get("agent_type", _matched_result.get("agent_type", "—")), disabled=True, key="eval_meta_agent")
        e3.text_input("Eval run ID", value=_eval_run_id or "—", disabled=True, key="eval_meta_run")
        e4.text_input("Created at", value=eval_data.get("created_at", "—"), disabled=True, key="eval_meta_created")

        f1, f2, f3, f4 = st.columns(4)
        f1.text_input("Dataset", value=eval_data.get("dataset_name", "—"), disabled=True, key="eval_meta_dataset")
        f2.text_input("Project ID", value=eval_data.get("project_id", _matched_result.get("project_id", "—")), disabled=True, key="eval_meta_proj")
        f3.text_input("User ID", value=eval_data.get("user_id", _matched_result.get("user_id", "—")), disabled=True, key="eval_meta_user")

        # Time and tokens from matched result file (eval file doesn't store these)
        time_usage = _matched_result.get("time_counts") or _matched_result.get("time_usage") or {}
        if time_usage:
            _render_time_inputs(time_usage, key_prefix="eval_meta")

        token_counts = _matched_result.get("token_counts")
        if token_counts and isinstance(token_counts, dict):
            _render_token_metrics(token_counts)

    st.divider()

    # ── Flatten all test results from all session results ──────────────────────
    raw_results: list[dict] = eval_data.get("results") or []

    all_test_results: list[dict] = []
    for session_result in raw_results:
        if isinstance(session_result, dict):
            all_test_results.extend(session_result.get("test_results") or [])

    if not all_test_results:
        st.info("No test results found in this eval run.")
        st.stop()

    # ── Summary metrics ────────────────────────────────────────────────────────
    total_cases = len(all_test_results)
    passed_cases = sum(1 for t in all_test_results if t.get("success"))

    metric_scores: dict[str, list[float]] = {}
    metric_passes: dict[str, list[bool]] = {}
    for t in all_test_results:
        for m in t.get("metrics_data") or []:
            mname = m.get("name", "unknown")
            score = m.get("score")
            success = m.get("success")
            if score is not None:
                metric_scores.setdefault(mname, []).append(score)
            if success is not None:
                metric_passes.setdefault(mname, []).append(success)

    sum_cols = st.columns(2 + len(metric_scores))
    sum_cols[0].metric("Test cases", total_cases)
    sum_cols[1].metric("Overall pass rate", f"{passed_cases / total_cases:.0%}" if total_cases else "—")
    for i, metric_name in enumerate(metric_scores):
        scores = metric_scores[metric_name]
        passes = metric_passes.get(metric_name, [])
        avg_score = sum(scores) / len(scores) if scores else None
        pass_rate = sum(passes) / len(passes) if passes else None
        sum_cols[2 + i].metric(
            f"{metric_name.title()} (avg)",
            f"{avg_score:.2f}" if avg_score is not None else "—",
            delta=f"{pass_rate:.0%} pass" if pass_rate is not None else None,
        )

    st.divider()

    # ── Group test results by session, ordered by session number ──────────────
    sessions_map: dict[str, dict] = {}
    for t in all_test_results:
        meta = t.get("additional_metadata") or {}
        sname = meta.get("session_name") or "Unknown session"
        snum = meta.get("session") if meta.get("session") is not None else float("inf")
        if sname not in sessions_map:
            sessions_map[sname] = {"session": snum, "turns": []}
        sessions_map[sname]["turns"].append(t)

    # Sort sessions by session number, turns within each session by turn_order
    sorted_sessions = sorted(sessions_map.items(), key=lambda x: x[1]["session"])
    for _, sdata in sorted_sessions:
        sdata["turns"].sort(
            key=lambda t: int((t.get("additional_metadata") or {}).get("turn_order") or 0)
        )

    n_eval_sessions = len(sorted_sessions)
    total_turns = sum(len(s["turns"]) for _, s in sorted_sessions)
    st.caption(f"**{n_eval_sessions}** sessions · **{total_turns}** turns")
    st.write("")

    # ── Sessions ───────────────────────────────────────────────────────────────
    for s_idx, (sname, sdata) in enumerate(sorted_sessions):
        turns = sdata["turns"]
        label = f"📁 {sname}"
        result_session = _result_sessions.get(sname, {})

        with st.expander(label, expanded=True):
            ev_cap_col, ev_btn_col = st.columns([0.65, 0.35])
            _ev_runtime_sid = result_session.get("runtime_session_id", "")
            ev_cap_col.caption(
                f"🔢 {len(turns)} {'turn' if len(turns) == 1 else 'turns'}"
                + (f" · session_id: `{_ev_runtime_sid}`" if _ev_runtime_sid else "")
            )
            ev_q_collapsed = st.session_state.get(f"_ev_q_collapsed_{s_idx}", False)
            if ev_btn_col.button(
                "⬆️ Collapse turns" if not ev_q_collapsed else "⬇️ Expand turns",
                key=f"toggle_ev_q_{s_idx}",
                type="tertiary",
                use_container_width=True,
            ):
                st.session_state[f"_ev_q_collapsed_{s_idx}"] = not ev_q_collapsed
                st.rerun()

            render_attachments_section(result_session.get("attachments", []))

            session_tokens = result_session.get("token_counts")
            if session_tokens and isinstance(session_tokens, dict):
                _render_token_metrics(session_tokens)

            for t_idx, test in enumerate(turns):
                success = test.get("success", False)
                meta = test.get("additional_metadata") or {}
                turn_order = meta.get("turn_order", t_idx + 1)
                metrics_data = test.get("metrics_data") or []

                score_parts = []
                for m in metrics_data:
                    s = m.get("score")
                    score_parts.append(f"{m.get('name', '?')}: {s:.2f}" if s is not None else m.get("name", "?"))
                score_summary = " · ".join(score_parts)

                turn_label = f"{'✅' if success else '❌'} Turn {turn_order}" + (f" — {score_summary}" if score_summary else "")

                with st.expander(turn_label, expanded=not ev_q_collapsed):
                    inp = test.get("input", "").strip()
                    actual = test.get("actual_output", "").strip()
                    expected = test.get("expected_output", "").strip()

                    st.markdown("**🧑‍💼 Query**")
                    st.markdown(inp or "_No input_")
                    st.write("")

                    col_exp, col_act = st.columns(2)
                    with col_exp:
                        st.markdown("**✍️ Ground truth**")
                        st.text_area(
                            "Expected",
                            value=expected or "—",
                            height=text_height(expected) if expected else 80,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"eval_exp_{selected_eval_idx}_{s_idx}_{t_idx}",
                        )
                    with col_act:
                        st.markdown("**🤖 Model response**")
                        st.text_area(
                            "Actual",
                            value=actual or "—",
                            height=text_height(actual) if actual else 80,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"eval_act_{selected_eval_idx}_{s_idx}_{t_idx}",
                        )

                    # Token counts for this turn (from joined result data if present)
                    turn_tokens = test.get("token_counts")
                    if turn_tokens and isinstance(turn_tokens, dict):
                        _render_token_metrics(turn_tokens)

                    if metrics_data:
                        st.write("")
                        st.markdown("**📊 Metrics**")
                        for m in metrics_data:
                            m_name = m.get("name", "unknown")
                            m_score = m.get("score")
                            m_pass = m.get("success")
                            m_reason = m.get("reason", "")
                            m_threshold = m.get("threshold")
                            m_eval_model = m.get("evaluation_model", "")
                            badge = "✅" if m_pass else "❌"
                            score_str = f"{m_score:.3f}" if m_score is not None else "—"
                            threshold_str = f"(threshold: {m_threshold})" if m_threshold is not None else ""
                            model_str = f" · evaluated by `{m_eval_model}`" if m_eval_model else ""
                            st.markdown(f"{badge} **{m_name}** — score: `{score_str}` {threshold_str}{model_str}")
                            if m_reason:
                                st.caption(m_reason)

                    st.write("")
                    st.caption(f"query_id: `{meta.get('query_id', '—')}` · turn: `{turn_order}`")

        st.write("")
