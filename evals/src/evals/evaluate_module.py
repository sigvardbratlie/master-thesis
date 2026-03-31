from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import GEval, AnswerRelevancyMetric
from deepeval import evaluate
from deepeval.evaluate import AsyncConfig
from deepeval.test_case import ConversationalTestCase, Turn, TurnParams
from deepeval.metrics import ConversationalGEval
from deepeval.models import GeminiModel
import logging
from google.cloud import storage
import os

from .models import ConversationTurn, GatheredResultPayload, Session

logger = logging.getLogger(__name__)
logging.getLogger("absl").setLevel(logging.WARNING)  
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


class Evaluater:
    def __init__(self, client=None, model = "gpt-4.1", bucket_name="master-thesis-prod", throttle_value=5, max_concurrent=1, threshold=0.5):
        self._client = client or storage.Client()
        self.bucket = self._client.bucket(bucket_name)
        self.model = self._pick_llm(model=model)
        self.throttle_value = throttle_value
        self.max_concurrent = max_concurrent
        self.threshold = threshold
        #self.sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2")

    
    def _pick_llm(self, model : str):
        if "gemini" in model:
            return GeminiModel(model=model, api_key=os.getenv("GOOGLE_API_KEY"),
                               generation_kwargs={"thinking_config": {"thinking_budget": 1024}})
        elif "gpt" in model:
            return model
        else:
            raise TypeError(f'Only gpt and gemini are implemented')

    
    def collect_single(self, conversation_turn: ConversationTurn, session_name: str = "unknown", session_id: str = "unknown", session: int = None) -> LLMTestCase | None:
        if not conversation_turn.input or not conversation_turn.model_response or not conversation_turn.answer:
            logger.warning("Conversation turn is missing required fields. Skipping evaluation for this turn.")
            return None
        return LLMTestCase(
            name=f"Turn {conversation_turn.order} in session {session_name}",
            input=conversation_turn.input,
            actual_output=conversation_turn.model_response,
            expected_output=conversation_turn.answer,
            additional_metadata={
                "turn_order": conversation_turn.order,
                "query_id": conversation_turn.query_id,
                "session_name": session_name,
                "session_id": session_id,
                "session": session,
                "question_type": conversation_turn.question_type,
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
            threshold=self.threshold,
        )

        return evaluate(test_cases=[convo_test_case], metrics=[metric], async_config=AsyncConfig(max_concurrent=self.max_concurrent, throttle_value=self.throttle_value))

    def _build_metrics(self, include_completeness: bool):
        correctness = GEval(
            name="correctness",
            criteria=(
                "Evaluate whether the factual claims in actual_output are accurate with respect to the expected answer. "
                "Treat expected_output as a minimum baseline; additional facts in actual_output must not lower the score. "
                "Reduce the score only for claims that are directly and demonstrably incorrect."
            ),
            evaluation_steps=[
                "Identify every factual claim in actual_output.",
                "Assess whether each claim is accurate.",
                "Identify direct contradictions with expected_output — where actual_output asserts something demonstrably false.",
                "Score 1.0 for a fully correct answer; reduce only in proportion to genuine factual errors.",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=self.model,
            threshold=self.threshold,
        )

        relevancy = GEval(
            name="relevancy",
            criteria=(
                "Evaluate whether actual_output addresses the user's query. "
                "Treat expected_output as a minimum baseline; additional facts in actual_output must not lower the score. "
                "Score low only if the response is clearly off-topic or fails to address the query."
            ),
            evaluation_steps=[
                "Identify the subject and intent of the input question.",
                "Determine whether actual_output attempts to answer it.",
                "Score high if on-topic, low only if the response addresses a substantially different question.",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=self.model,
            threshold=self.threshold,
        )

        if not include_completeness:
            return [correctness, relevancy]

        completeness = GEval(
            name="completeness",
            criteria=(
                "Evaluate whether actual_output covers the key claims listed in expected_output. "
                "expected_output contains only the minimum required claims — it is not an exhaustive model answer. "
                "Check that each individual claim in expected_output is addressed in actual_output. "
                "Additional correct facts in actual_output must not lower the score."
            ),
            evaluation_steps=[
                "Identify the key claims in expected_output.",
                "For each claim, determine whether actual_output addresses it.",
                "Treat additional correct facts in actual_output as a positive signal.",
                "Do not penalize for omitting information not present in expected_output.",
            ],
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
            model=self.model,
            threshold=self.threshold,
        )

        return [correctness, completeness, relevancy]

    def run_session_eval(self, session: Session) -> list:
        test_cases = [
            tc for conv in session.conversation
            if (tc := self.collect_single(conversation_turn=conv,
                                          session_name=session.session_name,
                                          session_id=session.runtime_session_id,
                                          session=session.session)) is not None
        ]

        # Split by question_type: only factual questions get completeness
        factual = [tc for tc in test_cases if tc.additional_metadata.get("question_type") == "factual"]
        non_factual = [tc for tc in test_cases if tc.additional_metadata.get("question_type") != "factual"]

        results = []
        async_cfg = AsyncConfig(max_concurrent=self.max_concurrent, throttle_value=self.throttle_value)

        if factual:
            results.append(evaluate(test_cases=factual, metrics=self._build_metrics(include_completeness=True), async_config=async_cfg))
        if non_factual:
            results.append(evaluate(test_cases=non_factual, metrics=self._build_metrics(include_completeness=False), async_config=async_cfg))

        return results

    def run_evaluation(self, data: GatheredResultPayload) -> list:
        results = []
        for session in data.sessions:
            results.extend(self.run_session_eval(session))
        return results
    

    
    