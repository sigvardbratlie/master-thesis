import logging
from utils import setup_logging, AppConfig
from dotenv import load_dotenv
import argparse
from evals import Dataset
from evals.collect_module import CollectAgentResult
import asyncio



async def single_run(data, 
                     llm_model : str, 
                     agent_type : str , 
                     config : AppConfig, 
                     eval_run_id : str = None,
                     ):
        car_custom = CollectAgentResult(data, 
                                        llm_model=llm_model, 
                                        agent_type=agent_type,
                                        config = config
                                        )
        collected_results = await car_custom.run_agent(eval_run_id=eval_run_id)
                                                       
        ds = Dataset(data.dataset_name)
        ds.update_token_counts(collected_results)

model_choices = ["google_gemini-2.5-flash", "google_gemini-2.5-pro", 
                                "openai_gpt-5.3-chat-latest", "openai_gpt-5.4",
                                "anthropic_claude-haiku-4-5", "anthropic_claude-sonnet-4-6",
                                "qwen_Qwen/Qwen3-Next-80B-A3B-Instruct", "qwen_Qwen/Qwen3.5-397B-A17B",
                                "zai_zai-org/GLM-5", 
                                ]

async def main():
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("-d","--dataset", 
                        type=str, 
                        choices=["test", 
                                 "THRD-2021-163881",
                                 "TOSL-2024-125319",
                                 "TOSL-2024-125319-MIN"
                                 ], 
                        help="Dataset name to evaluate")
    parser.add_argument("-m","--model", 
                        type=str, 
                        choices=model_choices,
                        default="google_gemini-2.5-flash",
                        help="LLM model to use for evaluation")

    parser.add_argument("-a", "--agent-type", 
                        nargs="+", 
                        type=str, 
                        choices=["custom", 
                                 #"baseline", 
                                 "baseline_rag"], 
                        default=["custom",
                                 "baseline_rag"],
                        help="Agent type to run (custom, baseline, or baseline_rag)")
    parser.add_argument("-n","--n-runs", type=int, default=1, help="Number of runs to execute for each agent")
    parser.add_argument("--clean-rate", type = int, help="The rate (of sessions) in which to clean the factsheet. From -1 for last msg, 1 > for all other rates")
    parser.add_argument("--eval-run-id", type=str, help="Evaluation run ID")
    args = parser.parse_args()
    dataset_name = args.dataset
    llm_model = args.model
    eval_run_id = args.eval_run_id

    agent_types = args.agent_type
    n_runs = args.n_runs
    clean_rate = args.clean_rate
    
    config = AppConfig.from_toml(f"config.toml") 
    setup_logging(config)
    noisy_packages = ["httpx", "httpcore", "hpack", "urllib3", 
                      "anthropic", "openai", "asyncio", "langsmith", "ocrmypdf", "PIL", 
                      "img2pdf", "botocore","textractor", "google_genai"]
    [logging.getLogger(_pkg).setLevel(logging.WARNING) for _pkg in noisy_packages]

    logger = logging.getLogger(__name__)
    load_dotenv()
    
    logger.info("\n\n")
    logger.info("━" * 64)
    logger.info(f"🚀  COLLECT  |  dataset: {dataset_name}  |  model: {llm_model}  |  n_runs: {n_runs}")
    logger.info("━" * 64)

    if "custom" in agent_types:
        ds_custom = Dataset(dataset_name)
        data_custom = ds_custom.load_dataset()
        data_custom.dataset_name = dataset_name
        if not data_custom or not data_custom.sessions:
            logger.error("Custom dataset is empty or missing 'sessions' key.")
            exit()
        ds_custom.assign_session_attachments()
        # ====== RUN CUSTOM AGENT ======
        logger.info("━" * 64)
        logger.info(f"🤖  CUSTOM AGENT  |  {llm_model}  |  dataset: {dataset_name} | significance {config.agent.significance} |  clean_rate | {clean_rate}")
        logger.info("━" * 64)

        for i in range(n_runs):
            logger.info(f"━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}")
            logger.info("━" * 64)
            await single_run(data=data_custom.model_copy(deep=True),
                            llm_model=llm_model,
                            agent_type="custom",
                            #embed_to_vectorstore=embed_to_vectorstore,
                           # save_to_storage=save_to_storage,
                           #significance = significance,
                            config = config,
                            clean_rate = clean_rate)
        logger.info("━" * 64)
        logger.info(f"🎉  All done — results saved for dataset: {dataset_name} - Custom")
        logger.info("━" * 64)
            
    if "baseline" in agent_types:
        config_baseline = AppConfig.from_toml(f"config_baseline.toml")
        ds_baseline = Dataset(dataset_name)
        data_baseline = ds_baseline.load_dataset()
        data_baseline.dataset_name = dataset_name
        if not data_baseline or not data_baseline.sessions:
            logger.error("Baseline dataset is empty or missing 'sessions' key.")
            exit()
        ds_baseline.assign_session_attachments_baseline()
        logger.info("━" * 64)
        logger.info(f"📋🔍  BASELINE  |  {llm_model}  |  dataset: {dataset_name} | significance : {config_baseline.agent.significance}")
        logger.info("━" * 64)
        for i in range(n_runs):
            logger.info("━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}")
            logger.info("━" * 64)
            await single_run(data=data_baseline.model_copy(deep=True),
                             llm_model=llm_model,
                             agent_type="baseline",
                             config=config_baseline,
                             clean_rate=clean_rate,)

        logger.info("━" * 64)
        logger.info(f"🎉  All done — results saved for dataset: {dataset_name} - Baseline")
        logger.info("━" * 64)
    
    if "baseline_rag" in agent_types:
        config_baseline_rag = AppConfig.from_toml(f"config_baseline_rag.toml")
        ds_baseline_rag = Dataset(dataset_name)
        data_baseline_rag = ds_baseline_rag.load_dataset()
        data_baseline_rag.dataset_name = dataset_name
        if not data_baseline_rag or not data_baseline_rag.sessions:
            logger.error("Baseline RAG dataset is empty or missing 'sessions' key.")
            exit()
        ds_baseline_rag.assign_session_attachments()
        # ====== RUN BASELINE + BASELINE RAG IN PARALLEL ======
        logger.info("━" * 64)
        logger.info(f"📋🔍  BASELINE + RAG |  {llm_model}  |  dataset: {dataset_name} | significance : {config_baseline_rag.agent.significance}")
        logger.info("━" * 64)
        for i in range(n_runs):
            logger.info("━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}")
            logger.info("━" * 64)
            await single_run(data=data_baseline_rag.model_copy(deep=True),
                             llm_model=llm_model,
                             agent_type="baseline_rag",
                             config=config_baseline_rag,
                             clean_rate=clean_rate,)

        logger.info("━" * 64)
        logger.info(f"🎉  All done — results saved for dataset: {dataset_name} - Baseline + RAG")
        logger.info("━" * 64)

if __name__ == "__main__":
    asyncio.run(main())
