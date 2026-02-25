import uuid
import logging
from base64 import b64encode
from dotenv import load_dotenv
import argparse
from evals import Dataset, CollectAgentResult
from langsmith import Client as LangSmithClient
import os
import asyncio
logging.basicConfig(level=logging.INFO)
logging.getLogger(__name__).setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
load_dotenv()


def get_token_counts(eval_run_id: str) -> dict:
    """Query LangSmith for total token usage across an eval run."""
    client = LangSmithClient()
    project_name = os.getenv("LANGCHAIN_PROJECT", "default")
    runs = list(client.list_runs(
        project_name=project_name,
        filter=f'has(tags, "{eval_run_id}")',
        run_type="llm",
    ))
    return {
        "eval_run_id": eval_run_id,
        "input_tokens": sum(r.prompt_tokens or 0 for r in runs),
        "output_tokens": sum(r.completion_tokens or 0 for r in runs),
        "total_tokens": sum(r.total_tokens or 0 for r in runs),
        "llm_calls": len(runs),
    }

async def main():
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("--dataset", type=str, help="Dataset name to evaluate")
    parser.add_argument("--model", type=str, choices=["google_gemini-2.5-flash", "google_gemini-2.5-pro", "openai_gpt-5.2", "openai_gpt-4.0", "openai_gpt-5-mini"],
                        help="LLM model to use for evaluation")
    parser.add_argument("--skip-embedding", action="store_true", help="Skip embedding step for custom agent")
    parser.add_argument("--skip-storage", action="store_true", help="Skip saving results to storage for custom agent")
    args = parser.parse_args()
    dataset_name = args.dataset
    llm_model = args.model
    embed_to_vectorstore = not args.skip_embedding
    save_to_storage = not args.skip_storage

    logger.info("━" * 64)
    logger.info(f"🚀  COLLECT  |  dataset: {dataset_name}  |  model: {llm_model}")
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
    car_custom = CollectAgentResult(data_custom, llm_model=llm_model, agent_type="custom")
    collected_custom_results = await car_custom.run_agent(embed_to_vectorstore=embed_to_vectorstore, save_to_storage=save_to_storage)
    token_counts = get_token_counts(collected_custom_results.eval_run_id)
    logger.info(f"📊 Tokens — in: {token_counts['input_tokens']}  out: {token_counts['output_tokens']}  total: {token_counts['total_tokens']}  calls: {token_counts['llm_calls']}")
    collected_custom_results.token_counts = token_counts
    ds_custom.save_results(collected_custom_results)
    logger.info("✅ Custom agent results saved")

    # ====== RUN BASELINE AGENT ======
    logger.info("━" * 64)
    logger.info(f"📋  BASELINE AGENT  |  {llm_model}  |  dataset: {dataset_name}")
    logger.info("━" * 64)
    car_baseline = CollectAgentResult(data_baseline, llm_model=llm_model, agent_type="baseline")
    collected_baseline_results = await car_baseline.run_agent(embed_to_vectorstore=False, save_to_storage=False)
    token_counts_baseline = get_token_counts(collected_baseline_results.eval_run_id)
    logger.info(f"📊 Tokens — in: {token_counts_baseline['input_tokens']}  out: {token_counts_baseline['output_tokens']}  total: {token_counts_baseline['total_tokens']}  calls: {token_counts_baseline['llm_calls']}")
    collected_baseline_results.token_counts = token_counts_baseline
    ds_baseline.save_results(collected_baseline_results)
    logger.info("✅ Baseline agent results saved")

    # ====== RUN BASELINE RAG AGENT ======
    logger.info("━" * 64)
    logger.info(f"🔍  BASELINE RAG AGENT  |  {llm_model}  |  dataset: {dataset_name}")
    logger.info("━" * 64)
    car_baseline_rag = CollectAgentResult(data_baseline_rag, llm_model=llm_model, agent_type="baseline_rag")
    collected_baseline_rag_results = await car_baseline_rag.run_agent(embed_to_vectorstore=True, save_to_storage=False)
    token_counts_baseline_rag = get_token_counts(collected_baseline_rag_results.eval_run_id)
    logger.info(f"📊 Tokens — in: {token_counts_baseline_rag['input_tokens']}  out: {token_counts_baseline_rag['output_tokens']}  total: {token_counts_baseline_rag['total_tokens']}  calls: {token_counts_baseline_rag['llm_calls']}")
    collected_baseline_rag_results.token_counts = token_counts_baseline_rag
    ds_baseline_rag.save_results(collected_baseline_rag_results)
    logger.info("✅ Baseline RAG agent results saved")

    logger.info("━" * 64)
    logger.info(f"🎉  All done — results saved for dataset: {dataset_name}")
    logger.info("━" * 64)

if __name__ == "__main__":
    asyncio.run(main())
