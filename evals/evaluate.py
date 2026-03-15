import logging
from utils import AppConfig, setup_logging
import argparse
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from evals import Dataset, Evaluater
load_dotenv()

os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "600")

config = AppConfig.from_toml("config.toml")
setup_logging(config)

noisy_packages = ["httpx", "httpcore", "hpack", "urllib3", "anthropic", "openai", "asyncio", "langsmith"]
[logging.getLogger(_pkg).setLevel(logging.WARNING) for _pkg in noisy_packages]

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("-d","--dataset", type=str, choices=["test", "THRD-2021-163881", "TOSL-2024-125319"], help="Dataset name to evaluate")
    parser.add_argument("-m","--model", type=str, choices = ["gemini-2.5-flash", "gpt-4.1",], default = "gemini-2.5-flash", help="LLM model to evaluate (optional, defaults to all models in dataset)")
    parser.add_argument("-i","--id" , type = str, help = "eval_runtime_id")
    parser.add_argument("--threshold", type=float, default=0.5, help="Threshold for evaluation metrics (default: 0.5)")
    args = parser.parse_args()
    dataset_name = args.dataset
    model = args.model
    throttle = config.async_tasks.throttle_value
    concurrent = config.async_tasks.max_concurrent_requests
    threshold = args.threshold
    eval_runtime_id = args.id

    logger.info("━" * 64)
    logger.info(f"🧪  EVALUATE  |  dataset: {dataset_name}")
    logger.info("━" * 64)

    ds = Dataset(dataset_name)
    collected_results = ds.load_results()
    evaluated_results = ds.load_evaluation_results()
    eval_results = []
    for r in evaluated_results.keys():
        eval_results.append(r.split("/")[-1].replace("llm-as-judge_", ""))


    count = 0
    for result_file, data in collected_results.items():
        if eval_runtime_id and eval_runtime_id not in result_file:
            logger.info(f'Skipping {result_file} as only ID {eval_runtime_id} is set to run')
            continue
        if not data.sessions:
            logger.warning(f"⚠️  No sessions in {result_file} — skipping")
            continue
        if result_file.split("/")[-1] in eval_results:
            logger.info(f"✅  Already evaluated {result_file} — skipping")
            continue
        
        if count > 5:
            logger.info("⚠️  Reached evaluation limit of 5 — stopping")
            break

        logger.info("┄" * 64)
        logger.info(f"📂  {data.dataset_name}  |  {data.llm_model}  |  {data.agent_type}  |  run: {data.eval_run_id}")
        logger.info("┄" * 64)

        evaluater = Evaluater(model=model, throttle_value=throttle, max_concurrent=concurrent, threshold=threshold)
        results = evaluater.run_evaluation(data=data)
        ds.save_evaluation_results(results, data)
        logger.info(f"✅  Evaluation saved for {data.agent_type} — {data.llm_model}")

        count += 1
        logger.info(f"📊  Evaluated {count}/{len(collected_results)} results")

    logger.info("━" * 64)
    logger.info(f"🎉  All evaluations done — dataset: {dataset_name}")
    logger.info("━" * 64)
