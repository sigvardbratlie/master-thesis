
import logging

_log_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_log_fmt)
logging.root.setLevel(logging.DEBUG)
logging.root.addHandler(_console_handler)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("langsmith").setLevel(logging.WARNING)

import argparse
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "600")

from evals import Dataset, Evaluater



logger = logging.getLogger(__name__)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("-d","--dataset", type=str, choices=["test", "THRD-2021-163881", "TOSL-2024-103311", "TOSL-2024-125319"], help="Dataset name to evaluate")
    parser.add_argument("-m","--model", type=str, help="LLM model to evaluate (optional, defaults to all models in dataset)")
    parser.add_argument("-i","--id" , type = str, help = "eval_runtime_id")
    parser.add_argument("-t","--throttle", type=int, default=1, help="Throttle value for evaluation (default: 5)")
    parser.add_argument("-c","--concurrent", type=int, default=2, help="Max concurrent evaluations (default: 1)")
    parser.add_argument("--threshold", type=float, default=0.5, help="Threshold for evaluation metrics (default: 0.5)")
    args = parser.parse_args()
    dataset_name = args.dataset
    model = args.model
    throttle = args.throttle
    concurrent = args.concurrent
    threshold = args.threshold
    eval_runtime_id = args.id

    _run_id = uuid.uuid4().hex[:8]
    _log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = os.path.join(_log_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_evaluate_{_run_id}.log")
    _file_handler = logging.FileHandler(_log_file)
    _file_handler.setLevel(logging.DEBUG)
    _file_handler.setFormatter(_log_fmt)
    logging.root.addHandler(_file_handler)
    logger.info(f"Logging to {_log_file}")

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
            logger.info("⚠️  Reached evaluation limit of 3 — stopping")
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
