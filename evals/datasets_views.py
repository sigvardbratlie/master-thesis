import copy
import email
import json
import logging
import math
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_OSLO = ZoneInfo("Europe/Oslo")
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import streamlit as st
from docx import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not Path(".").resolve().name == "evals":
    os.chdir("./evals")

st.set_page_config(page_title="📂 Dataset Viewer", layout="wide")

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📂 Dataset Viewer")
st.caption("Select a dataset, edit the content, and download the revised version.")

st.divider()

# ── Dataset selection ─────────────────────────────────────────────────────────

dataset_names = sorted(
    folder.name
    for folder in Path("./datasets").iterdir()
    if folder.is_dir()
)

st.markdown("#### 🗂️ Select dataset")
dataset = st.selectbox(
    "Dataset",
    dataset_names,
    index=0,
    label_visibility="collapsed",
)
if not dataset:
    st.stop()

dataset_file = Path("./datasets") / dataset / f"dataset_{dataset}.json"
data_dir = Path("./datasets") / dataset / "01_data"

if not dataset_file.exists():
    st.warning(f"⚠️ No data file found for **{dataset}**.")
    st.stop()

# ── Autosave path ─────────────────────────────────────────────────────────────

def autosave_path(ds: str) -> Path:
    return Path("./datasets") / ds / f"dataset_{ds}_autosave.json"


# ── Load into session_state (reset on dataset change) ────────────────────────

if st.session_state.get("_loaded_dataset") != dataset:
    _autosave = autosave_path(dataset)
    _force_original = st.session_state.pop("_reset_to_original", False)

    if not _force_original and _autosave.exists():
        with open(_autosave, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
        st.session_state["_from_autosave"] = True
    else:
        with open(dataset_file, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
        st.session_state["_from_autosave"] = False

    st.session_state["_raw"] = raw
    st.session_state["_loaded_dataset"] = dataset
    st.session_state["_last_saved"] = None

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


def render_file(path: Path) -> None:
    """Render a supported file inline."""
    ext = path.suffix.lower()
    content = path.read_bytes()

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


def save_autosave() -> None:
    """Sync widgets → _raw, write autosave file, update last-saved timestamp."""
    _sync_widgets_to_raw()
    data = copy.deepcopy(st.session_state["_raw"])
    data["last_updated"] = datetime.now(_OSLO).isoformat()
    path = autosave_path(st.session_state["_loaded_dataset"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    st.session_state["_last_saved"] = datetime.now(_OSLO).strftime("%H:%M:%S")
    st.session_state["_from_autosave"] = True


def reset_to_original() -> None:
    """Delete autosave and force reload from original JSON on next rerun."""
    path = autosave_path(st.session_state["_loaded_dataset"])
    if path.exists():
        path.unlink()
    st.session_state["_reset_to_original"] = True
    del st.session_state["_loaded_dataset"]


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_dataset, tab_files = st.tabs(["📋 Dataset", "📁 Files"])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Dataset editor
# ════════════════════════════════════════════════════════════════════════════

with tab_dataset:

    # ── Autosave on every rerun ───────────────────────────────────────────────
    save_autosave()

    # ── Status bar ───────────────────────────────────────────────────────────
    if st.session_state.get("_from_autosave"):
        last = st.session_state.get("_last_saved")
        msg = f"💾 Autosaved at {last}" if last else "💾 Loaded from autosave"
        st.success(msg, icon=None)

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
    st.markdown("#### 💾 Download revised dataset")
    st.caption("All edits made in the fields above will be included in the downloaded file.")

    col_dl, col_reset = st.columns([0.75, 0.25])
    col_dl.download_button(
        label="⬇️ Download revised JSON",
        data=build_export(),
        file_name=f"dataset_{dataset}_revised.json",
        mime="application/json",
        type="primary",
        use_container_width=True,
    )
    col_reset.button(
        "↩️ Reset to original",
        on_click=reset_to_original,
        type="secondary",
        use_container_width=True,
        help="Discard all changes and reload the original dataset file",
    )


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — File browser
# ════════════════════════════════════════════════════════════════════════════

with tab_files:

    if not data_dir.exists():
        st.warning(f"⚠️ No `01_data` folder found for dataset **{dataset}**.")
        st.stop()

    all_files = sorted(
        f for f in data_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    if not all_files:
        st.info("📭 No supported files found in this dataset's data folder.")
        st.stop()

    st.markdown(
        f"#### 📁 Files &nbsp; <span style='color:grey;font-size:0.85em;font-weight:normal'>({len(all_files)} supported files)</span>",
        unsafe_allow_html=True,
    )
    st.caption("Select a file on the left to preview its contents.")
    st.write("")

    col_list, col_preview = st.columns([0.28, 0.72])

    with col_list:
        file_labels = [
            f"{FILE_ICONS.get(f.suffix.lower(), '📎')} {f.name}"
            for f in all_files
        ]
        with st.container(height=600, border=True):
            selected_label = st.radio(
                "Files",
                file_labels,
                label_visibility="collapsed",
            )

    selected_file = all_files[file_labels.index(selected_label)]

    with col_preview:
        st.markdown(f"**{FILE_ICONS.get(selected_file.suffix.lower(), '📎')} {selected_file.name}**")
        size_kb = selected_file.stat().st_size / 1024
        st.caption(f"{selected_file.suffix.upper().lstrip('.')} · {size_kb:.1f} KB")
        st.divider()
        try:
            render_file(selected_file)
        except Exception as e:
            st.error(f"❌ Could not render file: {e}")
            logger.error(f"Error rendering {selected_file}: {e}", exc_info=True)
