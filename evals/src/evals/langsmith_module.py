from langsmith import Client
from dotenv import load_dotenv
import logging
import json
import os
from pydantic import BaseModel
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

def get_session_token_counts(runtime_session_id: str) -> dict:
    """Query LangSmith for per-query token usage for a single session via thread_id."""
    client = Client()
    project_name = os.getenv("LANGCHAIN_PROJECT", "default")
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
        "runtime_session_id": runtime_session_id,
        "input_tokens": sum(r.prompt_tokens or 0 for r in runs),
        "output_tokens": sum(r.completion_tokens or 0 for r in runs),
        "total_tokens": sum(r.total_tokens or 0 for r in runs),
        "llm_calls": len(runs),
        "per_query": per_query,
    }


class ConversationEntry(BaseModel):
    input: str
    answer: str
    query_id: str
    order: int

class TestSession(BaseModel):
    session: int  # Changed from str to int
    date: str
    session_id: str
    session_name: str
    init_query: str
    conversation: list[ConversationEntry]

class LangSmithMetadata(BaseModel):
    session: int  # Changed from str to int
    date: str
    session_id: str
    session_name: str
    query_id: str
    order: int

class LangSmithData(BaseModel):
    input : str
    answer : str
    metadata : LangSmithMetadata

class LangSmithDatasetManager:
    def __init__(self,):
        self.client = Client()

    def load_or_create_dataset(self, dataset_name: str):
        if self.client.has_dataset(dataset_name=dataset_name):
            try:
                dataset = self.client.read_dataset(dataset_name=dataset_name)
                logger.info(f"Dataset '{dataset_name}' already exists. Loaded existing dataset.")
            except Exception as e:
                logger.error(f"Error loading dataset '{dataset_name}': {e}")
        else:
            try:
                dataset = self.client.create_dataset(dataset_name=dataset_name,
                                                description="Dataset for THRD-2021-163881")
                logger.info(f"Dataset '{dataset_name}' created.")
            except Exception as e:
                logger.error(f"Error creating dataset '{dataset_name}': {e}")

        return dataset
    
    def read_examples(self, dataset_name: str):
        try:
            examples = list(self.client.list_examples(dataset_name=dataset_name, as_of="latest"))
            logger.info(f"Loaded {len(examples)} examples from dataset '{dataset_name}'.")
            return [example.model_dump() for example in examples]
        except Exception as e:
            logger.error(f"Error loading examples from dataset '{dataset_name}': {e}")
            return []
        
    def delete_dataset(self, dataset_name: str):
        try:
            self.client.delete_dataset(dataset_name=dataset_name)
            logger.info(f"Dataset '{dataset_name}' deleted.")
        except Exception as e:
            logger.error(f"Error deleting dataset '{dataset_name}': {e}")
        
    def upload_examples(self, dataset_name: str, data: list):
        if not "input" in data[0] and not "answer" in data[0] and not "metadata" in data[0]:
            logger.error("Data must contain 'input', 'answer', and 'metadata' fields.")
            return
        inputs = [{"input": item["input"]} for item in data]
        outputs = [{"answer": item["answer"]} for item in data]
        metadata = [item["metadata"] for item in data]
        try:
            self.client.create_examples(dataset_name=dataset_name, 
                                        inputs = inputs,
                                        outputs = outputs,
                                        metadata = metadata,
                                        )
            logger.info(f"Uploaded {len(inputs)} examples to dataset '{dataset_name}'.")
        except Exception as e:
            logger.error(f"Error uploading examples to dataset '{dataset_name}': {e}", exc_info=True)

    
    #LANGSMITH->JSON
    def from_langsmith_to_json(self, data):
        [LangSmithData.model_validate(record) for record in data]
        new_data = []
        for i in range(len(data)):
            record = data[i]
            if i == 0 or record["metadata"]["session"] != data[i-1]["metadata"]["session"]:
                session_data = {
                    "session": record["metadata"]["session"],
                    "date": record["metadata"]["date"],
                    "session_id": record["metadata"]["session_id"],
                    "session_name": record["metadata"]["session_name"],
                    "init_query": "",
                    "conversation" : [{"input" : record.get("input", ""), 
                                    "answer" : record.get("answer", ""),
                                    "query_id" : record["metadata"].get("query_id", ""),
                                    "order" : record["metadata"].get("order", 0)},]
                }
                new_data.append(session_data)
            else:
                new_data[-1]["conversation"].append({"input" : record.get("input", ""), 
                                                    "answer" : record.get("answer", ""),
                                                    "query_id" : record["metadata"].get("query_id", ""),
                                                    "order" : record["metadata"].get("order", 0)})
        [TestSession.model_validate(session) for session in new_data]
        return new_data
        
    #JSON->LANGSMITH
    def from_json_to_langsmith(self, data):
        data_cp = data.copy()
        [TestSession.model_validate(session) for session in data_cp]
        all_data = []
        for session in data_cp:
            session_data = []
            conversation = session.pop("conversation", [])  
            for turn in conversation:
                session_data.append({
                    "input": turn["input"],
                    "answer": turn["answer"],
                    "metadata" : {
                        "query_id" : turn.get("query_id", ""),
                        "order" : turn.get("order", 0),
                        **session, 
                    }
                })
            all_data.extend(session_data)
        [LangSmithData.model_validate(record) for record in all_data]
        return all_data 
    
    def load_json_manus_file(self, dataset_name : str, filepath : str = None):
        if not filepath:
            file = f'{dataset_name}/manuscript-{dataset_name}.json'
            with open(file, 'r') as f:
                data = json.load(f)
        else:
            with open(filepath, 'r') as f:
                data = json.load(f)

        return data

