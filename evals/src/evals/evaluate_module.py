from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval, AnswerRelevancyMetric
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.test_case import ConversationalTestCase, Turn, TurnParams
from deepeval.metrics import ConversationalGEval
import logging
import json
from datetime import datetime
from deepeval.evaluate.types import EvaluationResult
from google.cloud import storage

from .models import ConversationTurn, EvalOutput, GatheredResultPayload, Session


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class Evaluater:
    def __init__(self, client=None, model = "gpt-4.1", bucket_name="master-thesis-prod"):
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)
        self.model = model

    def collect_single(self, conversation_turn: ConversationTurn, session_name: str = "unknown") -> LLMTestCase | None:
        if not conversation_turn.input or not conversation_turn.model_response or not conversation_turn.answer:
            logger.warning("Conversation turn is missing required fields. Skipping evaluation for this turn.")
            return None
        return LLMTestCase(
            name=f"Turn {conversation_turn.order or 'unknown'} in session {session_name}",
            input=conversation_turn.input,
            actual_output=conversation_turn.model_response,
            expected_output=conversation_turn.answer,
            additional_metadata={
                "turn_order": conversation_turn.order or "unknown",
                "query_id": conversation_turn.query_id or "unknown",
            },
        )

    def eval_conversation(self, conversation: list[ConversationTurn]):
        turns = []
        for item in conversation:
            turns.append(Turn(role="user", content=item.input))
            turns.append(Turn(role="assistant", content=item.model_response))

        convo_test_case = ConversationalTestCase(turns=turns)

        metric = ConversationalGEval(
            name="Legal Accuracy",
            criteria="Evaluate whether the assistant's legal analysis is accurate and consistent across the conversation.",
            evaluation_params=[TurnParams.CONTENT],
            threshold=0.5,
        )

        return evaluate(test_cases=[convo_test_case], metrics=[metric], async_config=AsyncConfig(max_concurrent=2, throttle_value=3))

    def run_session_eval(self, session: Session):
        test_cases = [
            tc for conv in session.conversation
            if (tc := self.collect_single(conversation_turn=conv, session_name=session.session_name)) is not None
        ]
        correctness = GEval(
                        name="correctness",
                        criteria="Determine if actual_output is factually correct based on expected_output",
                        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                        model=self.model,
                        threshold=0.5,
                    )
        completeness = GEval(
                        name="completeness",
                        criteria="Determine if actual_output covers all key points and facts present in expected_output. Penalize missing critical information.",
                        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                        model=self.model,
                        threshold=0.5,
                    )
        relevancy = AnswerRelevancyMetric(
                        threshold=0.5,
                        model=self.model,
                    )

        return evaluate(test_cases=test_cases, metrics=[correctness, completeness, relevancy], async_config=AsyncConfig(max_concurrent=2, throttle_value=3))

    def run_evaluation(self, data: GatheredResultPayload) -> list:
        results = []
        for session in data.sessions:
            results.append(self.run_session_eval(session))
        return results

    
