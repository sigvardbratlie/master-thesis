import logging
from utils import setup_logging, AppConfig
from dotenv import load_dotenv
import argparse
from evals import Dataset
from evals.collect_module import CollectAgentResult
import asyncio



async def single_run(data, llm_model : str, agent_type : str , config : AppConfig, clean_rate : int,
                     #embed_to_vectorstore, save_to_storage, , significance, 
                     ):
        car_custom = CollectAgentResult(data, llm_model=llm_model, agent_type=agent_type,
                                        config = config, 
                                        #significance = significance, 
                                        clean_rate = clean_rate)
        collected_results = await car_custom.run_agent()
                                                       
        ds = Dataset(data.dataset_name)
        ds.update_token_counts(collected_results)
        

async def main():
    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("-d","--dataset", type=str, choices=["test", "THRD-2021-163881","TOSL-2024-125319"], help="Dataset name to evaluate")
    parser.add_argument("-m","--model", type=str, choices=["google_gemini-2.5-flash", "google_gemini-2.5-pro", 
                                                           "openai_gpt-5.3-chat-latest", "openai_gpt-5.4",
                                                             "anthropic_claude-haiku-4-5", "anthropic_claude-sonnet-4-6",
                                                             "qwen_Qwen/Qwen3-Next-80B-A3B-Instruct", "qwen_Qwen/Qwen3.5-397B-A17B",
                                                             "zai_zai-org/GLM-5", 
                                                           ],
                        help="LLM model to use for evaluation")
    parser.add_argument("-a", "--agent-type", nargs="+", type=str, choices=["custom", "baseline", "baseline_rag"], default=["custom", "baseline", "baseline_rag"],help="Agent type to run (custom, baseline, or baseline_rag)")
    parser.add_argument("-n","--n-runs", type=int, default=1, help="Number of runs to execute for each agent")
    #parser.add_argument("--skip-embedding", action="store_true", help="Skip embedding step for custom agent")
    #parser.add_argument("--skip-storage", action="store_true", help="Skip saving results to storage for custom agent")
    #parser.add_argument("-s", "--significance", nargs="+", type=str, choices=["high", "medium", "low"], help="Significance levels to include for agent runs (overrides config.toml settings)")
    parser.add_argument("--clean-rate", type = int, help="The rate (of sessions) in which to clean the factsheet. From -1 for last msg, 1 > for all other rates")
    args = parser.parse_args()
    dataset_name = args.dataset
    llm_model = args.model
    agent_types = args.agent_type
    n_runs = args.n_runs
    # embed_to_vectorstore = not args.skip_embedding
    # save_to_storage = not args.skip_storage
    # significance = args.significance
    clean_rate = args.clean_rate

    config = AppConfig.from_toml(f"config_custom.toml")
    config_baseline = AppConfig.from_toml(f"config_baseline.toml")
    config_baseline_rag = AppConfig.from_toml(f"config_baseline_rag.toml")
    setup_logging(config)
    noisy_packages = ["httpx", "httpcore", "hpack", "urllib3", "anthropic", "openai", "asyncio", "langsmith"]
    [logging.getLogger(_pkg).setLevel(logging.WARNING) for _pkg in noisy_packages]

    logger = logging.getLogger(__name__)
    load_dotenv()

    logger.info("\n\n━" * 64)
    logger.info(f"🚀  COLLECT  |  dataset: {dataset_name}  |  model: {llm_model}  |  n_runs: {n_runs} | Significance : {config.agent.significance} | clean_rate | {clean_rate}")
    logger.info("━" * 64)

    ds_custom = Dataset(dataset_name)
    ds_baseline = Dataset(dataset_name)
    ds_baseline_rag = Dataset(dataset_name)

    data_custom = ds_custom.load_dataset() if "custom" in agent_types else None
    data_baseline = ds_baseline.load_dataset() if "baseline" in agent_types else None
    data_baseline_rag = ds_baseline_rag.load_dataset() if "baseline_rag" in agent_types else None

    if "custom" in agent_types and (not data_custom or not data_custom.sessions):
        logger.error("Custom dataset is empty or missing 'sessions' key.")
        exit()
    if "baseline" in agent_types and (not data_baseline or not data_baseline.sessions):
        logger.error("Baseline dataset is empty or missing 'sessions' key.")
        exit()
    if "baseline_rag" in agent_types and (not data_baseline_rag or not data_baseline_rag.sessions):
        logger.error("Baseline RAG dataset is empty or missing 'sessions' key.")
        exit()

    ds_custom.assign_session_attachments() if "custom" in agent_types else None
    ds_baseline.assign_session_attachments_baseline() if "baseline" in agent_types else None
    ds_baseline_rag.assign_session_attachments() if "baseline_rag" in agent_types else None

    if "custom" in agent_types:
        # ====== RUN CUSTOM AGENT ======
        logger.info("━" * 64)
        logger.info(f"🤖  CUSTOM AGENT  |  {llm_model}  |  dataset: {dataset_name}")
        logger.info("━" * 64)

        for i in range(n_runs):
            logger.info(f"━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}  |  CUSTOM AGENT  |  {llm_model}  |  dataset: {dataset_name}")
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
        logger.info("━" * 64)
        logger.info(f"📋🔍  BASELINE  |  {llm_model}  |  dataset: {dataset_name}")
        logger.info("━" * 64)
        for i in range(n_runs):
            logger.info("━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}  |     BASELINE   |  {llm_model}  |  dataset: {dataset_name}")
            logger.info("━" * 64)
            await single_run(data=data_baseline.model_copy(deep=True),
                             llm_model=llm_model,
                             agent_type="baseline",
                             #embed_to_vectorstore=False,
                             #save_to_storage=False,
                             #significance=significance,

                             config=config_baseline,
                             clean_rate=clean_rate)

        logger.info("━" * 64)
        logger.info(f"🎉  All done — results saved for dataset: {dataset_name} - Baseline")
        logger.info("━" * 64)
    
    if "baseline_rag" in agent_types:
        # ====== RUN BASELINE + BASELINE RAG IN PARALLEL ======
        logger.info("━" * 64)
        logger.info(f"📋🔍  BASELINE + RAG |  {llm_model}  |  dataset: {dataset_name}")
        logger.info("━" * 64)
        for i in range(n_runs):
            logger.info("━" * 64)
            logger.info(f"🔁  RUN {i+1}/{n_runs}  |  BASELINE RAG |  {llm_model}  |  dataset: {dataset_name}")
            logger.info("━" * 64)
            await single_run(data=data_baseline_rag.model_copy(deep=True),
                             llm_model=llm_model,
                             agent_type="baseline_rag",
                             #embed_to_vectorstore=True,
                             #save_to_storage=False,
                             #significance=significance,
                             config=config_baseline_rag,
                             clean_rate=clean_rate)

        logger.info("━" * 64)
        logger.info(f"🎉  All done — results saved for dataset: {dataset_name} - Baseline + RAG")
        logger.info("━" * 64)

if __name__ == "__main__":
    asyncio.run(main())

#python collect.py -d test -m anthropic_claude-sonnet-4-6