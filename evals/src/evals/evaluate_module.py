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
            return GeminiModel(model=model, api_key=os.getenv("GOOGLE_API_KEY"),)
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
                        criteria="""Score how well actual_output covers the key points in expected_output.

                        CRITICAL RULES — violations invalidate the evaluation:
                        - expected_output is a MINIMUM EXAMPLE answer, not an exhaustive truth.
                        - actual_output identifying MORE valid points than expected_output is BETTER, not worse.
                        - Restrictive language in expected_output such as 'only', 'sole', or 'the only' describes that author's summary, NOT a cap on what a correct answer may contain. Never use such language as grounds to penalise additional correct points.
                        - Extra information in actual_output must NEVER lower the score. It should raise it.

                        Score solely on: what fraction of expected_output's key facts appear in actual_output.""",
                        evaluation_steps=[
                            "List the key facts from expected_output.",
                            "For each fact, check whether actual_output covers it.",
                            "Note any additional facts in actual_output: these are a bonus, never a penalty.",
                            "Score = fraction of expected_output facts covered, boosted if actual_output provides additional correct information.",
                        ],
                        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                        model=self.model,
                        threshold=self.threshold,
                    )

        correctness = GEval(
                    name="correctness",
                    criteria="""Score whether the claims in actual_output are factually accurate and legally sound given the input question.

                    CRITICAL RULES — violations invalidate the evaluation:
                    - expected_output is ONE valid sample answer. It is NOT the complete truth and may itself be incomplete.
                    - If actual_output identifies additional correct facts, legal arguments, or relevant clauses not mentioned in expected_output, this RAISES the score — it does NOT constitute a contradiction.
                    - Restrictive language in expected_output such as 'only', 'sole', or 'the only reservation' is the sample author's opinion, NOT a factual constraint. Never treat it as evidence that extra correct points in actual_output are wrong.
                    - A contradiction is ONLY when actual_output makes a claim that is directly and clearly factually wrong (e.g. names the wrong law, inverts a fact, denies something that demonstrably occurred).
                    - A more detailed, thorough answer that is factually correct must score HIGHER than a brief correct answer.""",
                    evaluation_steps=[
                        "Read the input question to understand what is being asked.",
                        "Identify every factual or legal claim in actual_output.",
                        "For each claim: is it factually/legally defensible? If yes, it is not an error.",
                        "Check whether expected_output contains any facts that actual_output directly contradicts (not merely supplements). Count only those as errors.",
                        "Do not penalise actual_output for identifying valid points absent from expected_output.",
                        "Score: 1.0 for fully correct (possibly richer than expected), lower only for genuine factual errors or direct contradictions.",
                    ],
                    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.EXPECTED_OUTPUT],
                    model=self.model,
                    threshold=self.threshold,
                )

        relevancy = GEval(
                    name="relevancy",
                    criteria="""Score whether actual_output attempts to answer the user's query.

                    CRITICAL RULES:
                    - Relevancy is ONLY about whether the response is directed at the question asked. It is NOT about whether the content is correct, complete, or contains the 'right' details — that is judged by other metrics.
                    - Do NOT penalise a response for including actors, facts, or details you personally consider peripheral. If the response is clearly an attempt to answer the query, it is relevant.
                    - A response that fully answers the query AND provides additional information must score at least as high as one that only answers the query.
                    """,
                    evaluation_steps=[
                        "Identify what the input is asking for (topic and type of answer).",
                        "Ask: is actual_output an attempt to answer that question? If yes, it is relevant — score high.",
                        "Do NOT judge whether the specific content (e.g. which actors are listed) is correct or appropriate — that belongs to other metrics.",
                        "Only score low if the response addresses a completely different question or topic.",
                    ],
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
    

    
    