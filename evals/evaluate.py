from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval
from deepeval import evaluate
from deepeval.test_case import ConversationalTestCase, Turn, TurnParams
from deepeval.metrics import ConversationalGEval
import argparse
import logging
from evals import Dataset

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

from deepeval.evaluate.types import EvaluationResult
from google.cloud import storage
import json

class Evaluater:
    def __init__(self, client=None, bucket_name="master-thesis-prod"):
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)

    def collect_single(self, conversation_turn : dict,session_name : str = "unknown"): 
        if "input" not in conversation_turn or "model_response" not in conversation_turn or "answer" not in conversation_turn:
            raise ValueError("Conversation turn must contain 'input', 'model_response', and 'answer' fields.")
        if not conversation_turn.get("input") or not conversation_turn.get("model_response") or not conversation_turn.get("answer"):
            logger.warning("Conversation turn is missing required fields. Skipping evaluation for this turn.")
            return
        test_case = LLMTestCase(name = f"Turn {conversation_turn.get('order', 'unknown')} in session {session_name}",
                                input = conversation_turn.get("input"), 
                                actual_output = conversation_turn.get("model_response"),
                                expected_output=conversation_turn.get("answer"),
                                additional_metadata={"turn_order": conversation_turn.get("order", "unknown"),
                                                     "query_id" : conversation_turn.get("query_id", "unknown")})

        correctness = GEval(name = "correctness",
                            criteria="Determine if actual_output is factually correct based on expected_output",
                            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                            threshold=0.5)

        return {"test_case": test_case, "metric": correctness}

    def eval_conversation(self, conversation : list[dict]):
        turns = []
        for item in conversation:
            turns.append(Turn(role="user", content=item["input"]))
            turns.append(Turn(role="assistant", content=item["model_response"]))

        convo_test_case = ConversationalTestCase(turns=turns)

        metric = ConversationalGEval(
            name="Legal Accuracy",
            criteria="Evaluate whether the assistant's legal analysis is accurate and consistent across the conversation.",
            evaluation_params=[TurnParams.CONTENT],
            threshold=0.5
        )

        return evaluate(test_cases=[convo_test_case], metrics=[metric])
    
    def run_session_eval(self, session : dict):
        test_cases = []
        metrics = []
        for conversation_turn in session.get("conversation", []):
            collected = self.collect_single(conversation_turn=conversation_turn, session_name=session.get("session_name", "unknown"))
            if collected:
                test_cases.append(collected["test_case"])
                metrics.append(collected["metric"])

        return evaluate(test_cases=test_cases, metrics=metrics)

    def run_evaluation(self,data : dict):
        sessions = data.get("sessions", [])
        results = []
        for session in sessions:
            results.append(self.run_session_eval(session))
        return results

    def save_evaluation_results(self, results : list[EvaluationResult]):
        output = {
            "dataset_name": self.data.get("dataset_name"),
            "project_id": self.data.get("project"),
            "user_id": self.data.get("user"),
            "eval_run_id": self.data.get("eval_run_id"),
            "llm_model": self.data.get("llm_model"),
            "custom_agent": self.data.get("custom_agent"),
            "results": [r.model_dump() for r in results if r and isinstance(r, EvaluationResult)],
            }
        agent_type = "custom" if self.data.get("custom_agent") else "baseline"
        filepath = f'datasets/{self.data.get("dataset_name")}/05_evals/{self.data.get("llm_model")}_{agent_type}_{self.data.get("eval_run_id")}.json'
        blob = self.bucket.blob(filepath)
        blob.upload_from_string(json.dumps(output), content_type='application/json')

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Evaluate attachment assignment")
    parser.add_argument("--dataset", type=str, help="Dataset name to evaluate")
    args = parser.parse_args()
    dataset_name = args.dataset

    ds = Dataset(dataset_name)
    collected_results = ds.load_results()
    if not collected_results:
        logger.error("No evaluation results found to save.")
    else:
        evaluater = Evaluater()
        results = evaluater.run_evaluation(data = collected_results)
        evaluater.save_evaluation_results(results)