import email
import math
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st
from docx import Document

from gcs import (
    _DATE_PATTERN,
    SUPPORTED_EXTENSIONS,
    FILE_ICONS,
    read_blob_bytes,
    list_data_blobs,
)


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


def render_file(filename: str, content: bytes) -> None:
    """Render a supported file inline."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        st.pdf(BytesIO(content))

    elif ext == ".txt":
        with st.container(height=600, border=True):
            st.text(content.decode("utf-8", errors="ignore"))

    elif ext == ".md":
        with st.container(height=600, border=True):
            st.markdown(content.decode("utf-8", errors="ignore"))

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


@st.cache_data(ttl=300)
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


def render_attachment_popover(path: str, key_prefix: str = "") -> None:
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
            if st.button("📂 Load preview", key=f"load_{key_prefix}_{bytes_key}"):
                try:
                    st.session_state[bytes_key] = read_blob_bytes(path)
                except Exception as e:
                    st.error(f"Could not load: {e}")
        if st.session_state.get(bytes_key):
            render_file(fname, st.session_state[bytes_key])


def render_attachments_section(attachments: list[str], key_prefix: str = "") -> None:
    """Render an attachments expander with a lazy popover preview per file."""
    if not attachments:
        return
    with st.expander(f"📎 Attachments ({len(attachments)})", expanded=False):
        for path in attachments:
            render_attachment_popover(path, key_prefix=key_prefix)
