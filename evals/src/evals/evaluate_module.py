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
            return GeminiModel(model=model, api_key=os.getenv("GOOGLE_API_LEY"),)
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
                "session_name" : session_name,
                "session_id": session_id,
                "session": session,  
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

    def run_session_eval(self, session: Session):
        test_cases = [
            tc for conv in session.conversation
            if (tc := self.collect_single(conversation_turn=conv, 
                                          session_name=session.session_name, 
                                          session_id=session.runtime_session_id, 
                                          session=session.session)) is not None
        ]

        
        completeness = GEval(
                        name="completeness",
                        criteria="""Assess if the actual_output covers all key points mentioned in the expected_output.
                        The goal is 100% recall of the expected_output. 
                        If the agent provides additional relevant information beyond thes expected_output, it should NOT decrease the completeness score.""",
                        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                        model=self.model,
                        threshold=self.threshold,
                    )

        correctness = GEval(
                    name="correctness",
                    criteria="""Determine if actual_output is factually correct. 
                    Use expected_output as a primary guide, but do not penalize the actual_output 
                    for providing additional relevant facts found in the documents that are 
                    missing from the expected_output. Only penalize direct contradictions.""",
                    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                    model=self.model,
                    threshold=self.threshold,
                )

        relevancy = GEval(
                    name="relevancy",
                    criteria="""Evaluate if the response addresses the user's query. 
                    In 'sequence of events' queries, providing extra events within the requested 
                    timeframe is acceptable and should not be penalized as 'irrelevant' unless 
                    they are completely unrelated to the legal case at hand.""",
                    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
                    model=self.model,
                    threshold=self.threshold,
                )

        return evaluate(test_cases=test_cases, metrics=[correctness, completeness, relevancy], async_config=AsyncConfig(max_concurrent=self.max_concurrent, throttle_value=self.throttle_value))

    def run_evaluation(self, data: GatheredResultPayload) -> list:
        results = []
        for session in data.sessions:
            results.append(self.run_session_eval(session))
        return results
    

    
    