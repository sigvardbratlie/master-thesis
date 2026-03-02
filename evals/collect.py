import logging
from dotenv import load_dotenv
import argparse
from evals import Dataset
from evals.collect_module import CollectAgentResult
from langsmith import Client as LangSmithClient
import os
import asyncio
logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__).setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("agent.agent").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
load_dotenv()


def get_token_counts(eval_run_id: str) -> dict:
    """Query LangSmith for total and per-query token usage across an eval run."""
    client = LangSmithClient()
    project_name = os.getenv("LANGCHAIN_PROJECT", "default")
    runs = list(client.list_runs(
        project_name=project_name,
        filter=f'has(tags, "{eval_run_id}")',
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
        "eval_run_id": eval_run_id,
        "input_tokens": sum(r.prompt_tokens or 0 for r in runs),
        "output_tokens": sum(r.completion_tokens or 0 for r in runs),
        "total_tokens": sum(r.total_tokens or 0 for r in runs),
        "llm_calls": len(runs),
        "per_query": per_query,
    }

async def single_run(data, llm_model, agent_type, embed_to_vectorstore, save_to_storage):
        car_custom = CollectAgentResult(data, llm_model=llm_model, agent_type=agent_type)
        collected_custom_results = await car_custom.run_agent(embed_to_vectorstore=embed_to_vectorstore, save_to_storage=save_to_storage)
        token_counts = get_token_counts(collected_custom_results.eval_run_id)
        logger.info(f"📊 Tokens — in: {token_counts['input_tokens']}  out: {token_counts['output_tokens']}  total: {token_counts['total_tokens']}  calls: {token_counts['llm_calls']}")
        for session in collected_custom_results.sessions:
            for conv in session.conversation:
                qid = conv.query_id or "unknown"
                entry = token_counts["per_query"].setdefault(
                    qid, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "llm_calls": 0}
                )
                entry["duration"] = conv.turn_duration or 0.0
        collected_custom_results.token_counts = token_counts
        ds = Dataset(data.dataset_name)
        ds.save_results(collected_custom_results)
        logger.info(f"✅ {agent_type} agent results saved")

async def main():
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("-d","--dataset", type=str, choices=["test", "THRD-2021-163881", "TOSL-2024-103311", "TOSL-2024-125319"], help="Dataset name to evaluate")
    parser.add_argument("-m","--model", type=str, choices=["google_gemini-2.5-flash", "google_gemini-2.5-pro", "openai_gpt-5.2", "openai_gpt-4.0", "openai_gpt-5-mini"],
                        help="LLM model to use for evaluation")
    parser.add_argument("-n","--n-runs", type=int, default=1, help="Number of runs to execute for each agent")
    parser.add_argument("--skip-embedding", action="store_true", help="Skip embedding step for custom agent")
    parser.add_argument("--skip-storage", action="store_true", help="Skip saving results to storage for custom agent")
    args = parser.parse_args()
    dataset_name = args.dataset
    llm_model = args.model
    n_runs = args.n_runs
    embed_to_vectorstore = not args.skip_embedding
    save_to_storage = not args.skip_storage

    logger.info("━" * 64)
    logger.info(f"🚀  COLLECT  |  dataset: {dataset_name}  |  model: {llm_model}  |  n_runs: {n_runs}")
    logger.info("━" * 64)

    ds_custom = Dataset(dataset_name)
    ds_baseline = Dataset(dataset_name)
    ds_baseline_rag = Dataset(dataset_name)

    data_custom = ds_custom.load_dataset()
    data_baseline = ds_baseline.load_dataset()
    data_baseline_rag = ds_baseline_rag.load_dataset()

    if not data_custom or not data_custom.sessions:
        logger.error("Custom dataset is empty or missing 'sessions' key.")
        exit()
    if not data_baseline or not data_baseline.sessions:
        logger.error("Baseline dataset is empty or missing 'sessions' key.")
        exit()
    if not data_baseline_rag or not data_baseline_rag.sessions:
        logger.error("Baseline RAG dataset is empty or missing 'sessions' key.")
        exit()

    ds_custom.assign_session_attachments()
    ds_baseline.assign_session_attachments_baseline()
    ds_baseline_rag.assign_session_attachments()
    total_attachments = sum(len(s.attachments) for s in data_custom.sessions)
    logger.info(f"✅ {len(data_custom.sessions)} sessions ready — {total_attachments} attachments assigned in total")

    # ====== RUN CUSTOM AGENT ======
    logger.info("━" * 64)
    logger.info(f"🤖  CUSTOM AGENT  |  {llm_model}  |  dataset: {dataset_name}")
    logger.info("━" * 64)

    for i in range(n_runs):
        logger.info(f"━" * 64)
        logger.info(f"🔁  RUN {i+1}/{n_runs}  |  CUSTOM AGENT  |  {llm_model}  |  dataset: {dataset_name}")
        logger.info("━" * 64)
        await single_run(data = data_custom, 
                         llm_model=llm_model, 
                         agent_type="custom", 
                         embed_to_vectorstore=embed_to_vectorstore, 
                         save_to_storage=save_to_storage)

    # ====== RUN BASELINE + BASELINE RAG IN PARALLEL ======
    logger.info("━" * 64)
    logger.info(f"📋🔍  BASELINE + BASELINE RAG (parallel)  |  {llm_model}  |  dataset: {dataset_name}")
    logger.info("━" * 64)
    for i in range(n_runs):
        logger.info("━" * 64)
        logger.info(f"🔁  RUN {i+1}/{n_runs}  |  BASELINE + BASELINE RAG (parallel)  |  {llm_model}  |  dataset: {dataset_name}")
        logger.info("━" * 64)
        await asyncio.gather(
            single_run(data=data_baseline,     llm_model=llm_model, agent_type="baseline",     embed_to_vectorstore=False, save_to_storage=True),
            single_run(data=data_baseline_rag, llm_model=llm_model, agent_type="baseline_rag", embed_to_vectorstore=False, save_to_storage=True),
        )

    logger.info("━" * 64)
    logger.info(f"🎉  All done — results saved for dataset: {dataset_name}")
    logger.info("━" * 64)

if __name__ == "__main__":
    asyncio.run(main())
