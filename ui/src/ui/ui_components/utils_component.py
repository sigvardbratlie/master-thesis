import streamlit as st
import logging
from ui.models import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




def _render_project_stream_progress(
    stream_iter,
    initial_label: str = "🔄 Processing...",
    complete_label: str = "✅ Done!",
) -> bool:
    """
    Shared progress renderer for init-project, update-project, and
    update-project-from-session streams. Accepts a pre-created iterator so
    callers control which endpoint is used.

    Returns True on success, False on error.
    """
    PHASE_CONFIG = {
        "initialization": ("🚀", "Setting up"),
        "init_input": ("📋", "Analyzing case details"),
        "storage": ("💾", "Saving documents"),
        "parse-documents": ("📑", "Parsing documents"),
        "parse_doc": ("📄", "Document parsed"),
        "analyze_docs": ("📄", "Document analysis"),
        "analyze_doc": ("📝", "Document analyzed"),
        "analyze_email": ("✉️", "Email analyzed"),
        "final_analysis": ("🔬", "Running final analysis"),
        "factual_facts": ("⚖️", "Factual analysis"),
        "governing_law": ("📜", "Legal framework analysis"),
    }

    with st.status(initial_label, expanded=True) as status:
        progress_bar = st.progress(0, text="Starting...")
        total = 0
        completed = 0

        try:
            for event in stream_iter:
                if event.get("error"):
                    status.update(label="❌ Error occurred", state="error")
                    st.error(event["error"])
                    return False

                phase_raw = event.get("phase", "")
                phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                event_status = event.get("status", "")
                data = event.get("data") or {}
                emoji, label = PHASE_CONFIG.get(phase, ("⏳", phase or "Processing"))

                if event_status == "starting":
                    n = data.get("total_operations", data.get("total", 0))
                    total += n

                    if phase == "parse_doc":
                        fname = data.get("filename", "")
                        status.update(label=f"{emoji} Parsing {fname}..." if fname else f"{emoji} {label}...")
                    elif phase == "storage":
                        fname = data.get("filename", "")
                        status.update(label=f"💾 Saving {fname} to vector store..." if fname else f"💾 {label}...")
                    else:
                        status.update(label=f"{emoji} {label}...")

                    if phase == "initialization":
                        n_att = data.get("attachments", 0)
                        if n_att:
                            st.caption(f"📎 {n_att} attachment(s) to process")
                    elif phase in ("analyze_docs", "analyze_doc"):
                        n_docs = data.get("total", 0)
                        if n_docs:
                            st.caption(f"📄 Analyzing {n_docs} document(s)...")

                elif event_status == "complete":
                    if phase == "analyze_docs":
                        continue

                    completed += 1
                    detail = ""

                    if phase == "init_input":
                        n = data.get("parties_found", 0)
                        detail = f" — {n} parties found" if n else ""
                    elif phase == "parse_doc":
                        fname = data.get("filename", "")
                        progress = data.get("progress", 0)
                        total_files = data.get("total", 0)
                        detail = f": **{fname}** ({progress}/{total_files})" if fname else ""
                    elif phase == "storage":
                        fname = data.get("filename", "")
                        storage_types = data.get("storage_type", [])
                        if fname:
                            detail = f": **{fname}**"
                        elif "file_storage" in storage_types:
                            detail = " — file storage"
                        elif "database" in storage_types:
                            detail = " — database"
                    elif phase == "analyze_doc":
                        fname = data.get("filename", "")
                        progress = data.get("progress", 0)
                        total_docs = data.get("total", 0)
                        detail = f": **{fname}** ({progress}/{total_docs})" if fname else f" ({progress}/{total_docs})"
                    elif phase == "analyze_email":
                        subject = data.get("subject", "")
                        progress = data.get("progress", 0)
                        total_docs = data.get("total", 0)
                        detail = f": **{subject}** ({progress}/{total_docs})" if subject else f" ({progress}/{total_docs})"
                    elif phase == "factual_facts":
                        d = data.get("disputed_count", 0)
                        u = data.get("undisputed_count", 0)
                        detail = f" — {d} disputed, {u} undisputed facts"
                    elif phase == "governing_law":
                        j = data.get("jurisdiction", "")
                        detail = f" — {j}" if j else ""

                    st.markdown(f"✅ {label}{detail}")

                    if phase == "storage":
                        fname = data.get("filename", "")
                        status.update(label=f"💾 Saving {fname}..." if fname else "💾 Saving documents...")
                    elif phase == "analyze_doc":
                        fname = data.get("filename", "")
                        status.update(label=f"{emoji} Analyzing {fname}..." if fname else f"{emoji} Analyzing documents...")
                    elif phase == "analyze_email":
                        subject = data.get("subject", "")
                        status.update(label=f"{emoji} Analyzing {subject}..." if subject else f"{emoji} Analyzing emails...")

                    if total > 0:
                        pct = min(completed / total, 1.0)
                        progress_bar.progress(pct, text=f"{emoji} {label}...")

            progress_bar.progress(1.0, text="Complete!")
            status.update(label=complete_label, state="complete")
            return True

        except Exception as e:
            status.update(label="❌ Error during processing", state="error")
            st.error(str(e))
            logger.error(f"Error in project stream progress: {e}", exc_info=True)
            return False

