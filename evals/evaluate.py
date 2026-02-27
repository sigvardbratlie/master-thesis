import argparse
import logging
from datetime import datetime
from evals import Dataset, Evaluater
from dotenv import load_dotenv
import os
load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("--dataset", type=str, choices=["test", "THRD-2021-163881", "TOSL-2024-103311", "TOSL-2024-125319"], help="Dataset name to evaluate")
    parser.add_argument("--model", type=str, help="LLM model to evaluate (optional, defaults to all models in dataset)")
    args = parser.parse_args()
    dataset_name = args.dataset
    model = args.model

    logger.info("━" * 64)
    logger.info(f"🧪  EVALUATE  |  dataset: {dataset_name}")
    logger.info("━" * 64)

    ds = Dataset(dataset_name)
    collected_results = ds.load_results()

    for result_file, data in collected_results.items():
        if not data.sessions:
            logger.warning(f"⚠️  No sessions in {result_file} — skipping")
            continue

        logger.info("┄" * 64)
        logger.info(f"📂  {data.dataset_name}  |  {data.llm_model}  |  {data.agent_type}  |  run: {data.eval_run_id}")
        logger.info("┄" * 64)

        evaluater = Evaluater(model=model)
        results = evaluater.run_evaluation(data=data)
        ds.save_evaluation_results(results, data)
        logger.info(f"✅  Evaluation saved for {data.agent_type} — {data.llm_model}")

    logger.info("━" * 64)
    logger.info(f"🎉  All evaluations done — dataset: {dataset_name}")
    logger.info("━" * 64)
