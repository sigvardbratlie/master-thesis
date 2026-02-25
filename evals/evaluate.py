import argparse
import logging
from datetime import datetime
from evals import Dataset,Evaluater
from dotenv import load_dotenv
import os   
load_dotenv()  # Load environment variables from .env file

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("--dataset", type=str, help="Dataset name to evaluate")
    args = parser.parse_args()
    dataset_name = args.dataset

    ds = Dataset(dataset_name)
    collected_results = ds.load_results()
    for result_file, data in collected_results.items():
        if not data.get("sessions"):
            logger.warning(f"No sessions found in result file {result_file}. Skipping evaluation for this file.")
            continue
        logger.info(f'=========== RUNNING EVALUATION FOR {data.get("dataset_name")} - {data.get("llm_model")} - {data.get("agent_type", "unknown")} - {data.get("eval_run_id")} ===========')
        evaluater = Evaluater()
        results = evaluater.run_evaluation(data = data)
        evaluater.save_evaluation_results(results, data)