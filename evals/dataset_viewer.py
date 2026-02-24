import copy
import email
import json
import logging
import math
import os
import re
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

if not Path(".").resolve().name == "evals":
    os.chdir("./evals")

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
    _bucket().blob(blob_path).upload_from_string(data)


def delete_blob(blob_path: str) -> None:
    blob = _bucket().blob(blob_path)
    if blob.exists():
        blob.delete()


def list_dataset_names() -> list[str]:
    client = get_gcs_client()
    blobs = client.list_blobs(BUCKET_NAME, prefix="datasets/", delimiter="/")
    _ = list(blobs)  # consume iterator to populate prefixes
    return sorted(
        p.replace("datasets/", "").rstrip("/")
        for p in blobs.prefixes
        if p != "datasets/"
    )


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
    blobs = [b for b in client.list_blobs(BUCKET_NAME, prefix=prefix) if not b.name.endswith("/")]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


def list_data_blobs(dataset: str) -> list[storage.Blob]:
    """Return blobs under datasets/<dataset>/01_data/ with supported extensions."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/01_data/"
    return [
        b for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/") and Path(b.name).suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def list_result_blobs(dataset: str) -> list[storage.Blob]:
    """Return blobs under datasets/<dataset>/04_results/ (JSON files), newest first."""
    client = get_gcs_client()
    prefix = f"datasets/{dataset}/04_results/"
    blobs = [
        b for b in client.list_blobs(BUCKET_NAME, prefix=prefix)
        if not b.name.endswith("/") and b.name.endswith(".json")
    ]
    return sorted(blobs, key=lambda b: b.name, reverse=True)


_RESULT_RE = re.compile(r"^(.+)_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.json$")


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


# ── Header ────────────────────────────────────────────────────────────────────

st.title("📂 Dataset Viewer")
st.caption("Select a dataset, edit the content, and download the revised version.")

st.divider()

# ── Dataset selection ─────────────────────────────────────────────────────────

dataset_names = list_dataset_names()

st.markdown("#### 🗂️ Select dataset")
dataset = st.selectbox(
    "Dataset",
    dataset_names,
    index=0,
    label_visibility="collapsed",
)
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
            raw: dict = json.loads(read_blob_bytes(dataset_blob_path(dataset)).decode("utf-8"))
            st.session_state["_from_draft"] = False
    except NotFound:
        st.error(
            f"⚠️ No dataset file found for **{dataset}**.\n\n"
            f"`datasets/{dataset}/dataset_{dataset}.json` does not exist in the bucket.",
            icon=None,
        )
        st.stop()

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

def text_height(text: str, min_height: int = 100, max_height: int = 800, chars_per_line: int = 90) -> int:
    lines = text.split("\n")
    total_lines = sum(max(1, math.ceil(len(line) / chars_per_line)) for line in lines)
    return max(min_height, min(max_height, total_lines * 22 + 50))


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".eml", ".docx", ".xlsx"}

FILE_ICONS = {
    ".pdf":  "📄",
    ".txt":  "📝",
    ".eml":  "📧",
    ".docx": "📝",
    ".xlsx": "📊",
}


def render_file(filename: str, content: bytes) -> None:
    """Render a supported file inline."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        st.pdf(BytesIO(content))

    elif ext == ".txt":
        st.text(content.decode("utf-8", errors="ignore"))

    elif ext == ".eml":
        msg = email.message_from_bytes(content)
        st.markdown(f"**From:** {msg.get('From', '')}")
        st.markdown(f"**To:** {msg.get('To', '')}")
        st.markdown(f"**Subject:** {msg.get('Subject', '')}")
        st.markdown(f"**Date:** {msg.get('Date', '')}")
        st.divider()
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    st.text(part.get_payload(decode=True).decode("utf-8", errors="ignore"))
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
        session["session_name"] = st.session_state.get(f"sname_{s_idx}", session.get("session_name", ""))
        session["date"] = st.session_state.get(f"sdate_{s_idx}", session.get("date", ""))
        session["init_query"] = st.session_state.get(f"sinit_{s_idx}", session.get("init_query", ""))
        for q_idx, query in enumerate(session["conversation"]):
            query["input"] = st.session_state.get(f"inp_{s_idx}_{q_idx}", query.get("input", ""))
            query["answer"] = st.session_state.get(f"ans_{s_idx}_{q_idx}", query.get("answer", ""))


def _rebuild_session_keys() -> None:
    """Clear and re-initialise all index-based widget keys from _raw."""
    for key in [k for k in st.session_state if k.startswith(("sname_", "sdate_", "sinit_", "inp_", "ans_"))]:
        del st.session_state[key]
    for s_idx, session in enumerate(st.session_state["_raw"]["sessions"]):
        st.session_state[f"sname_{s_idx}"] = session.get("session_name", "")
        st.session_state[f"sdate_{s_idx}"] = session.get("date", "")
        st.session_state[f"sinit_{s_idx}"] = session.get("init_query", "")
        for q_idx, query in enumerate(session["conversation"]):
            st.session_state[f"inp_{s_idx}_{q_idx}"] = query.get("input", "").strip()
            st.session_state[f"ans_{s_idx}_{q_idx}"] = query.get("answer", "").strip()


def delete_session(s_idx: int) -> None:
    _sync_widgets_to_raw()
    del st.session_state["_raw"]["sessions"][s_idx]
    _rebuild_session_keys()


def move_session(s_idx: int, direction: int) -> None:
    """Swap session at s_idx with neighbour. direction: -1 = up, +1 = down."""
    _sync_widgets_to_raw()
    sessions = st.session_state["_raw"]["sessions"]
    target = s_idx + direction
    sessions[s_idx], sessions[target] = sessions[target], sessions[s_idx]
    _rebuild_session_keys()


def delete_query(s_idx: int, q_idx: int) -> None:
    _sync_widgets_to_raw()
    del st.session_state["_raw"]["sessions"][s_idx]["conversation"][q_idx]
    _rebuild_session_keys()


def move_query(s_idx: int, q_idx: int, direction: int) -> None:
    _sync_widgets_to_raw()
    conv = st.session_state["_raw"]["sessions"][s_idx]["conversation"]
    target = q_idx + direction
    conv[q_idx], conv[target] = conv[target], conv[q_idx]
    _rebuild_session_keys()


def add_query(s_idx: int) -> None:
    import uuid
    _sync_widgets_to_raw()
    conv = st.session_state["_raw"]["sessions"][s_idx]["conversation"]
    next_order = max((q.get("order", 0) for s in st.session_state["_raw"]["sessions"] for q in s["conversation"]), default=0) + 1
    conv.append({"input": "", "answer": "", "query_id": str(uuid.uuid4()), "order": next_order})
    _rebuild_session_keys()


def add_session() -> None:
    import uuid
    _sync_widgets_to_raw()
    sessions = st.session_state["_raw"]["sessions"]
    next_order = max((q.get("order", 0) for s in sessions for q in s["conversation"]), default=0) + 1
    sessions.append({
        "session": len(sessions),
        "date": datetime.now(_OSLO).strftime("%Y-%m-%d"),
        "session_id": str(uuid.uuid4()),
        "session_name": f"New session {len(sessions) + 1}",
        "init_query": "",
        "conversation": [
            {"input": "", "answer": "", "query_id": str(uuid.uuid4()), "order": next_order}
        ],
    })
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
    write_blob(draft_blob_path(st.session_state["_loaded_dataset"]), json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8"))
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


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dataset, tab_files, tab_results = st.tabs(["📋 Dataset", "📁 Files", "📊 Results"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Dataset editor
# ════════════════════════════════════════════════════════════════════════════

with tab_dataset:

    # ── Autosave draft on every rerun ────────────────────────────────────────
    save_draft()

    # ── Status bar ───────────────────────────────────────────────────────────
    if st.session_state.pop("_show_publish_toast", False):
        st.toast(f"🚀 Published successfully at {st.session_state.get('_last_published')}", icon="✅")

    if st.session_state.get("_last_published"):
        st.success(f"✅ Published at {st.session_state['_last_published']}", icon=None)
    elif st.session_state.get("_from_draft"):
        last = st.session_state.get("_last_saved")
        msg = f"📝 Draft — autosaved at {last}" if last else "📝 Loaded from draft"
        st.info(msg, icon=None)

    with st.expander("ℹ️ Dataset metadata", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.text_input("📛 Dataset name", value=raw.get("dataset_name", ""), disabled=True)
        c2.text_input("🔑 Project ID", value=raw.get("project_id", ""), disabled=True)
        c3.text_input("🕐 Last updated", value=raw.get("last_updated", ""), disabled=True)

    st.divider()

    sessions = st.session_state["_raw"]["sessions"]
    n_sessions = len(sessions)

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

    st.caption("Click a session to expand or collapse it. You can edit all text directly in the fields.")
    st.write("")

    for s_idx, session in enumerate(sessions):
        n_queries = len(session["conversation"])
        sname = st.session_state.get(f"sname_{s_idx}", session.get("session_name", ""))
        sdate = st.session_state.get(f"sdate_{s_idx}", session.get("date", ""))
        label = f"📁 {sname or 'Unnamed session'}" + (f" — {sdate}" if sdate else "")

        with st.expander(label, expanded=not st.session_state.get("_all_collapsed", False)):
            col_name, col_date, col_up, col_down, col_del = st.columns([0.62, 0.16, 0.07, 0.07, 0.08])
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

            if session.get("init_query"):
                with st.expander("📝 Initial instruction", expanded=False):
                    st.text_area(
                        "Initial instruction",
                        key=f"sinit_{s_idx}",
                        height=text_height(st.session_state.get(f"sinit_{s_idx}", session.get("init_query", ""))),
                        label_visibility="collapsed",
                        help="The opening instruction given to the agent for this session",
                    )

            st.caption(f"🔢 {n_queries} {'query' if n_queries == 1 else 'queries'} in this session")
            st.write("")

            for q_idx, query in enumerate(session["conversation"]):
                order = query.get("order", q_idx + 1)
                inp_val = st.session_state.get(f"inp_{s_idx}_{q_idx}", query.get("input", "").strip())
                ans_val = st.session_state.get(f"ans_{s_idx}_{q_idx}", query.get("answer", "").strip())
                has_answer = bool(ans_val.strip())
                n_queries = len(session["conversation"])

                with st.expander(f"{'✅' if has_answer else '⬜'} Query {order}", expanded=True):
                    qc_up, qc_down, qc_del, qc_spacer = st.columns([0.07, 0.07, 0.09, 0.77])
                    qc_up.button(
                        "↑", key=f"up_q_{s_idx}_{q_idx}",
                        on_click=move_query, args=(s_idx, q_idx, -1),
                        help="Move query up", disabled=q_idx == 0, type="tertiary",
                    )
                    qc_down.button(
                        "↓", key=f"down_q_{s_idx}_{q_idx}",
                        on_click=move_query, args=(s_idx, q_idx, 1),
                        help="Move query down", disabled=q_idx == n_queries - 1, type="tertiary",
                    )
                    qc_del.button(
                        "🗑️ Delete", key=f"del_q_{s_idx}_{q_idx}",
                        on_click=delete_query, args=(s_idx, q_idx),
                        help="Remove this query", type="tertiary",
                    )

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

    st.button(
        "➕ Add session",
        on_click=add_session,
        type="secondary",
        use_container_width=True,
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
            st.info("No published versions yet. Hit **Publish** to create the first snapshot.")
        else:
            for blob in versions:
                vname = blob.name.split("/")[-1]
                ts_display = vname.replace(f"dataset_{dataset}_", "").replace(".json", "").replace("T", " ").replace("-", ":", 2)
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

    if not all_blobs:
        st.warning(f"⚠️ No supported files found in `01_data` for dataset **{dataset}**.")
        st.stop()

    all_blobs = sorted(all_blobs, key=lambda b: b.name)

    st.markdown(
        f"#### 📁 Files &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({len(all_blobs)} supported files)</span>",
        unsafe_allow_html=True,
    )
    st.caption("Select a file on the left to preview its contents.")
    st.write("")

    col_list, col_preview = st.columns([0.28, 0.72])

    filenames = [b.name.split("/")[-1] for b in all_blobs]
    file_labels = [
        f"{FILE_ICONS.get(Path(name).suffix.lower(), '📎')} {name}"
        for name in filenames
    ]

    with col_list:
        with st.container(height=600, border=True):
            selected_label = st.radio(
                "Files",
                file_labels,
                label_visibility="collapsed",
            )

    selected_idx = file_labels.index(selected_label)
    selected_blob = all_blobs[selected_idx]
    selected_name = filenames[selected_idx]
    selected_ext = Path(selected_name).suffix.lower()

    with col_preview:
        st.markdown(f"**{FILE_ICONS.get(selected_ext, '📎')} {selected_name}**")
        size_kb = (selected_blob.size or 0) / 1024
        st.caption(f"{selected_ext.upper().lstrip('.')} · {size_kb:.1f} KB")
        st.divider()
        try:
            content = read_blob_bytes(selected_blob.name)
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
        st.warning(f"⚠️ No result files found in `04_results` for dataset **{dataset}**.")
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
    st.caption("Select a result run to compare model responses against the ground-truth answers.")
    st.write("")

    selected_result_label = st.selectbox(
        "Result run",
        result_labels,
        index=0,
        label_visibility="collapsed",
    )

    selected_result_idx = result_labels.index(selected_result_label)
    selected_result_blob = result_blobs[selected_result_idx]

    try:
        result_data: dict = json.loads(read_blob_bytes(selected_result_blob.name).decode("utf-8"))
    except Exception as e:
        st.error(f"❌ Could not load result file: {e}")
        st.stop()

    # ── Metadata strip ────────────────────────────────────────────────────────
    with st.expander("ℹ️ Run metadata", expanded=False):
        m1, m2, m3, m4 = st.columns(4)
        m1.text_input("Model", value=result_data.get("llm_model", "—"), disabled=True)
        m2.text_input("Dataset", value=result_data.get("dataset_name", "—"), disabled=True)
        m3.text_input("Last updated", value=result_data.get("last_updated", "—"), disabled=True)
        m4.text_input("Custom agent", value=str(result_data.get("custom_agent", "—")), disabled=True)

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
    st.caption(f"**{n_result_sessions}** sessions · **{total_queries}** queries · **{answered}** with model response")
    st.write("")

    for s_idx, session in enumerate(result_sessions):
        sname = session.get("session_name", f"Session {s_idx + 1}")
        sdate = session.get("date", "")
        label = f"📁 {sname}" + (f" — {sdate}" if sdate else "")

        with st.expander(label, expanded=True):
            conversation = session.get("conversation", [])
            st.caption(f"🔢 {len(conversation)} {'query' if len(conversation) == 1 else 'queries'}")

            if session.get("init_query"):
                with st.expander("📝 Initial instruction", expanded=False):
                    st.text(session["init_query"])

            for q in conversation:
                order = q.get("order", "?")
                inp = q.get("input", "").strip()
                answer = q.get("answer", "").strip()
                model_response = q.get("model_response", "").strip()
                has_response = bool(model_response)

                with st.expander(
                    f"{'✅' if has_response else '⬜'} Query {order}",
                    expanded=True,
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
                            key=f"res_gt_{s_idx}_{order}",
                        )
                    with col_mr:
                        st.markdown("**🤖 Model response**")
                        st.text_area(
                            "Model response",
                            value=model_response or "No response",
                            height=text_height(model_response) if model_response else 100,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"res_mr_{s_idx}_{order}",
                        )

        st.write("")
