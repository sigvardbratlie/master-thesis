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
        "initialization":    ("🚀", "Setting up"),
        "collapse_emails":   ("📧", "Collapsing email threads"),
        "init_input":        ("📋", "Analyzing case details"),
        "load_project_data": ("📂", "Loading project data"),
        "storage":           ("💾", "Saving documents"),
        "parse_documents":   ("📑", "Parsing documents"),
        "parse_doc":         ("📄", "Document parsed"),
        "analyze_docs":      ("📄", "Document analysis"),
        "analyze_emails":    ("✉️", "Email analysis"),
        "save_project":      ("💾", "Saving project"),
        "update_project":    ("🔄", "Updating project"),
        "final_analysis":    ("🔬", "Running final analysis"),
        "factual_facts":     ("⚖️", "Factual analysis"),
        "governing_law":     ("📜", "Legal framework analysis"),
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
                is_combined = isinstance(phase_raw, list) and len(phase_raw) > 1
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
                    elif phase == "collapse_emails":
                        n_emails = data.get("total", 0)
                        if n_emails:
                            st.caption(f"📧 {n_emails} email(s) to collapse")
                    elif phase in ("analyze_docs", "analyze_emails"):
                        if not is_combined:
                            n_tasks = data.get("total", 0)
                            if n_tasks:
                                st.caption(f"📦 {n_tasks} batch(es) to analyze")
                    elif phase == "parse_documents":
                        n_docs = data.get("total", 0)
                        if n_docs:
                            st.caption(f"📄 {n_docs} document(s) to parse")

                elif event_status == "complete":
                    # Combined final event for analyze_docs + analyze_emails — summary only
                    if is_combined:
                        n_tasks = data.get("total", 0)
                        st.markdown(f"✅ Analysis complete — {n_tasks} batch(es) processed")
                        completed += 1
                        if total > 0:
                            progress_bar.progress(min(completed / total, 1.0), text=f"{emoji} {label}...")
                        continue

                    completed += 1
                    detail = ""

                    if phase == "init_input":
                        n = data.get("parties_found", 0)
                        detail = f" — {n} parties found" if n else ""
                    elif phase == "collapse_emails":
                        n_collapsed = data.get("n_collapsed", 0)
                        detail = f" — {n_collapsed} thread(s)" if n_collapsed else ""
                    elif phase == "parse_doc":
                        fname = data.get("filename", "")
                        progress = data.get("progress", 0)
                        total_files = data.get("total", 0)
                        detail = f": **{fname}** ({progress}/{total_files})" if fname else ""
                    elif phase == "parse_documents":
                        n_docs = data.get("total", 0)
                        detail = f" — {n_docs} document(s)" if n_docs else ""
                    elif phase == "storage":
                        fname = data.get("filename", "")
                        storage_types = data.get("storage_type", [])
                        table_name = data.get("table_name", "")
                        if fname:
                            detail = f": **{fname}**"
                        elif "file_storage" in storage_types:
                            detail = " — file storage"
                        elif "vector_store" in storage_types:
                            detail = " — vector store"
                        elif "database" in storage_types:
                            detail = f" — {table_name}" if table_name else " — database"
                    elif phase == "analyze_docs":
                        specs = data.get("specs", "")
                        progress = data.get("progress", 0)
                        total_tasks = data.get("total", 0)
                        detail = f": {specs} ({progress}/{total_tasks})" if specs else f" ({progress}/{total_tasks})"
                    elif phase == "analyze_emails":
                        specs = data.get("specs", "")
                        progress = data.get("progress", 0)
                        total_tasks = data.get("total", 0)
                        detail = f": {specs} ({progress}/{total_tasks})" if specs else f" ({progress}/{total_tasks})"
                    elif phase == "load_project_data":
                        detail = ""
                    elif phase in ("save_project", "update_project"):
                        detail = ""
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
                    elif phase == "analyze_docs":
                        specs = data.get("specs", "")
                        status.update(label=f"{emoji} Analyzing {specs}..." if specs else f"{emoji} Analyzing documents...")
                    elif phase == "analyze_emails":
                        specs = data.get("specs", "")
                        status.update(label=f"{emoji} Analyzing {specs}..." if specs else f"{emoji} Analyzing emails...")

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
