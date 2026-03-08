
import logging
from dotenv import load_dotenv
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from bert_score import score
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from evals.models import DeepEvalObservation, ResourceObservation, ReferenceObservation

logging.getLogger(__name__).setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
load_dotenv()

class CollectMetrics:
    def __init__(self):
        self.embedding_model = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_run_type(self, path):
        run = path.split("/")[-1].replace("llm-as-judge_", "")
        return "_".join(run.split("_")[:-1])

    def organize_runs_by_type(self, eval_res):
        runs = {}
        for path in eval_res.keys():
            ext_path = self._extract_run_type(path)
            if ext_path in runs:
                runs[ext_path].append(eval_res[path])
            else:
                runs[ext_path] = [eval_res[path]]
        return runs

    def _extract_query_metrics(self, query):
        correctness = relevancy = completeness = 0.0
        for metric in query.metrics_data:
            if metric.name == 'correctness [GEval]':
                correctness = metric.score
            elif metric.name == 'relevancy [GEval]':
                relevancy = metric.score
            elif metric.name == 'completeness [GEval]':
                completeness = metric.score
        return {"correctness": correctness, "relevancy": relevancy, "completeness": completeness}

    def similarity_score(self, outputs: list[str] | list[list[float]], embed = True) -> float:
        """Cosine similarity between sentence embeddings of multiple outputs for the same query."""
        if len(outputs) <= 1:
            return 1.0
        if embed:
            embeddings = self.embedding_model.embed_documents(outputs)
        else:            
            embeddings = outputs
        sim_matrix = cosine_similarity(embeddings)
        n = len(outputs)
        mask = np.triu(np.ones((n, n), dtype=bool), k=1)
        return float(sim_matrix[mask].mean())

    # ── Public collection methods ─────────────────────────────────────────────


    def collect_berts(self, runs) -> list[ReferenceObservation]:
        aa_all = []
        ea_all = []
        metadata_list = [] # Store metadata to pair with scores later

        for run in runs:
            for res in run.results:
                for query in res.test_results:
                    aa_all.append(query.actual_output)
                    ea_all.append(query.expected_output
                    )
                    # Keep track of the specific metadata for THIS query
                    metadata_list.append({
                        "dataset_name": run.dataset_name,
                        "eval_run_id": run.eval_run_id,
                        "query_id": query.additional_metadata.get("query_id"),
                        "session_id": query.additional_metadata.get("session_id"),
                        "session": query.additional_metadata.get("session"),
                        "session_name": query.additional_metadata.get("session_name"),
                        "llm_model": run.llm_model,
                        "agent_type": run.agent_type
                    })

        # Batch process BERTScore (more efficient)
        bert_prec, bert_rec, bert_f1 = score(aa_all, ea_all, lang="no")
        
        # Batch process S-BERT Embeddings
        aa_embeddings = self.embedding_model.embed_documents(aa_all)
        ea_embeddings = self.embedding_model.embed_documents(ea_all)

        output = []
        for i in range(len(aa_all)):
            # Calculate S-BERT for this specific pair
            s_bert = self.similarity_score([aa_embeddings[i], ea_embeddings[i]], embed=False)
            
            # Use the stored metadata for this specific index
            meta = metadata_list[i]
            
            output.append(ReferenceObservation(
                dataset_name=meta["dataset_name"],
                eval_run_id=meta["eval_run_id"],
                query_id=meta["query_id"],
                session_id=meta["session_id"],
                session=meta["session"],
                session_name=meta["session_name"],
                llm_model=meta["llm_model"],
                agent_type=meta["agent_type"],
                bert_precision=bert_prec[i].item(),
                bert_recall=bert_rec[i].item(),
                bert_f1=bert_f1[i].item(),
                s_bert_similarity=s_bert
            ))
        return output
        

    def collect_resource_metrics(self, runs) -> list[ResourceObservation]:
        """One ResourceObservation per query × eval_run, built from 04_results (GatheredResultPayload)."""
        observations = []
        for run in runs:
            for session in run.sessions:
                for conv in session.conversation:
                    if not conv.token_counts or not conv.time_counts:
                        continue
                    observations.append(ResourceObservation(
                        dataset_name=run.dataset_name,
                        eval_run_id=run.eval_run_id,
                        query_id=conv.query_id,
                        session_id=session.runtime_session_id,
                        session=session.session,
                        session_name = session.session_name,
                        llm_model=run.llm_model,
                        agent_type=run.agent_type,
                        input_tokens=conv.token_counts.input_tokens,
                        output_tokens=conv.token_counts.output_tokens,
                        total_tokens=conv.token_counts.total_tokens,
                        llm_calls=conv.token_counts.llm_calls,
                        starttime=conv.time_counts.starttime,
                        endtime=conv.time_counts.endtime,
                        duration_seconds=conv.time_counts.duration_seconds,
                    ))
        return observations
    
    def collect_deepeval_metrics(self, runs) -> list[DeepEvalObservation]:
        """One DeepEvalObservation per query × eval_run from LLM-as-judge."""
        observations = []
        for run in runs:
            for res in run.results:
                for query in res.test_results:
                    m = self._extract_query_metrics(query)
                    observations.append(DeepEvalObservation(
                        dataset_name=run.dataset_name,
                        eval_run_id=run.eval_run_id,
                        query_id=query.additional_metadata.get("query_id"),
                        session_id=query.additional_metadata.get("session_id"),
                        session=query.additional_metadata.get("session"),
                        session_name=query.additional_metadata.get("session_name"),
                        llm_model=run.llm_model,
                        agent_type=run.agent_type,
                        name=query.name,
                        correctness=m["correctness"],
                        relevancy=m["relevancy"],
                        completeness=m["completeness"],
                        success=query.success,
                    ))
        return observations
