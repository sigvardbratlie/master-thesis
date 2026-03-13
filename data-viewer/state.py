import copy
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from gcs import (
    _OSLO,
    write_blob,
    delete_blob,
    draft_blob_path,
    dataset_blob_path,
    version_blob_path,
)


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
    """Sync widgets → _raw, write draft blob to GCS only when content changed."""
    _sync_widgets_to_raw()
    content_hash = hash(json.dumps(st.session_state["_raw"], ensure_ascii=False, sort_keys=True))
    if content_hash == st.session_state.get("_draft_content_hash"):
        return
    st.session_state["_draft_content_hash"] = content_hash
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
