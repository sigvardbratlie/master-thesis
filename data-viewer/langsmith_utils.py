import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from gcs import _OSLO, write_blob

logger = logging.getLogger(__name__)


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
