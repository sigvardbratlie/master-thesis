from langsmith import Client
from dotenv import load_dotenv
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


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
            examples = list(self.client.list_examples(dataset_name=dataset_name))
            logger.info(f"Loaded {len(examples)} examples from dataset '{dataset_name}'.")
            return [example.model_dump() for example in examples]
        except Exception as e:
            logger.error(f"Error loading examples from dataset '{dataset_name}': {e}")
            return []
        
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
                                        metadata = metadata)
            logger.info(f"Uploaded {len(inputs)} examples to dataset '{dataset_name}'.")
        except Exception as e:
            logger.error(f"Error uploading examples to dataset '{dataset_name}': {e}", exc_info=True)

    def load_json_manus_file(self, dataset_name : str, filepath : str = None):
        if not filepath:
            file = f'{dataset_name}/manuscript-{dataset_name}.json'
            with open(file, 'r') as f:
                data = json.load(f)
        else:
            with open(filepath, 'r') as f:
                data = json.load(f)

        return data

