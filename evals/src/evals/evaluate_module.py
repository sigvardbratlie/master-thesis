from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.test_case import ConversationalTestCase, Turn, TurnParams
from deepeval.metrics import ConversationalGEval
import logging
from datetime import datetime
from deepeval.evaluate.types import EvaluationResult
from google.cloud import storage
import json


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Evaluater:
    def __init__(self, client=None, bucket_name="master-thesis-prod"):
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)

    def collect_single(self, conversation_turn: dict, session_name: str = "unknown") -> LLMTestCase | None:
        if "input" not in conversation_turn or "model_response" not in conversation_turn or "answer" not in conversation_turn:
            raise ValueError("Conversation turn must contain 'input', 'model_response', and 'answer' fields.")
        if not conversation_turn.get("input") or not conversation_turn.get("model_response") or not conversation_turn.get("answer"):
            logger.warning("Conversation turn is missing required fields. Skipping evaluation for this turn.")
            return None
        return LLMTestCase(
            name=f"Turn {conversation_turn.get('order', 'unknown')} in session {session_name}",
            input=conversation_turn.get("input"),
            actual_output=conversation_turn.get("model_response"),
            expected_output=conversation_turn.get("answer"),
            additional_metadata={
                "turn_order": conversation_turn.get("order", "unknown"),
                "query_id": conversation_turn.get("query_id", "unknown"),
            },
        )

    def eval_conversation(self, conversation: list[dict]):
        turns = []
        for item in conversation:
            turns.append(Turn(role="user", content=item["input"]))
            turns.append(Turn(role="assistant", content=item["model_response"]))

        convo_test_case = ConversationalTestCase(turns=turns)

        metric = ConversationalGEval(
            name="Legal Accuracy",
            criteria="Evaluate whether the assistant's legal analysis is accurate and consistent across the conversation.",
            evaluation_params=[TurnParams.CONTENT],
            threshold=0.5,
        )

        return evaluate(test_cases=[convo_test_case], metrics=[metric], async_config=AsyncConfig(max_concurrent=2, throttle_value=3))

    def run_session_eval(self, session: dict):
        test_cases = [
            tc for conv in session.get("conversation", [])
            if (tc := self.collect_single(conversation_turn=conv, session_name=session.get("session_name", "unknown"))) is not None
        ]

        correctness = GEval(
            name="correctness",
            criteria="Determine if actual_output is factually correct based on expected_output",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            threshold=0.5,
        )

        return evaluate(test_cases=test_cases, metrics=[correctness], async_config=AsyncConfig(max_concurrent=2, throttle_value=3))

    def run_evaluation(self,data : dict):
        if not isinstance(data, dict):
            raise ValueError("Input data must be a dictionary.")
        sessions = data.get("sessions", [])
        results = []
        for session in sessions:
            results.append(self.run_session_eval(session))
        return results

    def save_evaluation_results(self, results : list[EvaluationResult], data : dict):
        if not isinstance(data, dict):
            raise ValueError("Input data must be a dictionary.")
        if not isinstance(results, list) or not all(isinstance(r, EvaluationResult) for r in results):
            raise ValueError("Results must be a list of EvaluationResult instances.")
        
        agent_type = data.get("agent_type", "unknown")
        output = {
            "dataset_name": data.get("dataset_name"),
            "project_id": data.get("project_id"),
            "user_id": data.get("user_id"),
            "eval_run_id": data.get("eval_run_id"),
            "llm_model": data.get("llm_model"),
            "agent_type": agent_type,
            "token_counts" : data.get("token_counts"),
            "created_at": datetime.now().isoformat(),
            "results": [r.model_dump() for r in results if isinstance(r, EvaluationResult)] if results else None,
            }
        filepath = f'datasets/{data.get("dataset_name")}/05_evals/llm-as-judge_{data.get("llm_model")}_{agent_type}_{data.get("eval_run_id")}.json'
        blob = self.bucket.blob(filepath)
        blob.upload_from_string(json.dumps(output, indent=4, ensure_ascii=False), content_type='application/json')
        return output